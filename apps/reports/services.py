from decimal import Decimal

from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncMonth

from apps.expenses.models import Expense, ExpensePayer, ExpenseShare
from apps.settlements.models import Settlement

ZERO = Decimal("0")


def personal_report(user, start, end, currency):
    shares = ExpenseShare.objects.filter(
        user=user,
        expense__status=Expense.Status.ACTIVE,
        expense__currency=currency,
        expense__expense_date__range=(start, end),
    )
    paid = ExpensePayer.objects.filter(
        user=user,
        expense__status=Expense.Status.ACTIVE,
        expense__currency=currency,
        expense__expense_date__range=(start, end),
    )
    total_share = shares.aggregate(total=Sum("amount"))["total"] or ZERO
    total_paid = paid.aggregate(total=Sum("amount"))["total"] or ZERO
    count = shares.values("expense_id").distinct().count()
    average = (total_share / count) if count else ZERO
    by_category = list(
        shares.values("expense__category__name").annotate(total=Sum("amount")).order_by("-total")
    )
    by_month = list(
        shares.annotate(month=TruncMonth("expense__expense_date")).values("month").annotate(total=Sum("amount")).order_by("month")
    )
    largest = list(
        shares.select_related("expense").order_by("-amount")[:5]
    )
    settlements = Settlement.objects.filter(status=Settlement.Status.RECORDED, currency=currency, settled_on__range=(start, end)).filter(
        payer=user
    ) | Settlement.objects.filter(status=Settlement.Status.RECORDED, currency=currency, settled_on__range=(start, end)).filter(
        recipient=user
    )
    return {
        "total_share": total_share,
        "total_paid": total_paid,
        "count": count,
        "average": average,
        "by_category": by_category,
        "by_month": by_month,
        "largest": largest,
        "settlements": settlements.distinct().select_related("payer", "recipient"),
    }


def group_report(group, start, end):
    expenses = Expense.objects.filter(
        group=group, status=Expense.Status.ACTIVE, expense_date__range=(start, end), currency=group.currency
    )
    total = expenses.aggregate(total=Sum("amount"), count=Count("id"), average=Avg("amount"))
    by_category = list(expenses.values("category__name").annotate(total=Sum("amount")).order_by("-total"))
    by_month = list(
        expenses.annotate(month=TruncMonth("expense_date")).values("month").annotate(total=Sum("amount")).order_by("month")
    )
    by_member = list(
        ExpenseShare.objects.filter(expense__in=expenses).values("user__username", "user__first_name").annotate(total=Sum("amount")).order_by("-total")
    )
    contributions = list(
        ExpensePayer.objects.filter(expense__in=expenses).values("user__username", "user__first_name").annotate(total=Sum("amount")).order_by("-total")
    )
    return {
        "total": total["total"] or ZERO,
        "count": total["count"] or 0,
        "average": total["average"] or ZERO,
        "by_category": by_category,
        "by_month": by_month,
        "by_member": by_member,
        "contributions": contributions,
    }
