from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.constants import CURRENCY_CHOICES, GROUP_ROLES, GROUP_TYPES, MEMBERSHIP_STATUSES, SPLIT_METHODS


class Group(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="group_images/", blank=True)
    group_type = models.CharField(max_length=16, choices=GROUP_TYPES, default="other")
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="INR")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_groups"
    )
    simplify_debts = models.BooleanField(default=True)
    default_split_method = models.CharField(max_length=16, choices=SPLIT_METHODS, default="equal")
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["archived_at", "name"])]

    def __str__(self):
        return self.name

    @property
    def is_archived(self):
        return self.archived_at is not None


class GroupMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        VIEWER = "viewer", "Read-only"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        LEFT = "left", "Left"
        REMOVED = "removed", "Removed"

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships"
    )
    role = models.CharField(max_length=16, choices=GROUP_ROLES, default=Role.MEMBER)
    status = models.CharField(max_length=16, choices=MEMBERSHIP_STATUSES, default=Status.ACTIVE)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="memberships_added",
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["group", "user"], name="unique_group_member"),
        ]
        indexes = [models.Index(fields=["user", "status"])]


class GroupMembershipEvent(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="membership_events")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="membership_events"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="membership_actions"
    )
    action = models.CharField(max_length=32)
    from_role = models.CharField(max_length=16, blank=True)
    to_role = models.CharField(max_length=16, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["group", "created_at"])]


class GroupInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="invitations")
    inviter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="group_invites_sent"
    )
    invitee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="group_invites_received",
    )
    email = models.EmailField(blank=True)
    token_hash = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField()
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["group", "invitee"],
                condition=Q(status="pending", invitee__isnull=False),
                name="unique_pending_group_invitee",
            ),
            models.UniqueConstraint(
                fields=["group", "email"],
                condition=Q(status="pending") & ~Q(email=""),
                name="unique_pending_group_email",
            ),
        ]
        indexes = [models.Index(fields=["status", "expires_at"])]
