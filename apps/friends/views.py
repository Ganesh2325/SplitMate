from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.common.exceptions import AuthorizationError, DomainError
from apps.expenses.models import Expense
from apps.friends.models import FriendInvitation, Friendship
from apps.friends.services import (
    accept_email_invite,
    accept_friend_request,
    are_friends,
    block_user,
    cancel_friend_request,
    decline_friend_request,
    friends_of,
    invitation_from_token,
    invite_by_email,
    remove_friend,
    search_users,
    send_friend_request,
    unblock_user,
)
from apps.settlements.balances import explain_person, person_debt_map, person_expense_map
from apps.settlements.models import Settlement


@login_required
def friend_list(request):
    return render(request, "friends/list.html", {"friends": friends_of(request.user)})


@login_required
def friend_add(request):
    query = (request.GET.get("q") or "").strip()
    results = []
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        user_id = request.POST.get("user_id")
        try:
            if user_id:
                send_friend_request(request.user, get_object_or_404(User, pk=user_id), request=request)
                messages.success(request, "Friend request sent.")
            elif email:
                invite_by_email(request.user, email, request=request)
                messages.success(request, "Invitation sent if that address can receive mail. Existing members get an in-app request.")
            return redirect("friends:requests")
        except (DomainError, AuthorizationError) as exc:
            messages.error(request, str(exc))
    if query:
        results = search_users(request.user, query)
    return render(request, "friends/add.html", {"query": query, "results": results})


@login_required
def friend_requests(request):
    now = timezone.now()
    FriendInvitation.objects.filter(inviter=request.user, status=FriendInvitation.Status.PENDING, expires_at__lte=now).update(
        status=FriendInvitation.Status.EXPIRED
    )
    incoming = Friendship.objects.filter(addressee=request.user, status=Friendship.Status.PENDING).select_related("requester")
    outgoing = Friendship.objects.filter(requester=request.user, status=Friendship.Status.PENDING).select_related("addressee")
    email_invites = FriendInvitation.objects.filter(
        email__iexact=request.user.email, status=FriendInvitation.Status.PENDING, expires_at__gt=now
    ).select_related("inviter")
    return render(
        request,
        "friends/requests.html",
        {"incoming": incoming, "outgoing": outgoing, "email_invites": email_invites},
    )


@login_required
@require_POST
def friend_respond(request, pk):
    friendship = get_object_or_404(Friendship, pk=pk)
    action = request.POST.get("action")
    try:
        if action == "accept":
            accept_friend_request(request.user, friendship, request=request)
        elif action == "decline":
            decline_friend_request(request.user, friendship, request=request)
        elif action == "cancel":
            cancel_friend_request(request.user, friendship, request=request)
        else:
            raise DomainError("Choose an action.")
    except (DomainError, AuthorizationError) as exc:
        messages.error(request, str(exc))
    return redirect("friends:requests")


@login_required
def friend_detail(request, pk):
    other = get_object_or_404(User, pk=pk, is_active=True)
    if other.id == request.user.id:
        return redirect("accounts:profile")
    expense_map = person_expense_map(request.user)
    debt_map = person_debt_map(request.user)
    balances = []
    currencies = set(expense_map) | set(debt_map)
    for currency in currencies:
        expense_net = expense_map[currency][other.id]
        loan_net = debt_map[currency][other.id]
        if expense_net or loan_net or are_friends(request.user, other):
            balances.append(
                {
                    "currency": currency,
                    "expense_net": expense_net,
                    "loan_net": loan_net,
                    "combined": expense_net + loan_net,
                    "lines": explain_person(request.user, other, currency),
                }
            )
    shared = (
        Expense.objects.filter(Q(payers__user=request.user) | Q(shares__user=request.user))
        .filter(Q(payers__user=other) | Q(shares__user=other))
        .distinct()
        .select_related("group", "category")
        .order_by("-expense_date")[:30]
    )
    settlements = Settlement.objects.filter(
        Q(payer=request.user, recipient=other) | Q(payer=other, recipient=request.user)
    ).order_by("-settled_on")[:30]
    return render(
        request,
        "friends/detail.html",
        {
            "other": other,
            "is_friend": are_friends(request.user, other),
            "balances": balances,
            "shared": shared,
            "settlements": settlements,
        },
    )


@login_required
@require_POST
def friend_remove(request, pk):
    other = get_object_or_404(User, pk=pk)
    try:
        remove_friend(request.user, other, request=request)
        messages.success(request, "Friend removed. Existing expenses and balances remain.")
    except DomainError as exc:
        messages.error(request, str(exc))
    return redirect("friends:list")


@login_required
@require_POST
def friend_block(request, pk):
    other = get_object_or_404(User, pk=pk)
    if request.POST.get("action") == "unblock":
        try:
            unblock_user(request.user, other, request=request)
            messages.success(request, "Person unblocked.")
        except AuthorizationError as exc:
            messages.error(request, str(exc))
    else:
        block_user(request.user, other, request=request)
        messages.success(request, "Person blocked.")
    return redirect("friends:list")


@login_required
@require_POST
def friend_email_accept(request, pk):
    invite = get_object_or_404(FriendInvitation, pk=pk, email__iexact=request.user.email)
    try:
        with transaction.atomic():
            accept_email_invite(request.user, invite, request=request)
        messages.success(request, "You are now friends.")
    except (DomainError, AuthorizationError) as exc:
        messages.error(request, str(exc))
    return redirect("friends:list")


def friend_email_link(request, token):
    invite = invitation_from_token(token)
    if invite is None:
        raise Http404()
    if not request.user.is_authenticated:
        request.session["friend_invite_token"] = token
        messages.info(request, "Sign in or create an account with the invited email to accept.")
        return redirect("accounts:login")
    try:
        with transaction.atomic():
            accept_email_invite(request.user, invite, request=request)
        messages.success(request, "You are now friends.")
    except (DomainError, AuthorizationError) as exc:
        messages.error(request, str(exc))
    return redirect("friends:list")
