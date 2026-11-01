from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Friendship(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"
        BLOCKED = "blocked", "Blocked"
        REMOVED = "removed", "Removed"

    user_low = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="friendships_as_low"
    )
    user_high = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="friendships_as_high"
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="friend_requests_sent"
    )
    addressee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="friend_requests_received"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    blocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="friendships_blocked",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user_low", "user_high"], name="unique_friendship_pair"),
            models.CheckConstraint(
                condition=Q(user_low_id__lt=F("user_high_id")),
                name="friendship_low_before_high",
            ),
        ]
        indexes = [models.Index(fields=["status"])]

    def other(self, user):
        return self.user_high if user.id == self.user_low_id else self.user_low


class FriendInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    inviter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="friend_invites_sent"
    )
    email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField()
    accepted_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="friend_invites_accepted",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["inviter", "email"],
                condition=Q(status="pending"),
                name="unique_pending_friend_invite",
            )
        ]
        indexes = [models.Index(fields=["email", "status"])]
