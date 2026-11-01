from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.common.constants import CURRENCY_CHOICES, GROUP_TYPES, SPLIT_METHODS
from apps.common.exceptions import AuthorizationError, DomainError
from apps.expenses.models import Expense
from apps.groups.access import active_membership, is_manager
from apps.groups.models import Group, GroupInvitation, GroupMembership
from apps.groups.services import (
    accept_group_invite,
    archive_group,
    cancel_group_invite,
    create_group,
    decline_group_invite,
    delete_group,
    invitation_from_token,
    invite_to_group,
    leave_group,
    remove_member,
    restore_group,
    set_member_role,
    update_group,
)
from apps.settlements.balances import explain_group, group_nets
from apps.settlements.models import Settlement
from apps.settlements.simplify import simplify_nets, suggestions_match_nets


def _group_or_404(user, pk):
    group = get_object_or_404(Group, pk=pk)
    if not active_membership(user, group):
        raise Http404()
    return group


@login_required
def group_list(request):
    show_archived = request.GET.get("archived") == "1"
    memberships = GroupMembership.objects.filter(user=request.user, status=GroupMembership.Status.ACTIVE).select_related("group")
    if not show_archived:
        memberships = memberships.filter(group__archived_at__isnull=True)
    invites = GroupInvitation.objects.filter(invitee=request.user, status=GroupInvitation.Status.PENDING).select_related("group", "inviter")
    return render(request, "groups/list.html", {"memberships": memberships, "invites": invites, "show_archived": show_archived})


@login_required
def group_create(request):
    if request.method == "POST":
        try:
            group = create_group(
                actor=request.user,
                name=request.POST.get("name", ""),
                description=request.POST.get("description", ""),
                group_type=request.POST.get("group_type") or "other",
                currency=request.POST.get("currency") or request.user.preferred_currency,
                image=request.FILES.get("image"),
                simplify_debts=request.POST.get("simplify_debts") == "on",
                default_split_method=request.POST.get("default_split_method") or "equal",
                request=request,
            )
            messages.success(request, "Group created.")
            return redirect("groups:detail", pk=group.pk)
        except DomainError as exc:
            messages.error(request, str(exc))
    return render(
        request,
        "groups/form.html",
        {"types": GROUP_TYPES, "currencies": CURRENCY_CHOICES, "methods": SPLIT_METHODS, "group": None},
    )


@login_required
def group_detail(request, pk):
    group = _group_or_404(request.user, pk)
    membership = active_membership(request.user, group)
    members = group.memberships.filter(status=GroupMembership.Status.ACTIVE).select_related("user")
    total = group.expenses.filter(status=Expense.Status.ACTIVE).aggregate(total=Sum("amount"))["total"] or 0
    recent = group.expenses.select_related("category").order_by("-expense_date", "-id")[:8]
    return render(
        request,
        "groups/detail.html",
        {
            "group": group,
            "membership": membership,
            "members": members,
            "total": total,
            "recent": recent,
            "can_manage": is_manager(membership),
        },
    )


@login_required
def group_image(request, pk):
    group = _group_or_404(request.user, pk)
    if not group.image:
        raise Http404()
    return FileResponse(group.image.open("rb"))


@login_required
def group_members(request, pk):
    group = _group_or_404(request.user, pk)
    membership = active_membership(request.user, group)
    members = group.memberships.select_related("user").order_by("status", "role", "user__username")
    events = group.membership_events.select_related("actor", "user")[:40]
    invites = group.invitations.filter(status=GroupInvitation.Status.PENDING).select_related("invitee", "inviter")
    return render(
        request,
        "groups/members.html",
        {"group": group, "membership": membership, "members": members, "events": events, "invites": invites, "can_manage": is_manager(membership)},
    )


@login_required
@require_POST
def group_invite(request, pk):
    group = _group_or_404(request.user, pk)
    identifier = (request.POST.get("identifier") or "").strip()
    try:
        user = None
        email = ""
        if "@" in identifier:
            email = identifier
            user = User.objects.filter(email__iexact=email, is_active=True).first()
        elif identifier:
            user = User.objects.filter(username__iexact=identifier, is_active=True).first()
            if user is None:
                raise DomainError("No account uses that username.")
        else:
            raise DomainError("Enter a username or email.")
        invite_to_group(actor=request.user, group=group, user=user, email=email, request=request)
        messages.success(request, "Invitation sent.")
    except (DomainError, AuthorizationError) as exc:
        messages.error(request, str(exc))
    return redirect("groups:members", pk=group.pk)


@login_required
@require_POST
def group_invite_respond(request, pk):
    invite = get_object_or_404(GroupInvitation, pk=pk)
    action = request.POST.get("action")
    try:
        if action == "accept":
            accept_group_invite(request.user, invite, request=request)
            messages.success(request, "You joined the group.")
            return redirect("groups:detail", pk=invite.group_id)
        if action == "decline":
            decline_group_invite(request.user, invite, request=request)
        elif action == "cancel":
            cancel_group_invite(request.user, invite, request=request)
    except (DomainError, AuthorizationError) as exc:
        messages.error(request, str(exc))
    return redirect("groups:list")


