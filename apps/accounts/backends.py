from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from apps.accounts.models import User


class EmailOrUsernameBackend(ModelBackend):
    """Sign in with a username or an email address."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = (username or "").strip()
        if not identifier or password is None:
            return None
        user = User.objects.filter(
            Q(username__iexact=identifier) | Q(email__iexact=identifier)
        ).first()
        if user is None or not user.check_password(password):
            return None
        if not self.user_can_authenticate(user):
            return None
        return user
