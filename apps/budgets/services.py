from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum

from apps.budgets.models import Budget, BudgetAlert
from apps.common.exceptions import DomainError
from apps.common.money import quantize_amount
from apps.expenses.models import Expense, ExpenseShare
from apps.notifications.services import notify

ZERO = Decimal("0")


def period_bounds(budget, today):
    if budget.period == Budget.Period.WEEKLY:
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
    elif budget.period == Budget.Period.YEARLY:
        start = date(today.year, 1, 1)
        end = date(today.year, 12, 31)
    elif budget.period == Budget.Period.CUSTOM:
        start = budget.start_date
        end = budget.end_date or today
    else:
        start = today.replace(day=1)
        end = today.replace(day=monthrange(today.year, today.month)[1])
    if start < budget.start_date:
        start = budget.start_date
    if budget.end_date and end > budget.end_date:
        end = budget.end_date
    return start, end


def budget_spent(budget, today=None):
    from django.utils import timezone

    today = today or timezone.localdate()
    if today < budget.start_date:
        return ZERO
    start, end = period_bounds(budget, today)
    if end < start:
        return ZERO
    if budget.scope == Budget.Scope.GROUP:
        if budget.group_id is None:
            return ZERO
        query = Expense.objects.filter(
            group_id=budget.group_id,
            status=Expense.Status.ACTIVE,
            currency=budget.currency,
            expense_date__range=(start, end),
        )
        if budget.category_id:
            query = query.filter(category_id=budget.category_id)
        return query.aggregate(total=Sum("amount"))["total"] or ZERO
    query = ExpenseShare.objects.filter(
        user=budget.owner,
        expense__status=Expense.Status.ACTIVE,
        expense__currency=budget.currency,
        expense__expense_date__range=(start, end),
    )
    if budget.group_id:
        query = query.filter(expense__group_id=budget.group_id)
    if budget.category_id:
        query = query.filter(expense__category_id=budget.category_id)
    return query.aggregate(total=Sum("amount"))["total"] or ZERO


def budget_progress(budget, today=None):
    spent = budget_spent(budget, today)
    limit_amount = budget.limit_amount or ZERO
    remaining = limit_amount - spent
    percent = Decimal("0")
    if limit_amount > 0:
        percent = (spent / limit_amount * Decimal("100")).quantize(Decimal("0.1"))
    return {"spent": spent, "remaining": remaining, "percent": percent}


def create_budget(*, actor, name, limit_amount, currency, scope, period, start_date, end_date=None, group=None, category=None):
    name = (name or "").strip()
    if not name:
        raise DomainError("Enter a budget name.", field="name")
    limit_amount = quantize_amount(limit_amount, currency)
    if scope == Budget.Scope.GROUP and group is None:
        raise DomainError("Choose a group for a group budget.", field="group")
    if period == Budget.Period.CUSTOM and end_date is None:
        raise DomainError("A custom budget needs an end date.", field="end_date")
    if end_date and end_date < start_date:
        raise DomainError("The end date must be on or after the start date.", field="end_date")
    if group is not None and currency != group.currency:
        raise DomainError("Use the group's currency.", field="currency")
    return Budget.objects.create(
        owner=actor,
        group=group,
        category=category,
        name=name[:80],
        limit_amount=limit_amount,
        currency=currency,
        scope=scope,
        period=period,
        start_date=start_date,
        end_date=end_date,
    )


def check_budgets_for_expense(expense):
    from django.utils import timezone

    today = timezone.localdate()
    participant_ids = set(expense.shares.values_list("user_id", flat=True))
    budgets = Budget.objects.filter(is_active=True, currency=expense.currency, owner_id__in=participant_ids | {expense.created_by_id})
    if expense.group_id:
        budgets = budgets | Budget.objects.filter(is_active=True, currency=expense.currency, group=expense.group, scope=Budget.Scope.GROUP)
    seen = set()
    for budget in budgets.distinct():
        if budget.pk in seen:
            continue
        seen.add(budget.pk)
        if budget.category_id and budget.category_id != expense.category_id:
            continue
        if budget.scope == Budget.Scope.GROUP and budget.group_id != expense.group_id:
            continue
        progress = budget_progress(budget, today)
        percent = progress["percent"]
        threshold = 100 if percent >= 100 else 80 if percent >= 80 else None
        if threshold is None:
            continue
        start, _end = period_bounds(budget, today)
        key = start.isoformat()
        _, created = BudgetAlert.objects.get_or_create(
            budget=budget, period_key=key, threshold=threshold
        )
        if created:
            notify(
                [budget.owner],
                verb="budget_alert",
                message=f"{budget.name} is at {percent}% of its limit.",
                path="/budgets/",
                email_kind="reminder",
            )
