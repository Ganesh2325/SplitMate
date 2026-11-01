from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.settlements.balances import personal_lines


class Command(BaseCommand):
    help = "Notify people who currently owe money. Skips anyone already reminded today."

    def handle(self, *args, **options):
        today = timezone.localdate()
        sent = 0
        for user in User.objects.filter(is_active=True, anonymized_at__isnull=True).iterator():
            owed = [line for line in personal_lines(user) if line.net < 0]
            if not owed:
                continue
            already = Notification.objects.filter(
                recipient=user, verb="repayment_reminder", created_at__date=today
            ).exists()
            if already:
                continue
            notify(
                [user],
                verb="repayment_reminder",
                message="You have outstanding balances. Open Balances to see who to pay.",
                path="/balances/",
                email_kind="reminder",
            )
            sent += 1
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} reminder(s)."))
