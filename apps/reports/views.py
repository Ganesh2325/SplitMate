import json
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.expenses.models import Expense, ExpenseShare
from apps.expenses.selectors import filter_expenses
from apps.groups.access import active_membership
from apps.groups.models import Group, GroupMembership
from apps.notifications.services import feed_for
from apps.reports.exports import export_rows
from apps.reports.services import group_report, personal_report
from apps.settlements.balances import personal_lines, totals_by_currency
from apps.settlements.simplify import simplify_nets


def _range(params, today):
    preset = params.get("preset") or "this_month"
    if preset == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if preset == "this_year":
        return date(today.year, 1, 1), today
    if preset == "custom":
        try:
            start = date.fromisoformat(params.get("date_from"))
            end = date.fromisoformat(params.get("date_to"))
        except (TypeError, ValueError):
            start = today.replace(day=1)
            end = today
        return start, end
    return today.replace(day=1), today


@login_required
def dashboard(request):
    today = timezone.localdate()
    currency = request.user.preferred_currency
    lines = [line for line in personal_lines(request.user) if line.currency == currency]
    totals = totals_by_currency(lines).get(currency, {"owe": Decimal("0"), "owed": Decimal("0"), "net": Decimal("0")})
    month_start = today.replace(day=1)
    my_share = (
        ExpenseShare.objects.filter(
            user=request.user,
            expense__status=Expense.Status.ACTIVE,
            expense__currency=currency,
            expense__expense_date__gte=month_start,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    group_ids = GroupMembership.objects.filter(user=request.user, status=GroupMembership.Status.ACTIVE).values("group_id")
    group_spend = (
        Expense.objects.filter(
            group_id__in=group_ids,
            status=Expense.Status.ACTIVE,
            currency=currency,
            expense_date__gte=month_start,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    recent = (
        filter_expenses(request.user, {"status": "active"})
        .prefetch_related("shares__user", "payers__user")[:6]
    )
    start = (today.replace(day=1) - timedelta(days=150)).replace(day=1)
    monthly = (
        ExpenseShare.objects.filter(
            user=request.user,
            expense__status=Expense.Status.ACTIVE,
            expense__currency=currency,
            expense__expense_date__gte=start,
        )
        .annotate(month=TruncMonth("expense__expense_date"))
        .values("month")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )
    categories = (
        ExpenseShare.objects.filter(
            user=request.user,
            expense__status=Expense.Status.ACTIVE,
            expense__currency=currency,
            expense__expense_date__gte=month_start,
        )
        .values("expense__category__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")[:6]
    )
    chart = {
        "labels": [row["month"].strftime("%b %Y") for row in monthly if row["month"]],
        "values": [float(row["total"]) for row in monthly],
        "categories": [row["expense__category__name"] for row in categories],
        "category_values": [float(row["total"]) for row in categories],
    }
    you_owe = [line for line in lines if line.net < 0]
    you_are_owed = [line for line in lines if line.net > 0]
    return render(
        request,
        "dashboard/home.html",
        {
            "totals": totals,
            "currency": currency,
            "my_share": my_share,
            "group_spend": group_spend,
            "recent": recent,
            "activity": feed_for(request.user, 8),
            "you_owe": you_owe[:6],
            "you_are_owed": you_are_owed[:6],
            "chart": chart,
        },
    )


@login_required
def reports(request):
    today = timezone.localdate()
    start, end = _range(request.GET, today)
    currency = request.GET.get("currency") or request.user.preferred_currency
    group = None
    if request.GET.get("group"):
        group = get_object_or_404(Group, pk=request.GET.get("group"))
        if not active_membership(request.user, group):
            raise Http404()
    personal = None if group else personal_report(request.user, start, end, currency)
    grouped = group_report(group, start, end) if group else None
    chart = {"labels": [], "values": [], "categories": [], "category_values": []}
    source = grouped["by_month"] if grouped else personal["by_month"]
    cats = grouped["by_category"] if grouped else personal["by_category"]
    if source:
        chart["labels"] = [row["month"].strftime("%b %Y") if row["month"] else "" for row in source]
        chart["values"] = [float(row["total"]) for row in source]
    if cats:
        key = "category__name" if grouped else "expense__category__name"
        chart["categories"] = [row[key] for row in cats]
        chart["category_values"] = [float(row["total"]) for row in cats]
    groups = Group.objects.filter(memberships__user=request.user, memberships__status=GroupMembership.Status.ACTIVE)
    return render(
        request,
        "reports/report.html",
        {
            "start": start,
            "end": end,
            "currency": currency,
            "personal": personal,
            "grouped": grouped,
            "group": group,
            "groups": groups,
            "chart": chart,
            "filters": request.GET,
        },
    )


@login_required
def export_report(request, export_format):
    if export_format not in {"csv", "xlsx", "pdf"}:
        raise Http404()
    expenses = list(filter_expenses(request.user, request.GET)[:1000])
    rows = [
        [
            expense.expense_date.isoformat(),
            expense.description,
            expense.group.name if expense.group_id else "",
            expense.category.name,
            expense.currency,
            expense.amount,
            expense.get_status_display(),
        ]
        for expense in expenses
    ]
    return export_rows(request.user, rows, export_format, request.GET.dict())