def group_invite_link(request, token):
    invite = invitation_from_token(token)
    if invite is None:
        raise Http404()
    if not request.user.is_authenticated:
        request.session["group_invite_token"] = token
        return redirect("accounts:login")
    try:
        accept_group_invite(request.user, invite, request=request)
        messages.success(request, f"You joined {invite.group.name}.")
        return redirect("groups:detail", pk=invite.group_id)
    except (DomainError, AuthorizationError) as exc:
        messages.error(request, str(exc))
        return redirect("groups:list")


@login_required
@require_POST
def group_member_action(request, pk, user_id):
    group = _group_or_404(request.user, pk)
    person = get_object_or_404(User, pk=user_id)
    action = request.POST.get("action")
    try:
        if action == "remove":
            remove_member(request.user, group, person, request=request)
        elif action == "role":
            set_member_role(request.user, group, person, request.POST.get("role"), request=request)
        else:
            raise DomainError("Choose an action.")
        messages.success(request, "Membership updated.")
    except (DomainError, AuthorizationError) as exc:
        messages.error(request, str(exc))
    return redirect("groups:members", pk=group.pk)


@login_required
@require_POST
def group_leave(request, pk):
    group = _group_or_404(request.user, pk)
    try:
        leave_group(request.user, group, request=request)
        messages.success(request, "You left the group. Financial history was kept.")
        return redirect("groups:list")
    except DomainError as exc:
        messages.error(request, str(exc))
        return redirect("groups:settings", pk=group.pk)


@login_required
def group_settings(request, pk):
    group = _group_or_404(request.user, pk)
    membership = active_membership(request.user, group)
    if request.method == "POST" and request.POST.get("action") == "save":
        try:
            update_group(
                group,
                actor=request.user,
                name=request.POST.get("name"),
                description=request.POST.get("description"),
                group_type=request.POST.get("group_type"),
                currency=request.POST.get("currency"),
                simplify_debts=request.POST.get("simplify_debts") == "on",
                default_split_method=request.POST.get("default_split_method"),
                image=request.FILES.get("image"),
                request=request,
            )
            messages.success(request, "Group settings saved.")
            return redirect("groups:settings", pk=group.pk)
        except (DomainError, AuthorizationError) as exc:
            messages.error(request, str(exc))
    return render(
        request,
        "groups/settings.html",
        {
            "group": group,
            "membership": membership,
            "can_manage": is_manager(membership),
            "is_owner": membership and membership.role == GroupMembership.Role.OWNER,
            "types": GROUP_TYPES,
            "currencies": CURRENCY_CHOICES,
            "methods": SPLIT_METHODS,
        },
    )


@login_required
@require_POST
def group_archive(request, pk):
    group = _group_or_404(request.user, pk)
    try:
        if request.POST.get("action") == "restore":
            restore_group(request.user, group, request=request)
            messages.success(request, "Group restored.")
        elif request.POST.get("action") == "delete":
            delete_group(request.user, group, request=request)
            messages.success(request, "Group deleted.")
            return redirect("groups:list")
        else:
            archive_group(request.user, group, request=request)
            messages.success(request, "Group archived. History is still available.")
    except (DomainError, AuthorizationError) as exc:
        messages.error(request, str(exc))
    return redirect("groups:settings", pk=pk)


@login_required
def group_balances(request, pk):
    group = _group_or_404(request.user, pk)
    nets = group_nets(group)
    users = User.objects.in_bulk(nets)
    rows = [{"user": users.get(user_id), "net": net} for user_id, net in sorted(nets.items(), key=lambda item: item[1])]
    suggestions = []
    simplify_error = ""
    if group.simplify_debts:
        try:
            suggestions = simplify_nets(nets, group.currency, group.id)
            if not suggestions_match_nets(nets, suggestions, group.currency):
                simplify_error = "Suggestions were withheld because they did not preserve every balance."
                suggestions = []
        except DomainError as exc:
            simplify_error = str(exc)
    elif request.GET.get("simplify") == "1":
        try:
            suggestions = simplify_nets(nets, group.currency, group.id)
        except DomainError as exc:
            simplify_error = str(exc)
    explanation = explain_group(group, request.user)
    settlements = Settlement.objects.filter(group=group).select_related("payer", "recipient").order_by("-settled_on")[:30]
    return render(
        request,
        "groups/balances.html",
        {
            "group": group,
            "rows": rows,
            "suggestions": suggestions,
            "simplify_error": simplify_error,
            "explanation": explanation,
            "settlements": settlements,
            "users": users,
        },
    )


@login_required
def group_expenses(request, pk):
    group = _group_or_404(request.user, pk)
    expenses = group.expenses.select_related("category", "created_by").order_by("-expense_date", "-id")
    return render(request, "groups/expenses.html", {"group": group, "expenses": expenses})
