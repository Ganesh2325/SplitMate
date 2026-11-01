from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.common.constants import CURRENCY_CHOICES, LANGUAGE_CHOICES, THEME_CHOICES


class User(AbstractUser):
    """Person who records and shares expenses.

    Account deletion anonymizes this row. It is never removed, because expense
    and settlement history must keep a stable actor.
    """

    email = models.EmailField(unique=True)
    preferred_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="INR")
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    language = models.CharField(max_length=8, choices=LANGUAGE_CHOICES, default="en")
    theme = models.CharField(max_length=16, choices=THEME_CHOICES, default="system")
    profile_picture = models.ImageField(upload_to="profiles/", blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    anonymized_at = models.DateTimeField(null=True, blank=True)

    REQUIRED_FIELDS = ["email"]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        return self.get_full_name().strip() or self.username

    @property
    def is_email_verified(self):
        return self.email_verified_at is not None

    @property
    def is_anonymized(self):
        return self.anonymized_at is not None


class UserNotificationPreference(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="notification_preference"
    )
    email_friend_requests = models.BooleanField(default=True)
    email_group_invites = models.BooleanField(default=True)
    email_expenses = models.BooleanField(default=True)
    email_settlements = models.BooleanField(default=True)
    email_comments = models.BooleanField(default=True)
    email_reminders = models.BooleanField(default=False)
    in_app_enabled = models.BooleanField(default=True)

    def allows_email(self, kind):
        return {
            "friend": self.email_friend_requests,
            "group": self.email_group_invites,
            "expense": self.email_expenses,
            "settlement": self.email_settlements,
            "comment": self.email_comments,
            "reminder": self.email_reminders,
            "account": True,
        }.get(kind, False)


class EmailVerificationToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_tokens")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "created_at"])]


class LoginAttempt(models.Model):
    username = models.CharField(max_length=150, db_index=True)
    ip_address = models.GenericIPAddressField()
    successful = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["username", "ip_address", "created_at"]),
            models.Index(fields=["ip_address", "created_at"]),
        ]
