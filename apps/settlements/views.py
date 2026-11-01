import uuid
from datetime import date

from django.db.models import Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.common.constants import CURRENCY_CHOICES, PAYMENT_METHODS
from apps.common.exceptions import AuthorizationError, DomainError
from apps.friends.services import friends_of
from apps.groups.models import Group, GroupMembership
from apps.settlements.balances import explain_person, personal_lines, totals_by_currency
from apps.settlements.models import InformalDebt, Settlement
from apps.settlements.services import (
    debt_outstanding,
    record_debt,
    record_settlement,
    repay_debt,
    reverse_debt_repayment,
    reverse_settlement,
    void_debt,
)


def _groups(user):
    return Group.objects.filter(memberships__user=user, memberships__status=GroupMembership.Status.ACTIVE)


@login_required
def balance_list(request):
    lines = personal_lines(request.user)
    return render(
        request,
        "settlements/balances.html",
        {
            "lines": lines,
            "totals": totals_by_currency(lines),
            "settlements": Settlement.objects.filter(Q(payer=request.user) | Q(recipient=request.user))
            .select_related("payer", "recipient", "group")
            .order_by("-settled_on")[:8],
        },
    )


@login_required
def balance_with(request, pk):
    other = get_object_or_404(User, pk=pk)
    currency = request.GET.get("currency") or request.user.preferred_currency
    if currency not in {code for code, _label in CURRENCY_CHOICES}:
        currency = "INR"
    return render(
        request,
        "settlements/balance_with.html",
        {"other": other, "currency": currency, "lines": explain_person(request.user, other, currency)},
    )


@login_required
def settle(request):
    groups = _groups(request.user)
    friends = list(friends_of(request.user))
    initial = {
        "payer": request.GET.get("payer") or str(request.user.id),
        "recipient": request.GET.get("recipient") or "",
        "amount": request.GET.get("amount") or "",
        "currency": request.GET.get("currency") or request.user.preferred_currency,
        "group": request.GET.get("group") or "",
        "settled_on": request.GET.get("settled_on") or date.today().isoformat(),
        "method": "upi",
    }
    token = uuid.uuid4()
    if request.method == "POST":
        token = request.POST.get("client_token") or token
        group = None
        if request.POST.get("group"):
            group = get_object_or_404(groups, pk=request.POST.get("group"))
        try:
            payer = get_object_or_404(User, pk=request.POST.get("payer"))
            recipient = get_object_or_404(User, pk=request.POST.get("recipient"))
            settlement = record_settlement(
                actor=request.user,
                payer=payer,
                recipient=recipient,
                amount=request.POST.get("amount") or "0",
                currency=group.currency if group else request.POST.get("currency") or "INR",
                settled_on=date.fromisoformat(request.POST.get("settled_on")),
                method=request.POST.get("method") or "cash",
                group=group,
                note=request.POST.get("note", ""),
                reference=request.POST.get("reference", ""),
                client_token=token,
                is_advance=request.POST.get("is_advance") == "on",
                request=request,
            )
            messages.success(request, "Repayment recorded. This does not contact a bank or payment app.")
            return redirect("settlements:detail", pk=settlement.pk)
        except (DomainError, AuthorizationError, ValueError) as exc:
            messages.error(request, str(exc))
            initial = request.POST
    member_ids = GroupMembership.objects.filter(
        group__in=groups, status=GroupMembership.Status.ACTIVE
    ).values_list("user_id", flat=True)
    people = User.objects.filter(
        Q(pk=request.user.id) | Q(pk__in=[friend.id for friend in friends]) | Q(pk__in=member_ids),
        is_active=True,
    ).order_by("first_name", "username")
    return render(
        request,
        "settlements/settle.html",
        {
            "groups": groups,
            "people": people,
            "methods": PAYMENT_METHODS,
            "currencies": CURRENCY_CHOICES,
            "initial": initial,
            "token": token if request.method != "POST" else request.POST.get("client_token", token),
        },
    )


@login_required
def settlement_list(request):
    queryset = (
        Settlement.objects.filter(payer=request.user) | Settlement.objects.filter(recipient=request.user) | Settlement.objects.filter(created_by=request.user)
    ).distinct().select_related("payer", "recipient", "group").order_by("-settled_on", "-id")
    page = Paginator(queryset, 20).get_page(request.GET.get("page"))
    return render(request, "settlements/history.html", {"page_obj": page, "settlements": page.object_list})


