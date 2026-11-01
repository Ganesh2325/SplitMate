from datetime import date
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from apps.categories.models import ExpenseCategory
from apps.common.factories import make_user
from apps.expenses.models import Expense
from apps.recurring.services import create_recurring, process_due_recurring


class RecurringTests(TestCase):
    def test_processing_twice_creates_one_expense(self):
        owner = make_user("ganesh")
        category = ExpenseCategory.objects.get(slug="rent")
        create_recurring(
            actor=owner,
            description="Rent",
            amount=Decimal("1200.00"),
            currency="INR",
            frequency="monthly",
            start_date=date(2026, 11, 1),
            category=category,
            split_method="equal",
            payload={"participant_ids": [owner.id], "payers": {str(owner.id): "1200.00"}},
        )
        self.assertEqual(process_due_recurring(today=date(2026, 11, 1)), 1)
        self.assertEqual(process_due_recurring(today=date(2026, 11, 1)), 0)
        call_command("process_recurring_expenses")
        self.assertEqual(Expense.objects.filter(description="Rent").count(), 1)
