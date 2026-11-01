from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import LoginAttempt


class Command(BaseCommand):
    help = "Delete login attempts older than 30 days."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=30)
        deleted, _details = LoginAttempt.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Removed {deleted} login attempt row(s)."))
