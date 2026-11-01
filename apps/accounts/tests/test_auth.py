from django.core import mail
from django.test import TestCase

from apps.accounts.models import User
from apps.common.factories import make_user


class AuthTests(TestCase):
    def test_register_login_and_pages(self):
        response = self.client.post(
            "/accounts/register/",
            {
                "full_name": "Ganesh Rao",
                "username": "ganesh",
                "email": "ganesh@example.com",
                "password1": "ValidPass123",
                "password2": "ValidPass123",
                "accept_terms": "on",
            },
        )
        self.assertRedirects(response, "/accounts/login/")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(User.objects.filter(username="ganesh").exists())
        self.assertEqual(len(mail.outbox), 1)
        signed_in = self.client.post(
            "/accounts/login/",
            {"username": "ganesh", "password": "ValidPass123"},
        )
        self.assertRedirects(signed_in, "/dashboard/")
        for path in (
            "/dashboard/",
            "/expenses/",
            "/expenses/add/",
            "/friends/",
            "/friends/add/",
            "/friends/requests/",
            "/groups/",
            "/groups/create/",
            "/balances/",
            "/settle/",
            "/settlements/",
            "/recurring/",
            "/recurring/add/",
            "/categories/",
            "/budgets/",
            "/reports/",
            "/notifications/",
            "/debts/",
            "/debts/add/",
            "/expenses/templates/",
            "/accounts/profile/",
            "/accounts/settings/",
        ):
            page = self.client.get(path)
            self.assertEqual(page.status_code, 200, path)

    def test_login_throttle(self):
        make_user("rahul")
        for _index in range(5):
            self.client.post("/accounts/login/", {"username": "rahul", "password": "wrong-password"})
        blocked = self.client.post("/accounts/login/", {"username": "rahul", "password": "ValidPass123"})
        self.assertContains(blocked, "Too many sign-in attempts")

    def test_duplicate_username(self):
        make_user("priya")
        response = self.client.post(
            "/accounts/register/",
            {
                "full_name": "Priya N",
                "username": "priya",
                "email": "other@example.com",
                "password1": "ValidPass123",
                "password2": "ValidPass123",
                "accept_terms": "on",
            },
        )
        self.assertContains(response, "already taken")

    def test_password_minimum_is_six_characters(self):
        short = self.client.post(
            "/accounts/register/",
            {
                "full_name": "Short Pass",
                "username": "shortpass",
                "email": "short@example.com",
                "password1": "12345",
                "password2": "12345",
                "accept_terms": "on",
            },
        )
        self.assertContains(short, "too short")
        self.assertFalse(User.objects.filter(username="shortpass").exists())
        accepted = self.client.post(
            "/accounts/register/",
            {
                "full_name": "Six Pass",
                "username": "sixpass",
                "email": "six@example.com",
                "password1": "123456",
                "password2": "123456",
                "accept_terms": "on",
            },
        )
        self.assertRedirects(accepted, "/accounts/login/")

    def test_password_reset_email(self):
        make_user("arjun")
        response = self.client.post("/accounts/password-reset/", {"email": "arjun@example.com"})
        self.assertRedirects(response, "/accounts/password-reset/done/")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Update your SplitMate password")
        self.assertIn("update the password for your SplitMate account", message.body)
        self.assertIn("/accounts/password-reset/", message.body)
        self.assertIn("arjun@example.com", message.to)