@login_required
def settlement_detail(request, pk):
    settlement = get_object_or_404(
        Settlement.objects.select_related("payer", "recipient", "group", "created_by", "reversal"), pk=pk
    )
    involved = {settlement.payer_id, settlement.recipient_id, settlement.created_by_id}
    if request.user.id not in involved:
        if not settlement.group_id or not _groups(request.user).filter(pk=settlement.group_id).exists():
            raise Http404()
    return render(request, "settlements/detail.html", {"settlement": settlement})


@login_required
@require_POST
def settlement_reverse(request, pk):
    settlement = get_object_or_404(Settlement, pk=pk)
    try:
        reverse_settlement(settlement, actor=request.user, reason=request.POST.get("reason", ""), request=request)
        messages.success(request, "Repayment reversed. The original record remains.")
    except (DomainError, AuthorizationError) as exc:
        messages.error(request, str(exc))
    return redirect("settlements:detail", pk=pk)


@login_required
def debt_list(request):
    debts = (
        InformalDebt.objects.filter(creditor=request.user) | InformalDebt.objects.filter(debtor=request.user)
    ).distinct().select_related("creditor", "debtor").order_by("-borrowed_on")
    rows = [{"debt": debt, "outstanding": debt_outstanding(debt)} for debt in debts]
    return render(request, "settlements/debts.html", {"rows": rows})


@login_required
def debt_create(request):
    friends = list(friends_of(request.user))
    if request.method == "POST":
        try:
            other = get_object_or_404(User, pk=request.POST.get("person"))
            if request.POST.get("direction") == "borrowed":
                creditor, debtor = other, request.user
            else:
                creditor, debtor = request.user, other
            debt = record_debt(
                actor=request.user,
                creditor=creditor,
                debtor=debtor,
                amount=request.POST.get("amount") or "0",
                currency=request.POST.get("currency") or request.user.preferred_currency,
                borrowed_on=date.fromisoformat(request.POST.get("borrowed_on")),
                notes=request.POST.get("notes", ""),
                client_token=request.POST.get("client_token") or uuid.uuid4(),
                request=request,
            )
            messages.success(request, "Loan recorded separately from shared expenses.")
            return redirect("settlements:debt_detail", pk=debt.pk)
        except (DomainError, AuthorizationError, ValueError) as exc:
            messages.error(request, str(exc))
    return render(
        request,
        "settlements/debt_form.html",
        {"friends": friends, "currencies": CURRENCY_CHOICES, "token": uuid.uuid4(), "today": date.today()},
    )


@login_required
def debt_detail(request, pk):
    debt = get_object_or_404(InformalDebt.objects.select_related("creditor", "debtor"), pk=pk)
    if request.user.id not in {debt.creditor_id, debt.debtor_id, debt.created_by_id}:
        raise Http404()
    return render(
        request,
        "settlements/debt_detail.html",
        {"debt": debt, "outstanding": debt_outstanding(debt), "token": uuid.uuid4()},
    )


@login_required
@require_POST
def debt_repay(request, pk):
    debt = get_object_or_404(InformalDebt, pk=pk)
    try:
        if request.POST.get("action") == "void":
            void_debt(debt, actor=request.user, reason=request.POST.get("reason", ""), request=request)
            messages.success(request, "Loan voided.")
        else:
            repay_debt(
                debt,
                actor=request.user,
                amount=request.POST.get("amount") or "0",
                paid_on=date.fromisoformat(request.POST.get("paid_on")),
                note=request.POST.get("note", ""),
                client_token=request.POST.get("client_token") or uuid.uuid4(),
                request=request,
            )
            messages.success(request, "Loan payment recorded.")
    except (DomainError, AuthorizationError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("settlements:debt_detail", pk=pk)


@login_required
@require_POST
def debt_repayment_reverse(request, pk):
    from apps.settlements.models import InformalDebtRepayment

    repayment = get_object_or_404(InformalDebtRepayment, pk=pk)
    try:
        reverse_debt_repayment(repayment, actor=request.user, reason=request.POST.get("reason", ""), request=request)
        messages.success(request, "Loan payment reversed.")
    except (DomainError, AuthorizationError) as exc:
        messages.error(request, str(exc))
    return redirect("settlements:debt_detail", pk=repayment.debt_id)
