from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordResetConfirmView, PasswordResetView
from django.urls import reverse_lazy
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.forms import (
    LoginForm,
    PreferenceForm,
    ProfileForm,
    RegisterForm,
    StyledPasswordChangeForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
)
from apps.accounts.models import User
from apps.accounts.services import anonymize_user, prepare_new_user, send_verification, verify_email
from apps.common.exceptions import DomainError


class SplitMateLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class SplitMatePasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/password_reset_email.txt"
    html_email_template_name = "accounts/password_reset_email.html"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")
    form_class = StyledPasswordResetForm


class SplitMatePasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")
    form_class = StyledSetPasswordForm


def landing(request):
    if request.user.is_authenticated:
        return redirect("reports:dashboard")
    return render(request, "accounts/landing.html")


def terms(request):
    return render(request, "accounts/terms.html")


def privacy(request):
    return render(request, "accounts/privacy.html")


def register(request):
    if request.user.is_authenticated:
        return redirect("reports:dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        prepare_new_user(user)
        messages.success(
            request,
            "Your account is ready. Log in with the same username and password to open your dashboard.",
        )
        return redirect("accounts:login")
    return render(request, "accounts/register.html", {"form": form})


def verify_email_view(request, token):
    try:
        user = verify_email(token)
    except DomainError as exc:
        messages.error(request, str(exc))
        return redirect("accounts:login")
    messages.success(request, f"{user.email} is verified.")
    return redirect("reports:dashboard" if request.user.is_authenticated else "accounts:login")


@login_required
@require_POST
def resend_verification(request):
    if request.user.email_verified_at:
        messages.info(request, "Your email is already verified.")
    else:
        send_verification(request.user)
        messages.success(request, "If email delivery is available, a new verification link was sent.")
    return redirect("accounts:profile")


@login_required
def profile(request):
    previous_email = request.user.email
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        if user.email != previous_email:
            user.email_verified_at = None
            user.save(update_fields=["email_verified_at"])
            send_verification(user)
            messages.info(request, "Verify the new email address. The link is printed to the console in local development.")
        messages.success(request, "Profile saved.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form})


@login_required
def settings_view(request):
    preference = request.user.notification_preference
    form = PreferenceForm(request.POST or None, instance=preference)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Preferences saved.")
        return redirect("accounts:settings")
    return render(request, "accounts/settings.html", {"form": form})


@login_required
def change_password(request):
    form = StyledPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Password updated.")
        return redirect("accounts:settings")
    return render(request, "accounts/password_change.html", {"form": form})


@login_required
@require_POST
def theme(request):
    choice = request.POST.get("theme")
    if choice in {"system", "light", "dark"}:
        request.user.theme = choice
        request.user.save(update_fields=["theme"])
    return redirect(request.POST.get("next") or "reports:dashboard")


@login_required
def deactivate(request):
    if request.method == "POST":
        if not request.user.check_password(request.POST.get("password", "")):
            messages.error(request, "Password did not match.")
        else:
            request.user.is_active = False
            request.user.deactivated_at = timezone.now()
            request.user.save(update_fields=["is_active", "deactivated_at"])
            from django.contrib.auth import logout

            logout(request)
            messages.success(request, "Account deactivated. A staff member can reactivate it.")
            return redirect("accounts:landing")
    return render(request, "accounts/deactivate.html")


@login_required
def delete_account(request):
    if request.method == "POST":
        if request.POST.get("confirm") != request.user.username:
            messages.error(request, "Type your username to confirm deletion.")
        elif not request.user.check_password(request.POST.get("password", "")):
            messages.error(request, "Password did not match.")
        else:
            try:
                anonymize_user(request.user, request=request)
            except DomainError as exc:
                messages.error(request, str(exc))
                return redirect("accounts:delete")
            messages.success(request, "Your account was anonymized. Shared financial history was kept.")
            return redirect("accounts:landing")
    return render(request, "accounts/delete.html")


@login_required
def avatar(request, user_id):
    person = get_object_or_404(User, pk=user_id)
    if not person.profile_picture:
        raise Http404()
    return FileResponse(person.profile_picture.open("rb"), content_type="image/jpeg")
