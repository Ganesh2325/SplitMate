from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.budgets.models import Budget
from apps.budgets.services import budget_progress, create_budget
from apps.categories.models import ExpenseCategory
from apps.common.constants import CURRENCY_CHOICES
from apps.common.exceptions import DomainError
from apps.expenses.selectors import categories_for
from apps.groups.models import GroupMembership


@login_required
def budget_list(request):
    budgets = Budget.objects.filter(owner=request.user).select_related("group", "category")
    rows = [{"budget": budget, "progress": budget_progress(budget)} for budget in budgets]
    return render(request, "budgets/list.html", {"rows": rows})


@login_required
def budget_create(request):
    groups = [
        membership.group
        for membership in GroupMembership.objects.filter(
            user=request.user, status=GroupMembership.Status.ACTIVE
        ).select_related("group")
    ]
    if request.method == "POST":
        group = None
        if request.POST.get("group"):
            group = next((item for item in groups if str(item.id) == request.POST.get("group")), None)
        category = None
        if request.POST.get("category"):
            category = ExpenseCategory.objects.filter(pk=request.POST.get("category")).first()
        try:
            create_budget(
                actor=request.user,
                name=request.POST.get("name", ""),
                limit_amount=request.POST.get("limit_amount") or "0",
                currency=group.currency if group and request.POST.get("scope") == "group" else request.POST.get("currency") or "INR",
                scope=request.POST.get("scope") or "personal",
                period=request.POST.get("period") or "monthly",
                start_date=date.fromisoformat(request.POST.get("start_date")),
                end_date=date.fromisoformat(request.POST.get("end_date")) if request.POST.get("end_date") else None,
                group=group,
                category=category,
            )
            messages.success(request, "Budget saved. Personal budgets track your shares. Group budgets track each expense once.")
            return redirect("budgets:list")
        except (DomainError, ValueError) as exc:
            messages.error(request, str(exc))
    return render(
        request,
        "budgets/form.html",
        {
            "groups": groups,
            "categories": categories_for(request.user),
            "currencies": CURRENCY_CHOICES,
            "today": date.today(),
        },
    )


@login_required
@require_POST
def budget_toggle(request, pk):
    budget = get_object_or_404(Budget, pk=pk, owner=request.user)
    budget.is_active = not budget.is_active
    budget.save(update_fields=["is_active"])
    return redirect("budgets:list")
