"""Authoritative balances.

Positive means that person should receive money. Negative means they owe money.
Nothing in this module trusts a figure supplied by the browser.

Settlement signs follow the worked weekend-trip example: the payer's net moves
up (a debt is reduced) and the recipient's net moves down (they are owed less).

    net = expense payments - expense shares + repayments made - repayments received

Group expenses stay inside the group. Non-group expenses and loans stay on the
personal balance. The two are added only when a page is explicitly showing a
combined total, and they are still listed separately.
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from apps.common.allocations import net_directions, obligations_from_parts, pair_effect
from apps.expenses.models import Expense, ExpensePayer, ExpenseShare
from apps.groups.models import GroupMembership
from apps.settlements.models import InformalDebt, Settlement

ZERO = Decimal("0")
MONEY = DecimalField(max_digits=12, decimal_places=2)
ZERO_VALUE = Value(Decimal("0.00"), output_field=MONEY)


@dataclass
class ScopeLine:
    currency: str
    net: Decimal
    kind: str
    label: str
    group_id: int | None = None
    other_id: int | None = None


def group_nets(group, currency=None):
    currency = currency or group.currency
    paid = {
        row["user_id"]: row["total"]
        for row in ExpensePayer.objects.filter(
            expense__group=group,
            expense__status=Expense.Status.ACTIVE,
            expense__currency=currency,
        )
        .values("user_id")
        .annotate(total=Sum("amount"))
    }
    shared = {
        row["user_id"]: row["total"]
        for row in ExpenseShare.objects.filter(
            expense__group=group,
            expense__status=Expense.Status.ACTIVE,
            expense__currency=currency,
        )
        .values("user_id")
        .annotate(total=Sum("amount"))
    }
    made = {
        row["payer_id"]: row["total"]
        for row in Settlement.objects.filter(
            group=group, currency=currency, status=Settlement.Status.RECORDED
        )
        .values("payer_id")
        .annotate(total=Sum("amount"))
    }
    received = {
        row["recipient_id"]: row["total"]
        for row in Settlement.objects.filter(
            group=group, currency=currency, status=Settlement.Status.RECORDED
        )
        .values("recipient_id")
        .annotate(total=Sum("amount"))
    }
    member_ids = set(
        GroupMembership.objects.filter(group=group, status=GroupMembership.Status.ACTIVE).values_list(
            "user_id", flat=True
        )
    )
    everyone = set(paid) | set(shared) | set(made) | set(received) | member_ids
    return {
        user_id: paid.get(user_id, ZERO)
        - shared.get(user_id, ZERO)
        + made.get(user_id, ZERO)
        - received.get(user_id, ZERO)
        for user_id in everyone
    }


def group_pairwise(group, currency=None):
    """Direct remaining debts inside one group, after recorded repayments."""
    currency = currency or group.currency
    bucket = defaultdict(lambda: ZERO)
    expenses = Expense.objects.filter(
        group=group, status=Expense.Status.ACTIVE, currency=currency
    ).prefetch_related("payers", "shares")
    for expense in expenses:
        payers = {row.user_id: row.amount for row in expense.payers.all()}
        shares = {row.user_id: row.amount for row in expense.shares.all()}
        for key, amount in obligations_from_parts(payers, shares, currency).items():
            bucket[key] += amount
    for settlement in Settlement.objects.filter(
        group=group, currency=currency, status=Settlement.Status.RECORDED
    ):
        bucket[(settlement.payer_id, settlement.recipient_id)] -= settlement.amount
    return net_directions(bucket)


def person_expense_map(user):
    """Non-group expense and repayment balances. Positive: the other person owes the user."""
    result = defaultdict(lambda: defaultdict(lambda: ZERO))
    expenses = (
        Expense.objects.filter(group__isnull=True, status=Expense.Status.ACTIVE)
        .filter(Q(payers__user=user) | Q(shares__user=user))
        .distinct()
        .prefetch_related("payers", "shares")
    )
    for expense in expenses:
        payers = {row.user_id: row.amount for row in expense.payers.all()}
        shares = {row.user_id: row.amount for row in expense.shares.all()}
        obligations = obligations_from_parts(payers, shares, expense.currency)
        others = (set(payers) | set(shares)) - {user.id}
        for other_id in others:
            result[expense.currency][other_id] += pair_effect(obligations, user.id, other_id)
    settlements = Settlement.objects.filter(group__isnull=True, status=Settlement.Status.RECORDED).filter(
        Q(payer=user) | Q(recipient=user)
    )
    for settlement in settlements:
        other_id = settlement.recipient_id if settlement.payer_id == user.id else settlement.payer_id
        if settlement.payer_id == user.id:
            result[settlement.currency][other_id] += settlement.amount
        else:
            result[settlement.currency][other_id] -= settlement.amount
    return result


def person_debt_map(user):
    """Informal loans only. Positive: the other person still owes the user."""
    result = defaultdict(lambda: defaultdict(lambda: ZERO))
    debts = (
        InformalDebt.objects.exclude(status=InformalDebt.Status.VOID)
        .filter(Q(creditor=user) | Q(debtor=user))
        .annotate(
            paid=Coalesce(
                Sum("repayments__amount", filter=Q(repayments__status="recorded")),
                ZERO_VALUE,
            )
        )
    )
    for debt in debts:
        outstanding = debt.amount - debt.paid
        if outstanding == 0:
            continue
        if debt.creditor_id == user.id:
            result[debt.currency][debt.debtor_id] += outstanding
        else:
            result[debt.currency][debt.creditor_id] -= outstanding
    return result


def user_group_nets(user):
    paid = defaultdict(lambda: ZERO)
    shared = defaultdict(lambda: ZERO)
    made = defaultdict(lambda: ZERO)
    received = defaultdict(lambda: ZERO)
    for row in (
        ExpensePayer.objects.filter(user=user, expense__status=Expense.Status.ACTIVE, expense__group__isnull=False)
        .values("expense__group_id", "expense__currency")
        .annotate(total=Sum("amount"))
    ):
        paid[(row["expense__group_id"], row["expense__currency"])] = row["total"]
    for row in (
        ExpenseShare.objects.filter(user=user, expense__status=Expense.Status.ACTIVE, expense__group__isnull=False)
        .values("expense__group_id", "expense__currency")
        .annotate(total=Sum("amount"))
    ):
        shared[(row["expense__group_id"], row["expense__currency"])] = row["total"]
    for row in (
        Settlement.objects.filter(payer=user, group__isnull=False, status=Settlement.Status.RECORDED)
        .values("group_id", "currency")
        .annotate(total=Sum("amount"))
    ):
        made[(row["group_id"], row["currency"])] = row["total"]
    for row in (
        Settlement.objects.filter(recipient=user, group__isnull=False, status=Settlement.Status.RECORDED)
        .values("group_id", "currency")
        .annotate(total=Sum("amount"))
    ):
        received[(row["group_id"], row["currency"])] = row["total"]
    keys = set(paid) | set(shared) | set(made) | set(received)
    for membership in GroupMembership.objects.filter(user=user, status=GroupMembership.Status.ACTIVE).select_related(
        "group"
    ):
        keys.add((membership.group_id, membership.group.currency))
    rows = []
    for group_id, currency in sorted(keys, key=lambda item: (item[0], item[1])):
        net = paid[(group_id, currency)] - shared[(group_id, currency)] + made[(group_id, currency)] - received[(group_id, currency)]
        rows.append({"group_id": group_id, "currency": currency, "net": net})
    return rows


def personal_lines(user, users_by_id=None, groups_by_id=None):
    from apps.accounts.models import User
    from apps.groups.models import Group

    group_rows = user_group_nets(user)
    expense_map = person_expense_map(user)
    debt_map = person_debt_map(user)
    group_ids = [row["group_id"] for row in group_rows]
    other_ids = set()
    for mapping in (expense_map, debt_map):
        for people in mapping.values():
            other_ids.update(people)
    if groups_by_id is None:
        groups_by_id = Group.objects.in_bulk(group_ids)
    if users_by_id is None:
        users_by_id = User.objects.in_bulk(other_ids)
    lines = []
    for row in group_rows:
        group = groups_by_id.get(row["group_id"])
        lines.append(
            ScopeLine(
                currency=row["currency"],
                net=row["net"],
                kind="group",
                label=group.name if group else "Group",
                group_id=row["group_id"],
            )
        )
    for currency, people in expense_map.items():
        for other_id, net in people.items():
            if net == 0:
                continue
            other = users_by_id.get(other_id)
            lines.append(
                ScopeLine(
                    currency=currency,
                    net=net,
                    kind="person",
                    label=other.display_name if other else "Person",
                    other_id=other_id,
                )
            )
    for currency, people in debt_map.items():
        for other_id, net in people.items():
            if net == 0:
                continue
            other = users_by_id.get(other_id)
            lines.append(
                ScopeLine(
                    currency=currency,
                    net=net,
                    kind="loan",
                    label=other.display_name if other else "Person",
                    other_id=other_id,
                )
            )
    return lines


def totals_by_currency(lines):
    buckets = defaultdict(lambda: {"owe": ZERO, "owed": ZERO, "net": ZERO})
    for line in lines:
        bucket = buckets[line.currency]
        bucket["net"] += line.net
        if line.net > 0:
            bucket["owed"] += line.net
        elif line.net < 0:
            bucket["owe"] += -line.net
    return dict(buckets)


def explain_group(group, user, currency=None):
    currency = currency or group.currency
    lines = []
    expenses = (
        Expense.objects.filter(group=group, currency=currency)
        .prefetch_related("payers", "shares")
        .order_by("expense_date", "id")
    )
    for expense in expenses:
        paid = sum((row.amount for row in expense.payers.all() if row.user_id == user.id), ZERO)
        share = sum((row.amount for row in expense.shares.all() if row.user_id == user.id), ZERO)
        involved = paid != 0 or share != 0
        if expense.status != Expense.Status.ACTIVE and not involved:
            continue
        effect = paid - share if expense.status == Expense.Status.ACTIVE else ZERO
        if not involved and effect == 0:
            continue
        lines.append(
            {
                "date": expense.expense_date,
                "kind": "expense",
                "label": expense.description,
                "effect": effect,
                "path": f"/expenses/{expense.pk}/",
                "void": expense.status != Expense.Status.ACTIVE,
            }
        )
    for settlement in Settlement.objects.filter(group=group, currency=currency).filter(
        Q(payer=user) | Q(recipient=user)
    ).select_related("payer", "recipient").order_by("settled_on", "id"):
        if settlement.status != Settlement.Status.RECORDED:
            effect = ZERO
            void = True
        elif settlement.payer_id == user.id:
            effect = settlement.amount
            void = False
        else:
            effect = -settlement.amount
            void = False
        other = settlement.recipient if settlement.payer_id == user.id else settlement.payer
        lines.append(
            {
                "date": settlement.settled_on,
                "kind": "settlement",
                "label": f"Repayment with {other.display_name}",
                "effect": effect,
                "path": f"/settlements/{settlement.pk}/",
                "void": void,
            }
        )
    return lines


def explain_person(user, other, currency):
    lines = []
    expenses = (
        Expense.objects.filter(group__isnull=True, currency=currency, status=Expense.Status.ACTIVE)
        .filter(Q(payers__user=user) | Q(shares__user=user))
        .filter(Q(payers__user=other) | Q(shares__user=other))
        .distinct()
        .prefetch_related("payers", "shares")
        .order_by("expense_date", "id")
    )
    for expense in expenses:
        payers = {row.user_id: row.amount for row in expense.payers.all()}
        shares = {row.user_id: row.amount for row in expense.shares.all()}
        effect = pair_effect(obligations_from_parts(payers, shares, currency), user.id, other.id)
        if effect == 0:
            continue
        lines.append(
            {
                "date": expense.expense_date,
                "kind": "expense",
                "label": expense.description,
                "effect": effect,
                "path": f"/expenses/{expense.pk}/",
                "void": False,
            }
        )
    for settlement in Settlement.objects.filter(
        group__isnull=True, currency=currency, status=Settlement.Status.RECORDED
    ).filter(
        Q(payer=user, recipient=other) | Q(payer=other, recipient=user)
    ).order_by("settled_on", "id"):
        effect = settlement.amount if settlement.payer_id == user.id else -settlement.amount
        lines.append(
            {
                "date": settlement.settled_on,
                "kind": "settlement",
                "label": "Repayment",
                "effect": effect,
                "path": f"/settlements/{settlement.pk}/",
                "void": False,
            }
        )
    debts = (
        InformalDebt.objects.exclude(status=InformalDebt.Status.VOID)
        .filter(currency=currency)
        .filter(Q(creditor=user, debtor=other) | Q(creditor=other, debtor=user))
        .prefetch_related("repayments")
    )
    for debt in debts:
        sign = Decimal("1") if debt.creditor_id == user.id else Decimal("-1")
        lines.append(
            {
                "date": debt.borrowed_on,
                "kind": "loan",
                "label": "Informal loan",
                "effect": sign * debt.amount,
                "path": f"/debts/{debt.pk}/",
                "void": False,
            }
        )
        for repayment in debt.repayments.all():
            if repayment.status != "recorded":
                continue
            lines.append(
                {
                    "date": repayment.paid_on,
                    "kind": "loan_payment",
                    "label": "Loan repayment",
                    "effect": -sign * repayment.amount,
                    "path": f"/debts/{debt.pk}/",
                    "void": False,
                }
            )
    return lines


def active_effect(lines):
    return sum((line["effect"] for line in lines if not line["void"]), ZERO)
