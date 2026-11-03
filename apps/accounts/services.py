from datetime import timedelta
from email.message import EmailMessage as MimePart
from pathlib import Path

from django.conf import settings
from django.contrib.auth import logout
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.utils.html import escape
from django.utils import timezone

from apps.accounts.models import EmailVerificationToken, LoginAttempt, User
from apps.common.audit import write_audit
from apps.common.exceptions import DomainError
from apps.common.tokens import hash_token, make_token
from apps.groups.models import Group, GroupInvitation, GroupMembership
from apps.groups.services import link_group_invitations


def record_login(username, ip, successful):
    username = (username or "")[:150].lower()
    ip = ip or "0.0.0.0"
    LoginAttempt.objects.create(username=username, ip_address=ip, successful=successful)
    LoginAttempt.objects.filter(
        username=username, created_at__lt=timezone.now() - timedelta(days=7)
    ).delete()


def login_blocked(username, ip):
    since = timezone.now() - timedelta(minutes=15)
    username = (username or "")[:150].lower()
    ip = ip or "0.0.0.0"
    user_failures = LoginAttempt.objects.filter(
        username=username, ip_address=ip, successful=False, created_at__gte=since
    ).count()
    ip_failures = LoginAttempt.objects.filter(ip_address=ip, successful=False, created_at__gte=since).count()
    return user_failures >= 5 or ip_failures >= 30


def send_welcome(user):
    name = escape(user.display_name)
    text = (
        f"Welcome to SplitMate, {user.display_name}.\n\n"
        "Know who paid, who shares, and who still owes.\n\n"
        "Your account is ready. Sign in with the same username and password to open your dashboard. "
        "SplitMate keeps a clear record of shared bills, repayments, and balances."
    )
    html = (
        '<img src="cid:welcome-cover" alt="Welcome to SplitMate. Know who paid, who shares, and who still owes." '
        'style="width:100%;max-width:640px;border-radius:16px;display:block;">'
        f"<p>Hello {name},</p>"
        "<p>Your SplitMate account is ready. Sign in with the same username and password you just chose.</p>"
        "<p>Your dashboard shows what you owe, what you are owed, and the shared bills you add with other people. "
        "SplitMate records the expenses. It does not move the money.</p>"
    )
    message = EmailMultiAlternatives(
        subject="Welcome to SplitMate",
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html, "text/html")
    cover = Path(settings.BASE_DIR) / "static" / "images" / "welcome-cover.jpg"
    if cover.is_file():
        image = MimePart()
        image.set_content(
            cover.read_bytes(),
            maintype="image",
            subtype="jpeg",
            cid="welcome-cover",
            disposition="inline",
            filename="welcome-cover.jpg",
        )
        message.attach(image)
    message.send(fail_silently=False)


def send_verification(user, request=None):
    raw, digest = make_token()
    EmailVerificationToken.objects.create(
        user=user,
        token_hash=digest,
        expires_at=timezone.now() + timedelta(days=2),
    )
    if request is not None:
        base = request.build_absolute_uri("/").rstrip("/")
    else:
        base = settings.SITE_BASE_URL
    link = f"{base}/accounts/verify-email/{raw}/"
    name = escape(user.display_name)
    text = (
        f"Confirm this address for {user.display_name}.\n\n"
        f"{link}\n\n"
        "The link expires in two days. If you did not create a SplitMate account, ignore this message."
    )
    html = (
        "<p>Confirm this address for "
        f"{name}.</p>"
        f'<p><a href="{link}">Verify your SplitMate email</a></p>'
        "<p>The link expires in two days. If you did not create a SplitMate account, ignore this message.</p>"
    )
    message = EmailMultiAlternatives(
        subject="Verify your SplitMate email",
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html, "text/html")
    message.send(fail_silently=False)
    return raw


def verify_email(raw):
    token = EmailVerificationToken.objects.select_related("user").filter(token_hash=hash_token(raw)).first()
    if token is None:
        raise DomainError("This verification link is not valid.")
    if token.used_at:
        raise DomainError("This verification link was already used.")
    if token.expires_at <= timezone.now():
        raise DomainError("This verification link has expired.")
    token.used_at = timezone.now()
    token.save(update_fields=["used_at"])
    user = token.user
    user.email_verified_at = timezone.now()
    user.save(update_fields=["email_verified_at"])
    return user


def anonymize_user(user, request=None):
    owned = GroupMembership.objects.filter(
        user=user, role=GroupMembership.Role.OWNER, status=GroupMembership.Status.ACTIVE
    ).select_related("group")
    for membership in owned:
        others = GroupMembership.objects.filter(group=membership.group, status=GroupMembership.Status.ACTIVE).exclude(
            user=user
        )
        if others.exists():
            raise DomainError(
                f"Transfer ownership of {membership.group.name} before deleting your account."
            )
        membership.group.archived_at = timezone.now()
        membership.group.save(update_fields=["archived_at", "updated_at"])
    from apps.friends.models import Friendship

    Friendship.objects.filter(Q(user_low=user) | Q(user_high=user)).exclude(
        status=Friendship.Status.BLOCKED
    ).update(status=Friendship.Status.REMOVED, responded_at=timezone.now())
    GroupInvitation.objects.filter(Q(inviter=user) | Q(invitee=user), status=GroupInvitation.Status.PENDING).update(
        status=GroupInvitation.Status.CANCELLED
    )
    if user.profile_picture:
        user.profile_picture.delete(save=False)
    user.username = f"deleted-{user.pk}"
    user.email = f"deleted-{user.pk}@users.invalid"
    user.first_name = "Deleted"
    user.last_name = "User"
    user.is_active = False
    user.anonymized_at = timezone.now()
    user.set_unusable_password()
    user.save()
    write_audit(actor=user, action="account_anonymize", instance=user, request=request)
    if request is not None:
        logout(request)
    return user


def prepare_new_user(user, request=None):
    link_group_invitations(user)
    try:
        send_welcome(user)
    except Exception:
        pass
    try:
        send_verification(user, request=request)
    except Exception:
        return None
    return user
