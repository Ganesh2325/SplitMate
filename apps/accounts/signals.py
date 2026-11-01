from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import User, UserNotificationPreference


@receiver(post_save, sender=User)
def create_notification_preferences(sender, instance, created, **kwargs):
    if created:
        UserNotificationPreference.objects.get_or_create(user=instance)
