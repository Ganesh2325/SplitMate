from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.expenses.models import Expense, ExpensePayer, ExpenseShare
from apps.groups.models import GroupMembership

MONEY = DecimalField(max_digits=12, decimal_places=2)
ZERO = Value(Decimal("0.00"), output_field=MONEY)


def visible_expenses(user):
    group_ids = GroupMembership.objects.filter(
        user=user, status=GroupMembership.Status.ACTIVE
    ).values("group_id")
    return Expense.objects.filter(
        Q(created_by=user) | Q(payers__user=user) | Q(shares__user=user) | Q(group_id__in=group_ids)
    ).distinct()


def categories_for(user, group=None):
    from apps.categories.models import ExpenseCategory

    query = Q(is_system=True) | Q(owner=user)
    if group is not None:
        query |= Q(group=group)
    return ExpenseCategory.objects.filter(query)


def filter_expenses(user, params):
    queryset = visible_expenses(user).select_related("category", "group", "created_by")
    text = (params.get("q") or "").strip()
    if text:
        query = (
            Q(description__icontains=text)
            | Q(notes__icontains=text)
            | Q(category__name__icontains=text)
            | Q(group__name__icontains=text)
            | Q(payers__user__username__icontains=text)
            | Q(payers__user__first_name__icontains=text)
            | Q(shares__user__username__icontains=text)
            | Q(tag_assignments__tag__name__icontains=text)
        )
        try:
            amount = Decimal(text)
        except InvalidOperation:
            amount = None
        if amount is not None:
            query |= Q(amount=amount)
        queryset = queryset.filter(query)
    today = timezone.localdate()
    preset = params.get("preset") or ""
    start = end = None
    if preset == "this_month":
        start = today.replace(day=1)
        end = today
    elif preset == "last_month":
        first = today.replace(day=1)
        end = first - timedelta(days=1)
        start = end.replace(day=1)
    elif preset == "7d":
        start = today - timedelta(days=6)
        end = today
    elif preset == "30d":
        start = today - timedelta(days=29)
        end = today
    elif preset == "this_year":
        start = today.replace(month=1, day=1)
        end = today
    elif preset == "custom":
        start = _parse_date(params.get("date_from"))
        end = _parse_date(params.get("date_to"))
    if start:
        queryset = queryset.filter(expense_date__gte=start)
    if end:
        queryset = queryset.filter(expense_date__lte=end)
    minimum = _parse_amount(params.get("min"))
    maximum = _parse_amount(params.get("max"))
    if minimum is not None:
        queryset = queryset.filter(amount__gte=minimum)
    if maximum is not None:
        queryset = queryset.filter(amount__lte=maximum)
    if params.get("group"):
        queryset = queryset.filter(group_id=params.get("group"))
    if params.get("category"):
        queryset = queryset.filter(category_id=params.get("category"))
    if params.get("friend"):
        friend_id = params.get("friend")
        queryset = queryset.filter(Q(payers__user_id=friend_id) | Q(shares__user_id=friend_id))
    if params.get("paid") == "me":
        queryset = queryset.filter(payers__user=user)
    if params.get("involves") == "me":
        queryset = queryset.filter(Q(payers__user=user) | Q(shares__user=user))
    impact = params.get("impact")
    if impact in {"overpaid", "underpaid", "even"}:
        paid = ExpensePayer.objects.filter(expense=OuterRef("pk"), user=user).values("expense").annotate(
            total=Sum("amount")
        ).values("total")
        share = ExpenseShare.objects.filter(expense=OuterRef("pk"), user=user).values("expense").annotate(
            total=Sum("amount")
        ).values("total")
        queryset = queryset.annotate(
            my_paid=Coalesce(Subquery(paid, output_field=MONEY), ZERO),
            my_share=Coalesce(Subquery(share, output_field=MONEY), ZERO),
        )
        if impact == "overpaid":
            queryset = queryset.filter(my_paid__gt=F("my_share"))
        elif impact == "underpaid":
            queryset = queryset.filter(my_paid__lt=F("my_share"))
        else:
            queryset = queryset.filter(my_paid=F("my_share"))
    if params.get("status") == "void":
        queryset = queryset.filter(status=Expense.Status.VOID)
    elif params.get("status") != "all":
        queryset = queryset.filter(status=Expense.Status.ACTIVE)
    order = {
        "oldest": ("expense_date", "id"),
        "amount_desc": ("-amount", "-id"),
        "amount_asc": ("amount", "id"),
        "updated": ("-updated_at",),
    }.get(params.get("sort") or "newest", ("-expense_date", "-id"))
    return queryset.order_by(*order).distinct()


def _parse_date(value):
    from datetime import datetime

    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_amount(value):
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None
