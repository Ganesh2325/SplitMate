from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.accounts.models import EmailVerificationToken, LoginAttempt, User, UserNotificationPreference


@admin.register(User)
class SplitMateUserAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "is_active", "is_staff", "email_verified_at")
    search_fields = ("username", "email", "first_name", "last_name")
    list_filter = ("is_active", "is_staff", "preferred_currency")
    fieldsets = UserAdmin.fieldsets + (
        (
            "SplitMate",
            {
                "fields": (
                    "preferred_currency",
                    "timezone",
                    "language",
                    "theme",
                    "email_verified_at",
                    "terms_accepted_at",
                    "deactivated_at",
                    "anonymized_at",
                )
            },
        ),
    )


@admin.register(UserNotificationPreference)
class PreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "in_app_enabled")
    search_fields = ("user__username", "user__email")


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("username", "ip_address", "successful", "created_at")
    list_filter = ("successful",)
    search_fields = ("username", "ip_address")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(EmailVerificationToken)
class TokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "used_at", "expires_at")
    search_fields = ("user__email",)

    def has_add_permission(self, request):
        return False
