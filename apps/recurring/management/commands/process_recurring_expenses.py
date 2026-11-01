from django.core.management.base import BaseCommand

from apps.recurring.services import process_due_recurring


class Command(BaseCommand):
    help = "Create expenses for recurring schedules that are due. Safe to run more than once."

    def handle(self, *args, **options):
        created = process_due_recurring()
        self.stdout.write(self.style.SUCCESS(f"Generated {created} expense(s)."))
