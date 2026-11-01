import uuid
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.categories.models import ExpenseCategory
from apps.common.factories import make_user
from apps.expenses.models import Expense
from apps.expenses.services import create_expense, update_expense, void_expense
from apps.groups.services import accept_group_invite, create_group, invite_to_group
from apps.settlements.balances import active_effect, explain_group, group_nets, personal_lines, totals_by_currency
from apps.settlements.models import Settlement
from apps.settlements.services import record_settlement, reverse_settlement
from apps.settlements.simplify import simplify_nets, suggestions_match_nets


class WeekendTripTests(TestCase):
    def setUp(self):
        self.ganesh = make_user("ganesh")
        self.rahul = make_user("rahul")
        self.priya = make_user("priya")
        self.arjun = make_user("arjun")
        self.users = [self.ganesh, self.rahul, self.priya, self.arjun]
        self.group = create_group(actor=self.ganesh, name="Weekend Trip", group_type="trip", currency="INR")
        for user in self.users[1:]:
            invite = invite_to_group(actor=self.ganesh, group=self.group, user=user)
            accept_group_invite(user, invite)
        self.category = ExpenseCategory.objects.get(slug="miscellaneous")

    def _add(self, actor, description, amount):
        return create_expense(
            actor=actor,
            description=description,
            amount=Decimal(amount),
            currency="INR",
            expense_date=date(2026, 10, 1),
            split_method="equal",
            participant_ids=[user.id for user in self.users],
            payers={actor.id: Decimal(amount)},
            category=self.category,
            client_token=uuid.uuid4(),
            group=self.group,
        )

    def _seed(self):
        self._add(self.ganesh, "Hotel", "4000.00")
        self._add(self.rahul, "Food", "2000.00")
        self._add(self.priya, "Transport", "1000.00")
        self._add(self.arjun, "Tickets", "1000.00")

    def test_balances_simplify_and_settle_to_zero(self):
        self._seed()
        expenses = Expense.objects.filter(group=self.group, status=Expense.Status.ACTIVE)
        self.assertEqual(sum(expense.amount for expense in expenses), Decimal("8000.00"))
        self.assertEqual(sum(row.amount for expense in expenses for row in expense.payers.all()), Decimal("8000.00"))
        self.assertEqual(sum(row.amount for expense in expenses for row in expense.shares.all()), Decimal("8000.00"))
        nets = group_nets(self.group)
        self.assertEqual(nets[self.ganesh.id], Decimal("2000.00"))
        self.assertEqual(nets[self.rahul.id], Decimal("0.00"))
        self.assertEqual(nets[self.priya.id], Decimal("-1000.00"))
        self.assertEqual(nets[self.arjun.id], Decimal("-1000.00"))
        self.assertEqual(sum(nets.values(), Decimal("0")), Decimal("0"))
        self.assertEqual(active_effect(explain_group(self.group, self.ganesh)), nets[self.ganesh.id])
        self.assertEqual(active_effect(explain_group(self.group, self.priya)), nets[self.priya.id])
        suggestions = simplify_nets(nets, "INR", self.group.id)
        self.assertTrue(suggestions_match_nets(nets, suggestions, "INR"))
        for suggestion in suggestions:
            record_settlement(
                actor=self.users[0].__class__.objects.get(pk=suggestion.debtor_id),
                payer=self.users[0].__class__.objects.get(pk=suggestion.debtor_id),
                recipient=self.users[0].__class__.objects.get(pk=suggestion.creditor_id),
                amount=suggestion.amount,
                currency="INR",
                settled_on=date(2026, 10, 2),
                group=self.group,
                client_token=uuid.uuid4(),
            )
        settled = group_nets(self.group)
        self.assertTrue(all(value == 0 for value in settled.values()))

    def test_edit_void_and_reversal_recalculate(self):
        hotel = self._add(self.ganesh, "Hotel", "4000.00")
        food = self._add(self.rahul, "Food", "2000.00")
        self._add(self.priya, "Transport", "1000.00")
        self._add(self.arjun, "Tickets", "1000.00")
        update_expense(
            hotel,
            actor=self.ganesh,
            reason="Shorter stay",
            description="Hotel",
            amount=Decimal("2000.00"),
            expense_date=date(2026, 10, 1),
            split_method="equal",
            participant_ids=[user.id for user in self.users],
            payers={self.ganesh.id: Decimal("2000.00")},
            category=self.category,
        )
        hotel.refresh_from_db()
        self.assertEqual(hotel.amount, Decimal("2000.00"))
        self.assertEqual(hotel.revisions.count(), 2)
        nets = group_nets(self.group)
        self.assertEqual(nets[self.ganesh.id], Decimal("500.00"))
        self.assertEqual(nets[self.rahul.id], Decimal("500.00"))
        self.assertEqual(nets[self.priya.id], Decimal("-500.00"))
        self.assertEqual(sum(nets.values(), Decimal("0")), Decimal("0"))
        void_expense(food, actor=self.rahul, reason="Charged in error")
        food.refresh_from_db()
        self.assertEqual(food.status, Expense.Status.VOID)
        self.assertTrue(Expense.objects.filter(pk=food.pk).exists())
        nets = group_nets(self.group)
        self.assertEqual(nets[self.rahul.id], Decimal("-1000.00"))
        self.assertEqual(sum(nets.values(), Decimal("0")), Decimal("0"))
        suggestions = simplify_nets(nets, "INR")
        first = suggestions[0]
        settlement = record_settlement(
            actor=self.users[0].__class__.objects.get(pk=first.debtor_id),
            payer=self.users[0].__class__.objects.get(pk=first.debtor_id),
            recipient=self.users[0].__class__.objects.get(pk=first.creditor_id),
            amount=first.amount,
            currency="INR",
            settled_on=date(2026, 10, 3),
            group=self.group,
            client_token=uuid.uuid4(),
        )
        before = group_nets(self.group)
        reverse_settlement(settlement, actor=settlement.payer, reason="Wrong person")
        after = group_nets(self.group)
        self.assertEqual(before[settlement.payer_id] - first.amount, after[settlement.payer_id])
        self.assertEqual(before[settlement.recipient_id] + first.amount, after[settlement.recipient_id])
        self.assertEqual(sum(after.values(), Decimal("0")), Decimal("0"))

    def test_duplicate_settlement_token_is_idempotent(self):
        self._seed()
        token = uuid.uuid4()
        kwargs = dict(
            actor=self.priya,
            payer=self.priya,
            recipient=self.ganesh,
            amount=Decimal("1000.00"),
            currency="INR",
            settled_on=date(2026, 10, 2),
            group=self.group,
            client_token=token,
        )
        first = record_settlement(**kwargs)
        second = record_settlement(**kwargs)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Settlement.objects.filter(group=self.group).count(), 1)
        self.assertEqual(group_nets(self.group)[self.priya.id], Decimal("0.00"))

    def test_multiple_payers_percentage_and_separate_currencies(self):
        outsider = make_user("meera")
        invite = invite_to_group(actor=self.ganesh, group=self.group, user=outsider)
        accept_group_invite(outsider, invite)
        create_expense(
            actor=self.ganesh,
            description="Mixed bill",
            amount=Decimal("1500.00"),
            currency="INR",
            expense_date=date(2026, 10, 4),
            split_method="equal",
            participant_ids=[self.ganesh.id, self.rahul.id, self.priya.id],
            payers={self.ganesh.id: Decimal("900.00"), self.rahul.id: Decimal("600.00")},
            category=self.category,
            client_token=uuid.uuid4(),
            group=self.group,
        )
        nets = group_nets(self.group)
        self.assertEqual(nets[self.ganesh.id], Decimal("400.00"))
        self.assertEqual(nets[self.rahul.id], Decimal("100.00"))
        self.assertEqual(nets[self.priya.id], Decimal("-500.00"))
        create_expense(
            actor=self.ganesh,
            description="Uneven dinner",
            amount=Decimal("1000.00"),
            currency="INR",
            expense_date=date(2026, 10, 5),
            split_method="percent",
            participant_ids=[self.ganesh.id, self.rahul.id],
            payers={self.ganesh.id: Decimal("1000.00")},
            percentages={self.ganesh.id: Decimal("25"), self.rahul.id: Decimal("75")},
            category=self.category,
            client_token=uuid.uuid4(),
            group=self.group,
        )
        usd = create_group(actor=self.ganesh, name="US trip", group_type="trip", currency="USD")
        invite = invite_to_group(actor=self.ganesh, group=usd, user=self.rahul)
        accept_group_invite(self.rahul, invite)
        create_expense(
            actor=self.ganesh,
            description="Museum",
            amount=Decimal("40.00"),
            currency="USD",
            expense_date=date(2026, 10, 6),
            split_method="exact",
            participant_ids=[self.ganesh.id, self.rahul.id],
            payers={self.ganesh.id: Decimal("40.00")},
            exact={self.ganesh.id: Decimal("10.00"), self.rahul.id: Decimal("30.00")},
            category=self.category,
            client_token=uuid.uuid4(),
            group=usd,
        )
        self.assertEqual(group_nets(usd)[self.ganesh.id], Decimal("30.00"))
        self.assertEqual(group_nets(self.group, "INR")[self.ganesh.id], Decimal("1150.00"))
        totals = totals_by_currency(personal_lines(self.ganesh))
        self.assertIn("INR", totals)
        self.assertIn("USD", totals)
        self.assertNotEqual(totals["INR"]["net"], totals["USD"]["net"])
