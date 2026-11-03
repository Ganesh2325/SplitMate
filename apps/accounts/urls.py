from django.contrib.auth import views as auth_views
from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    path("accounts/register/", views.register, name="register"),
    path("accounts/login/", views.SplitMateLoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/password-reset/", views.SplitMatePasswordResetView.as_view(), name="password_reset"),
    path(
        "accounts/password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "accounts/password-reset/<uidb64>/<token>/",
        views.SplitMatePasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "accounts/password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    path("accounts/verify-email/resend/", views.resend_verification, name="resend_verification"),
    path("accounts/verify-email/<str:token>/", views.verify_email_view, name="verify"),
    path("accounts/profile/", views.profile, name="profile"),
    path("accounts/settings/", views.settings_view, name="settings"),
    path("accounts/password/", views.change_password, name="password"),
    path("accounts/theme/", views.theme, name="theme"),
    path("accounts/deactivate/", views.deactivate, name="deactivate"),
    path("accounts/delete/", views.delete_account, name="delete"),
    path("accounts/avatar/<int:user_id>/", views.avatar, name="avatar"),
]
