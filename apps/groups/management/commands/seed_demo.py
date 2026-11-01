import uuid
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.categories.models import ExpenseCategory
from apps.expenses.models import Expense
from apps.expenses.services import create_expense
from apps.groups.models import Group
from apps.groups.services import accept_group_invite, create_group, invite_to_group


PEOPLE = (
    ("ganesh", "Ganesh", "Rao"),
    ("rahul", "Rahul", "Mehta"),
    ("priya", "Priya", "Nair"),
    ("arjun", "Arjun", "Shah"),
)


class Command(BaseCommand):
    help = "Create the Weekend Trip example. Refuses to run when DEBUG is off."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            self.stderr.write("Refusing to load demo data while DEBUG is off.")
            return
        users = {}
        for username, first, last in PEOPLE:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@example.com",
                    "first_name": first,
                    "last_name": last,
                    "preferred_currency": "INR",
                },
            )
            if created:
                user.set_password("ValidPass123")
                user.save()
            users[username] = user
        owner = users["ganesh"]
        group = Group.objects.filter(name="Weekend Trip", created_by=owner).first()
        if group is None:
            group = create_group(
                actor=owner,
                name="Weekend Trip",
                group_type="trip",
                currency="INR",
                description="A shared trip used to check balances.",
            )
            for username in ("rahul", "priya", "arjun"):
                invite = invite_to_group(actor=owner, group=group, user=users[username])
                accept_group_invite(users[username], invite)
        if group.expenses.exists():
            self.stdout.write("Weekend Trip already has expenses. Left them in place.")
            return
        food = ExpenseCategory.objects.get(slug="food-and-dining")
        stay = ExpenseCategory.objects.get(slug="accommodation")
        travel = ExpenseCategory.objects.get(slug="transportation")
        events = ExpenseCategory.objects.get(slug="events")
        members = [users[name] for name, _first, _last in PEOPLE]
        rows = (
            ("Hotel", Decimal("4000.00"), owner, stay),
            ("Food", Decimal("2000.00"), users["rahul"], food),
            ("Transport", Decimal("1000.00"), users["priya"], travel),
            ("Tickets", Decimal("1000.00"), users["arjun"], events),
        )
        for description, amount, payer, category in rows:
            create_expense(
                actor=payer,
                description=description,
                amount=amount,
                currency="INR",
                expense_date=date(2026, 10, 18),
                split_method="equal",
                participant_ids=[person.id for person in members],
                payers={payer.id: amount},
                category=category,
                group=group,
                client_token=uuid.uuid5(uuid.NAMESPACE_URL, f"splitmate:demo:{description.lower()}"),
            )
        self.stdout.write(self.style.SUCCESS("Weekend Trip is ready. Log in as ganesh / ValidPass123."))
        self.stdout.write(f"Expenses: {Expense.objects.filter(group=group).count()}")
