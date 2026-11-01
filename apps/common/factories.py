from apps.accounts.models import User


def make_user(username, password="ValidPass123"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=password,
        first_name=username[:1].upper() + username[1:],
        last_name="Test",
    )
