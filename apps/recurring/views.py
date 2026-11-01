import uuid
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.common.constants import FREQUENCIES
from apps.common.exceptions import DomainError
from apps.expenses.selectors import categories_for
from apps.friends.services import friend_ids
from apps.groups.models import GroupMembership
from apps.recurring.models import RecurringExpense
from apps.recurring.services import create_recurring


def _people(user, group):
    if group is not None:
        ids = GroupMembership.objects.filter(group=group, status=GroupMembership.Status.ACTIVE).values_list(
            "user_id", flat=True
        )
    else:
        ids = set(friend_ids(user)) | {user.id}
    return list(User.objects.filter(pk__in=ids, is_active=True).order_by("first_name", "username"))


@login_required
def recurring_list(request):
    rows = RecurringExpense.objects.filter(owner=request.user).select_related("group", "category")
    return render(request, "recurring/list.html", {"rows": rows})


@login_required
def recurring_create(request):
    groups = [
        membership.group
        for membership in GroupMembership.objects.filter(user=request.user, status=GroupMembership.Status.ACTIVE).select_related("group")
        if membership.role != "viewer"
    ]
    if request.method == "POST":
        group = next((item for item in groups if str(item.id) == request.POST.get("group")), None)
        category = None
        if request.POST.get("category"):
            category = categories_for(request.user, group).filter(pk=request.POST.get("category")).first()
        people = _people(request.user, group)
        allowed = {person.id for person in people}
        participant_ids = [int(value) for value in request.POST.getlist("participant") if str(value).isdigit()]
        participant_ids = [value for value in participant_ids if value in allowed]
        if request.user.id not in participant_ids:
            participant_ids.append(request.user.id)
        try:
            amount = request.POST.get("amount") or "0"
            create_recurring(
                actor=request.user,
                description=request.POST.get("description", ""),
                amount=Decimal(amount),
                currency=group.currency if group else request.user.preferred_currency,
                frequency=request.POST.get("frequency") or "monthly",
                start_date=date.fromisoformat(request.POST.get("start_date")),
                end_date=date.fromisoformat(request.POST.get("end_date")) if request.POST.get("end_date") else None,
                group=group,
                category=category,
                split_method="equal",
                payload={
                    "participant_ids": participant_ids,
                    "payers": {str(request.user.id): amount},
                    "notes": request.POST.get("notes", ""),
                },
                request=request,
            )
            messages.success(request, "Recurring expense saved. It creates a real expense only when the schedule runs.")
            return redirect("recurring:list")
        except (DomainError, ValueError) as exc:
            messages.error(request, str(exc))
    return render(
        request,
        "recurring/form.html",
        {
            "groups": groups,
            "frequencies": FREQUENCIES,
            "categories": categories_for(request.user),
            "today": date.today(),
            "selected_group": request.GET.get("group") or "",
            "people": _people(
                request.user,
                next((item for item in groups if str(item.id) == request.GET.get("group")), None),
            ),
        },
    )


@login_required
@require_POST
def recurring_status(request, pk):
    row = get_object_or_404(RecurringExpense, pk=pk, owner=request.user)
    action = request.POST.get("action")
    if action == "pause":
        row.status = RecurringExpense.Status.PAUSED
    elif action == "resume":
        row.status = RecurringExpense.Status.ACTIVE
        messages.info(request, "Missed dates will be generated the next time the schedule runs.")
    elif action == "cancel":
        row.status = RecurringExpense.Status.CANCELLED
        row.next_occurrence = None
    row.save()
    return redirect("recurring:list")
