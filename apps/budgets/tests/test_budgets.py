import uuid
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.budgets.services import budget_progress, create_budget
from apps.categories.models import ExpenseCategory
from apps.common.factories import make_user
from apps.expenses.services import create_expense


class BudgetTests(TestCase):
    def test_personal_budget_uses_shares(self):
        user = make_user("ganesh")
        category = ExpenseCategory.objects.get(slug="groceries")
        budget = create_budget(
            actor=user,
            name="Groceries",
            limit_amount="8000",
            currency="INR",
            scope="personal",
            period="monthly",
            start_date=date(2026, 11, 1),
            category=category,
        )
        create_expense(
            actor=user,
            description="Market",
            amount="6000",
            currency="INR",
            expense_date=date(2026, 11, 2),
            split_method="equal",
            participant_ids=[user.id],
            payers={user.id: "6000"},
            category=category,
            client_token=uuid.uuid4(),
        )
        progress = budget_progress(budget, today=date(2026, 11, 15))
        self.assertEqual(progress["spent"], Decimal("6000.00"))
        self.assertEqual(progress["remaining"], Decimal("2000.00"))
        self.assertEqual(progress["percent"], Decimal("75.0"))
