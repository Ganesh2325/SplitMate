from django.conf import settings
from django.db import models


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notifications_sent",
    )
    verb = models.CharField(max_length=40)
    message = models.CharField(max_length=255)
    path = models.CharField(max_length=255, blank=True)
    email_kind = models.CharField(max_length=20, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["recipient", "read_at", "created_at"])]
        ordering = ["-created_at"]

    @property
    def is_read(self):
        return self.read_at is not None


class Activity(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="activities"
    )
    verb = models.CharField(max_length=40)
    summary = models.CharField(max_length=255)
    group = models.ForeignKey(
        "groups.Group", null=True, blank=True, on_delete=models.SET_NULL, related_name="activities"
    )
    path = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["group", "created_at"]), models.Index(fields=["created_at"])]
        ordering = ["-created_at"]


class ActivityViewer(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="viewers")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activity_views"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["activity", "user"], name="unique_activity_viewer"),
        ]
