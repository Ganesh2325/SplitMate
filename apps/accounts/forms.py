from zoneinfo import available_timezones

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from apps.accounts.models import User, UserNotificationPreference
from apps.accounts.services import login_blocked, record_login
from apps.common.constants import CURRENCY_CHOICES, LANGUAGE_CHOICES, THEME_CHOICES


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Username or email",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username", "class": "form-control"}),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "class": "form-control"}),
    )

    def clean(self):
        username = self.data.get("username", "")
        ip = ""
        if self.request is not None:
            ip = self.request.META.get("REMOTE_ADDR", "")
        if login_blocked(username, ip):
            raise forms.ValidationError("Too many sign-in attempts. Wait a few minutes and try again.")
        try:
            cleaned = super().clean()
        except forms.ValidationError:
            record_login(username, ip, successful=False)
            raise
        record_login(username, ip, successful=True)
        return cleaned


class RegisterForm(forms.Form):
    full_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": "form-control"}))
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "username"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"}))
    password1 = forms.CharField(
        label="Password",
        help_text="At least 6 characters.",
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
    )
    accept_terms = forms.BooleanField(
        label="I agree to the terms and privacy policy",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with that email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password1")
        if password and password != cleaned.get("password2"):
            self.add_error("password2", "Passwords do not match.")
        if password:
            validate_password(password, user=User(username=cleaned.get("username") or "", email=cleaned.get("email") or ""))
        return cleaned

    def save(self):
        full = self.cleaned_data["full_name"].strip()
        parts = full.split(None, 1)
        return User.objects.create_user(
            username=self.cleaned_data["username"],
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
            first_name=parts[0],
            last_name=parts[1] if len(parts) > 1 else "",
            terms_accepted_at=timezone.now(),
        )


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "username",
            "email",
            "preferred_currency",
            "timezone",
            "language",
            "theme",
            "profile_picture",
        ]
        widgets = {field: forms.TextInput(attrs={"class": "form-control"}) for field in ("first_name", "last_name", "username", "email")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        zones = sorted(available_timezones())
        self.fields["timezone"].widget = forms.Select(choices=[(zone, zone) for zone in zones], attrs={"class": "form-select"})
        self.fields["preferred_currency"].widget.attrs["class"] = "form-select"
        self.fields["language"].widget.attrs["class"] = "form-select"
        self.fields["theme"].widget.attrs["class"] = "form-select"
        self.fields["profile_picture"].widget.attrs["class"] = "form-control"
        self.fields["preferred_currency"].choices = CURRENCY_CHOICES
        self.fields["language"].choices = LANGUAGE_CHOICES
        self.fields["theme"].choices = THEME_CHOICES

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("An account with that email already exists.")
        return email

    def clean_profile_picture(self):
        picture = self.cleaned_data.get("profile_picture")
        if picture and getattr(picture, "size", 0) > 2 * 1024 * 1024:
            raise forms.ValidationError("Profile pictures must be 2 MB or smaller.")
        return picture


class PreferenceForm(forms.ModelForm):
    class Meta:
        model = UserNotificationPreference
        exclude = ["user"]
        widgets = {name: forms.CheckboxInput(attrs={"class": "form-check-input"}) for name in (
            "email_friend_requests",
            "email_group_invites",
            "email_expenses",
            "email_settlements",
            "email_comments",
            "email_reminders",
            "in_app_enabled",
        )}


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class StyledPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update({"class": "form-control", "autocomplete": "email"})


class StyledSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
