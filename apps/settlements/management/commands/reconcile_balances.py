from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.common.money import to_minor
from apps.groups.models import Group
from apps.settlements.balances import group_nets


class Command(BaseCommand):
    help = "Check that each group's active balances add up to zero."

    def handle(self, *args, **options):
        problems = 0
        for group in Group.objects.iterator():
            nets = group_nets(group)
            total = sum((amount for amount in nets.values()), Decimal("0"))
            if to_minor(total, group.currency) != 0:
                problems += 1
                self.stdout.write(f"{group.pk} {group.name} {group.currency} sums to {total}")
        if problems:
            self.stderr.write(f"{problems} group(s) do not balance.")
            return
        self.stdout.write(self.style.SUCCESS("Group balances sum to zero."))
