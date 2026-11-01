from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.common.audit import write_audit
from apps.common.exceptions import AuthorizationError, DomainError
from apps.common.tokens import make_token
from apps.friends.models import FriendInvitation, Friendship
from apps.notifications.services import notify, record_activity


def ordered_ids(user_a, user_b):
    if user_a.id == user_b.id:
        raise DomainError("You cannot add yourself.")
    if user_a.id < user_b.id:
        return user_a, user_b
    return user_b, user_a


def friendship_between(user_a, user_b):
    if user_a.id == user_b.id:
        return None
    low, high = ordered_ids(user_a, user_b)
    return Friendship.objects.filter(user_low=low, user_high=high).first()


def are_friends(user_a, user_b):
    row = friendship_between(user_a, user_b)
    return bool(row and row.status == Friendship.Status.ACCEPTED)


def friend_ids(user):
    rows = Friendship.objects.filter(status=Friendship.Status.ACCEPTED).filter(
        Q(user_low=user) | Q(user_high=user)
    )
    return [
        row.user_high_id if row.user_low_id == user.id else row.user_low_id
        for row in rows
    ]


def friends_of(user):
    return User.objects.filter(pk__in=friend_ids(user)).order_by("username")


def search_users(actor, query):
    query = (query or "").strip()
    if len(query) < 2:
        return User.objects.none()
    return (
        User.objects.filter(is_active=True, anonymized_at__isnull=True)
        .exclude(pk=actor.pk)
        .filter(
            Q(username__iexact=query)
            | Q(email__iexact=query)
            | Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
        .order_by("username")[:20]
    )


@transaction.atomic
def send_friend_request(actor, other, request=None):
    if not other.is_active or other.anonymized_at:
        raise DomainError("That account is not available.")
    low, high = ordered_ids(actor, other)
    existing = Friendship.objects.select_for_update().filter(user_low=low, user_high=high).first()
    if existing and existing.status == Friendship.Status.ACCEPTED:
        raise DomainError("You are already friends.")
    if existing and existing.status == Friendship.Status.BLOCKED:
        raise DomainError("That person is not available.")
    if existing and existing.status == Friendship.Status.PENDING:
        if existing.requester_id == actor.id:
            raise DomainError("You already sent a request.")
        return accept_friend_request(actor, existing, request=request)
    if existing:
        existing.requester = actor
        existing.addressee = other
        existing.status = Friendship.Status.PENDING
        existing.blocked_by = None
        existing.responded_at = None
        existing.save()
        row = existing
    else:
        row = Friendship.objects.create(
            user_low=low,
            user_high=high,
            requester=actor,
            addressee=other,
            status=Friendship.Status.PENDING,
        )
    notify(
        [other],
        actor=actor,
        verb="friend_request",
        message=f"{actor.display_name} sent you a friend request.",
        path="/friends/requests/",
        email_kind="friend",
    )
    write_audit(actor=actor, action="friend_request", instance=row, after={"status": row.status}, request=request)
    return row


def _pending_for_addressee(actor, friendship):
    if friendship.status != Friendship.Status.PENDING or friendship.addressee_id != actor.id:
        raise AuthorizationError("That request is not yours to answer.")


@transaction.atomic
def accept_friend_request(actor, friendship, request=None):
    friendship = Friendship.objects.select_for_update().get(pk=friendship.pk)
    _pending_for_addressee(actor, friendship)
    friendship.status = Friendship.Status.ACCEPTED
    friendship.responded_at = timezone.now()
    friendship.save(update_fields=["status", "responded_at", "updated_at"])
    notify(
        [friendship.requester],
        actor=actor,
        verb="friend_accept",
        message=f"{actor.display_name} accepted your friend request.",
        path=f"/friends/{actor.pk}/",
        email_kind="friend",
    )
    record_activity(
        actor=actor,
        verb="friend_accept",
        summary=f"{actor.display_name} and {friendship.requester.display_name} are now friends.",
        viewer_ids=[actor.id, friendship.requester_id],
        path=f"/friends/{friendship.requester_id}/",
    )
    write_audit(actor=actor, action="friend_accept", instance=friendship, after={"status": "accepted"}, request=request)
    return friendship


@transaction.atomic
def decline_friend_request(actor, friendship, request=None):
    friendship = Friendship.objects.select_for_update().get(pk=friendship.pk)
    _pending_for_addressee(actor, friendship)
    friendship.status = Friendship.Status.DECLINED
    friendship.responded_at = timezone.now()
    friendship.save(update_fields=["status", "responded_at", "updated_at"])
    write_audit(actor=actor, action="friend_decline", instance=friendship, request=request)
    return friendship


@transaction.atomic
def cancel_friend_request(actor, friendship, request=None):
    friendship = Friendship.objects.select_for_update().get(pk=friendship.pk)
    if friendship.status != Friendship.Status.PENDING or friendship.requester_id != actor.id:
        raise AuthorizationError("You cannot cancel that request.")
    friendship.status = Friendship.Status.CANCELLED
    friendship.responded_at = timezone.now()
    friendship.save(update_fields=["status", "responded_at", "updated_at"])
    write_audit(actor=actor, action="friend_cancel", instance=friendship, request=request)
    return friendship


@transaction.atomic
def remove_friend(actor, other, request=None):
    row = friendship_between(actor, other)
    if row is None or row.status != Friendship.Status.ACCEPTED:
        raise DomainError("You are not friends with that person.")
    row.status = Friendship.Status.REMOVED
    row.responded_at = timezone.now()
    row.save(update_fields=["status", "responded_at", "updated_at"])
    write_audit(
        actor=actor,
        action="friend_remove",
        instance=row,
        reason="Removed. Shared expenses and balances stay in the ledger.",
        request=request,
    )
    return row


@transaction.atomic
def block_user(actor, other, request=None):
    low, high = ordered_ids(actor, other)
    row = Friendship.objects.select_for_update().filter(user_low=low, user_high=high).first()
    if row is None:
        row = Friendship.objects.create(
            user_low=low,
            user_high=high,
            requester=actor,
            addressee=other,
            status=Friendship.Status.BLOCKED,
            blocked_by=actor,
            responded_at=timezone.now(),
        )
    else:
        row.status = Friendship.Status.BLOCKED
        row.blocked_by = actor
        row.responded_at = timezone.now()
        row.save()
    write_audit(actor=actor, action="friend_block", instance=row, request=request)
    return row


@transaction.atomic
def unblock_user(actor, other, request=None):
    row = friendship_between(actor, other)
    if row is None or row.status != Friendship.Status.BLOCKED or row.blocked_by_id != actor.id:
        raise AuthorizationError("You cannot unblock that person.")
    row.status = Friendship.Status.REMOVED
    row.blocked_by = None
    row.save()
    write_audit(actor=actor, action="friend_unblock", instance=row, request=request)
    return row


def invite_by_email(actor, email, request=None):
    from datetime import timedelta

    email = email.strip().lower()
    if not email or "@" not in email:
        raise DomainError("Enter an email address.", field="email")
    if User.objects.filter(email__iexact=email, is_active=True).exists():
        other = User.objects.get(email__iexact=email)
        return send_friend_request(actor, other, request=request)
    now = timezone.now()
    FriendInvitation.objects.filter(
        inviter=actor, email=email, status=FriendInvitation.Status.PENDING, expires_at__lte=now
    ).update(status=FriendInvitation.Status.EXPIRED)
    if FriendInvitation.objects.filter(
        inviter=actor, email=email, status=FriendInvitation.Status.PENDING
    ).exists():
        raise DomainError("You already invited that email address.")
    raw, digest = make_token()
    invite = FriendInvitation.objects.create(
        inviter=actor,
        email=email,
        token_hash=digest,
        expires_at=now + timedelta(days=14),
    )
    notify(
        [],
        actor=actor,
        verb="friend_invite",
        message="",
    )
    from apps.notifications.services import _send

    class Placeholder:
        pass

    # Email the address even though there is no account yet.
    transaction.on_commit(
        lambda: _send_invite(email, actor, raw)
    )
    write_audit(actor=actor, action="friend_email_invite", instance=invite, request=request)
    return invite


def _send_invite(email, actor, raw):
    from django.conf import settings
    from django.core.mail import send_mail

    link = f"{settings.SITE_BASE_URL}/friends/invite/{raw}/"
    try:
        send_mail(
            subject="SplitMate invitation",
            message=(
                f"{actor.display_name} invited you to share expenses on SplitMate.\n\n"
                f"Create an account or sign in, then open this link:\n{link}"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True,
        )
    except Exception:
        pass


def invitation_from_token(raw):
    from apps.common.tokens import hash_token

    return FriendInvitation.objects.filter(token_hash=hash_token(raw)).select_related("inviter").first()


@transaction.atomic
def accept_email_invite(user, invite, request=None):
    invite = FriendInvitation.objects.select_for_update().get(pk=invite.pk)
    if invite.status != FriendInvitation.Status.PENDING:
        raise DomainError("This invitation is no longer active.")
    if invite.expires_at <= timezone.now():
        invite.status = FriendInvitation.Status.EXPIRED
        invite.save(update_fields=["status"])
        raise DomainError("This invitation has expired.")
    if user.email.lower() != invite.email.lower():
        raise AuthorizationError("This invitation was sent to a different email address.")
    invite.status = FriendInvitation.Status.ACCEPTED
    invite.accepted_user = user
    invite.save(update_fields=["status", "accepted_user"])
    low, high = ordered_ids(invite.inviter, user)
    row = Friendship.objects.filter(user_low=low, user_high=high).first()
    if row is None:
        row = Friendship.objects.create(
            user_low=low,
            user_high=high,
            requester=invite.inviter,
            addressee=user,
            status=Friendship.Status.ACCEPTED,
            responded_at=timezone.now(),
        )
    elif row.status != Friendship.Status.BLOCKED:
        row.status = Friendship.Status.ACCEPTED
        row.responded_at = timezone.now()
        row.save()
    write_audit(actor=user, action="friend_email_accept", instance=invite, request=request)
    return row
