import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q

from apps.notifications.models import Activity, ActivityViewer, Notification

logger = logging.getLogger("splitmate")


def notify(users, *, actor=None, verb, message, path="", email_kind=""):
    actor_id = getattr(actor, "id", None)
    text = (message or "")[:255]
    for user in users:
        if user is None or user.id == actor_id:
            continue
        if not user.is_active or user.anonymized_at:
            continue
        prefs = getattr(user, "notification_preference", None)
        if prefs is None or prefs.in_app_enabled:
            Notification.objects.create(
                recipient=user,
                actor=actor if actor_id else None,
                verb=verb,
                message=text,
                path=path[:255],
                email_kind=email_kind,
            )
        if email_kind and prefs is not None and prefs.allows_email(email_kind) and user.email:
            transaction.on_commit(
                lambda user=user, text=text, path=path: _send(user, text, path)
            )


def _send(user, text, path):
    try:
        link = f"{settings.SITE_BASE_URL}{path}" if path else settings.SITE_BASE_URL
        send_mail(
            subject="SplitMate",
            message=f"{text}\n\n{link}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("email_failed user=%s", user.pk)


def record_activity(*, actor, verb, summary, group=None, path="", viewer_ids=None):
    activity = Activity.objects.create(
        actor=actor,
        verb=verb,
        summary=summary[:255],
        group=group,
        path=(path or "")[:255],
    )
    if group is None and viewer_ids:
        ActivityViewer.objects.bulk_create(
            [
                ActivityViewer(activity=activity, user_id=user_id)
                for user_id in set(viewer_ids)
                if user_id
            ],
            ignore_conflicts=True,
        )
    return activity


def feed_for(user, limit=30):
    from apps.groups.models import GroupMembership

    group_ids = GroupMembership.objects.filter(
        user=user, status=GroupMembership.Status.ACTIVE
    ).values("group_id")
    return (
        Activity.objects.filter(Q(group_id__in=group_ids) | Q(viewers__user=user))
        .select_related("actor", "group")
        .distinct()[:limit]
    )
