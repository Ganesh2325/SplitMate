from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.common.audit import write_audit
from apps.common.exceptions import AuthorizationError, DomainError
from apps.common.tokens import hash_token, make_token
from apps.groups.access import active_membership, is_manager
from apps.groups.models import Group, GroupInvitation, GroupMembership, GroupMembershipEvent
from apps.notifications.services import notify, record_activity


def _event(group, user, actor, action, from_role="", to_role="", note=""):
    GroupMembershipEvent.objects.create(
        group=group,
        user=user,
        actor=actor,
        action=action,
        from_role=from_role,
        to_role=to_role,
        note=note[:255],
    )


def create_group(*, actor, name, group_type, currency, description="", image=None, simplify_debts=True, default_split_method="equal", request=None):
    name = (name or "").strip()
    if not name:
        raise DomainError("Enter a group name.", field="name")
    group = Group.objects.create(
        name=name[:120],
        description=(description or "")[:4000],
        image=image or "",
        group_type=group_type or "other",
        currency=currency,
        created_by=actor,
        simplify_debts=simplify_debts,
        default_split_method=default_split_method or "equal",
    )
    GroupMembership.objects.create(
        group=group, user=actor, role=GroupMembership.Role.OWNER, added_by=actor
    )
    _event(group, actor, actor, "created", to_role="owner")
    record_activity(
        actor=actor,
        verb="group_create",
        summary=f"{actor.display_name} created {group.name}.",
        group=group,
        path=f"/groups/{group.pk}/",
    )
    write_audit(actor=actor, action="group_create", instance=group, after={"name": group.name}, request=request)
    return group


def update_group(group, *, actor, request=None, **fields):
    membership = active_membership(actor, group)
    if not is_manager(membership):
        raise AuthorizationError("You cannot edit this group.")
    if group.is_archived:
        raise DomainError("Restore the group before editing it.")
    new_currency = fields.get("currency", group.currency)
    if new_currency != group.currency and _has_financial_history(group):
        raise DomainError(
            "Currency cannot change after expenses or repayments exist. Historical amounts would be misread.",
            field="currency",
        )
    before = {"name": group.name, "currency": group.currency, "simplify_debts": group.simplify_debts}
    group.name = (fields.get("name") or group.name).strip()[:120]
    group.description = fields.get("description", group.description) or ""
    group.group_type = fields.get("group_type", group.group_type)
    group.currency = new_currency
    group.simplify_debts = fields.get("simplify_debts", group.simplify_debts)
    group.default_split_method = fields.get("default_split_method", group.default_split_method)
    if fields.get("image"):
        group.image = fields["image"]
    group.save()
    write_audit(
        actor=actor,
        action="group_update",
        instance=group,
        before=before,
        after={"name": group.name, "currency": group.currency, "simplify_debts": group.simplify_debts},
        request=request,
    )
    return group


def _has_financial_history(group):
    from apps.expenses.models import Expense
    from apps.settlements.models import Settlement

    return Expense.objects.filter(group=group).exists() or Settlement.objects.filter(group=group).exists()


def invite_to_group(*, actor, group, user=None, email="", request=None):
    membership = active_membership(actor, group)
    if not is_manager(membership):
        raise AuthorizationError("You cannot invite people to this group.")
    if group.is_archived:
        raise DomainError("This group is archived.")
    email = (email or "").strip().lower()
    if user is None and email:
        user = User.objects.filter(email__iexact=email, is_active=True, anonymized_at__isnull=True).first()
    if user is not None and user.id == actor.id:
        raise DomainError("You are already in this group.")
    if user is not None and active_membership(user, group):
        raise DomainError("That person is already a member.")
    GroupInvitation.objects.filter(group=group, status=GroupInvitation.Status.PENDING, expires_at__lte=timezone.now()).update(
        status=GroupInvitation.Status.EXPIRED
    )
    if user is not None and GroupInvitation.objects.filter(
        group=group, invitee=user, status=GroupInvitation.Status.PENDING
    ).exists():
        raise DomainError("That person already has a pending invitation.")
    if email and GroupInvitation.objects.filter(
        group=group, email=email, status=GroupInvitation.Status.PENDING
    ).exists():
        raise DomainError("That email already has a pending invitation.")
    raw, digest = make_token()
    invite = GroupInvitation.objects.create(
        group=group,
        inviter=actor,
        invitee=user,
        email=email if user is None else (user.email if not email else email),
        token_hash=digest,
        expires_at=timezone.now() + timedelta(days=14),
    )
    if user is not None:
        notify(
            [user],
            actor=actor,
            verb="group_invite",
            message=f"{actor.display_name} invited you to {group.name}.",
            path="/groups/",
            email_kind="group",
        )
    else:
        _email_group_invite(email, actor, group, raw)
    write_audit(actor=actor, action="group_invite", instance=invite, request=request)
    invite.raw_token = raw
    return invite


def _email_group_invite(email, actor, group, raw):
    from django.conf import settings
    from django.core.mail import send_mail
    from django.db import transaction

    if not email:
        return

    def send():
        link = f"{settings.SITE_BASE_URL}/groups/invite/{raw}/"
        try:
            send_mail(
                subject=f"Invitation to {group.name} on SplitMate",
                message=f"{actor.display_name} invited you to the group {group.name}.\n\n{link}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=True,
            )
        except Exception:
            pass

    transaction.on_commit(send)


def _lock_invite(invite):
    invite = GroupInvitation.objects.select_for_update().select_related("group", "invitee").get(pk=invite.pk)
    if invite.status != GroupInvitation.Status.PENDING:
        raise DomainError("This invitation is no longer active.")
    if invite.expires_at <= timezone.now():
        invite.status = GroupInvitation.Status.EXPIRED
        invite.save(update_fields=["status"])
        raise DomainError("This invitation has expired.")
    return invite


def _matches_invite(user, invite):
    if invite.invitee_id and invite.invitee_id != user.id:
        return False
    if invite.email and invite.email.lower() != user.email.lower() and invite.invitee_id != user.id:
        return False
    return True


@transaction.atomic
def accept_group_invite(user, invite, request=None):
    invite = _lock_invite(invite)
    if not _matches_invite(user, invite):
        raise AuthorizationError("This invitation belongs to someone else.")
    if invite.group.is_archived:
        raise DomainError("This group is archived.")
    membership = GroupMembership.objects.filter(group=invite.group, user=user).first()
    if membership is None:
        membership = GroupMembership.objects.create(
            group=invite.group,
            user=user,
            role=GroupMembership.Role.MEMBER,
            added_by=invite.inviter,
        )
    else:
        membership.status = GroupMembership.Status.ACTIVE
        membership.role = membership.role or GroupMembership.Role.MEMBER
        membership.left_at = None
        membership.save()
    invite.status = GroupInvitation.Status.ACCEPTED
    invite.invitee = user
    invite.responded_at = timezone.now()
    invite.save()
    _event(invite.group, user, user, "joined", to_role=membership.role)
    notify(
        [invite.inviter],
        actor=user,
        verb="group_join",
        message=f"{user.display_name} joined {invite.group.name}.",
        path=f"/groups/{invite.group_id}/",
        email_kind="group",
    )
    record_activity(
        actor=user,
        verb="group_join",
        summary=f"{user.display_name} joined {invite.group.name}.",
        group=invite.group,
        path=f"/groups/{invite.group_id}/",
    )
    write_audit(actor=user, action="group_join", instance=membership, request=request)
    return membership


@transaction.atomic
def decline_group_invite(user, invite, request=None):
    invite = _lock_invite(invite)
    if not _matches_invite(user, invite):
        raise AuthorizationError("This invitation belongs to someone else.")
    invite.status = GroupInvitation.Status.DECLINED
    invite.responded_at = timezone.now()
    invite.save()
    write_audit(actor=user, action="group_decline", instance=invite, request=request)
    return invite


@transaction.atomic
def cancel_group_invite(actor, invite, request=None):
    invite = _lock_invite(invite)
    membership = active_membership(actor, invite.group)
    if not is_manager(membership) and invite.inviter_id != actor.id:
        raise AuthorizationError("You cannot cancel that invitation.")
    invite.status = GroupInvitation.Status.CANCELLED
    invite.responded_at = timezone.now()
    invite.save()
    write_audit(actor=actor, action="group_invite_cancel", instance=invite, request=request)
    return invite


def invitation_from_token(raw):
    return (
        GroupInvitation.objects.filter(token_hash=hash_token(raw))
        .select_related("group", "inviter", "invitee")
        .first()
    )


@transaction.atomic
def set_member_role(actor, group, user, role, request=None):
    actor_membership = active_membership(actor, group)
    target = GroupMembership.objects.select_for_update().filter(group=group, user=user).first()
    if target is None or target.status != GroupMembership.Status.ACTIVE:
        raise DomainError("That person is not an active member.")
    if role not in {
        GroupMembership.Role.OWNER,
        GroupMembership.Role.ADMIN,
        GroupMembership.Role.MEMBER,
        GroupMembership.Role.VIEWER,
    }:
        raise DomainError("Choose a valid role.")
    if actor_membership is None or actor_membership.role != GroupMembership.Role.OWNER:
        if not is_manager(actor_membership):
            raise AuthorizationError("You cannot change roles.")
        if role in {GroupMembership.Role.OWNER, GroupMembership.Role.ADMIN}:
            raise AuthorizationError("Only the owner can assign admins or transfer ownership.")
        if target.role in {GroupMembership.Role.OWNER, GroupMembership.Role.ADMIN}:
            raise AuthorizationError("Only the owner can change an admin.")
    if role == GroupMembership.Role.OWNER and user.id != actor.id:
        return transfer_ownership(actor, group, user, request=request)
    previous = target.role
    target.role = role
    target.save(update_fields=["role"])
    _event(group, user, actor, "role", from_role=previous, to_role=role)
    write_audit(
        actor=actor,
        action="group_role",
        instance=target,
        before={"role": previous},
        after={"role": role},
        request=request,
    )
    return target


@transaction.atomic
def transfer_ownership(actor, group, user, request=None):
    actor_membership = GroupMembership.objects.select_for_update().get(
        group=group, user=actor, status=GroupMembership.Status.ACTIVE
    )
    if actor_membership.role != GroupMembership.Role.OWNER:
        raise AuthorizationError("Only the owner can transfer ownership.")
    target = GroupMembership.objects.select_for_update().get(
        group=group, user=user, status=GroupMembership.Status.ACTIVE
    )
    actor_membership.role = GroupMembership.Role.ADMIN
    target.role = GroupMembership.Role.OWNER
    actor_membership.save(update_fields=["role"])
    target.save(update_fields=["role"])
    _event(group, user, actor, "transfer", from_role="owner", to_role="owner")
    write_audit(actor=actor, action="group_transfer", instance=group, after={"owner_id": user.id}, request=request)
    return target


@transaction.atomic
def remove_member(actor, group, user, request=None):
    actor_membership = active_membership(actor, group)
    target = GroupMembership.objects.select_for_update().filter(
        group=group, user=user, status=GroupMembership.Status.ACTIVE
    ).first()
    if target is None:
        raise DomainError("That person is not an active member.")
    if user.id == actor.id:
        return leave_group(actor, group, request=request)
    if not is_manager(actor_membership):
        raise AuthorizationError("You cannot remove members.")
    if target.role == GroupMembership.Role.OWNER:
        raise AuthorizationError("Transfer ownership before removing the owner.")
    if actor_membership.role == GroupMembership.Role.ADMIN and target.role == GroupMembership.Role.ADMIN:
        raise AuthorizationError("An admin cannot remove another admin.")
    target.status = GroupMembership.Status.REMOVED
    target.left_at = timezone.now()
    target.save(update_fields=["status", "left_at"])
    _event(group, user, actor, "removed", from_role=target.role)
    notify(
        [user],
        actor=actor,
        verb="group_remove",
        message=f"You were removed from {group.name}. Existing expenses stay in the record.",
        path="/groups/",
        email_kind="group",
    )
    write_audit(actor=actor, action="group_remove", instance=target, request=request)
    return target


@transaction.atomic
def leave_group(actor, group, request=None):
    membership = GroupMembership.objects.select_for_update().filter(
        group=group, user=actor, status=GroupMembership.Status.ACTIVE
    ).first()
    if membership is None:
        raise DomainError("You are not a member of this group.")
    others = GroupMembership.objects.filter(group=group, status=GroupMembership.Status.ACTIVE).exclude(user=actor)
    if membership.role == GroupMembership.Role.OWNER and others.exists():
        raise DomainError("Transfer ownership before leaving this group.")
    if membership.role == GroupMembership.Role.OWNER and not others.exists():
        group.archived_at = timezone.now()
        group.save(update_fields=["archived_at", "updated_at"])
    membership.status = GroupMembership.Status.LEFT
    membership.left_at = timezone.now()
    membership.save(update_fields=["status", "left_at"])
    _event(group, actor, actor, "left", from_role=membership.role)
    record_activity(
        actor=actor,
        verb="group_leave",
        summary=f"{actor.display_name} left {group.name}.",
        group=group,
        path=f"/groups/{group.pk}/",
    )
    write_audit(actor=actor, action="group_leave", instance=membership, request=request)
    return membership


@transaction.atomic
def archive_group(actor, group, request=None):
    membership = active_membership(actor, group)
    if membership is None or membership.role != GroupMembership.Role.OWNER:
        raise AuthorizationError("Only the owner can archive this group.")
    group.archived_at = timezone.now()
    group.save(update_fields=["archived_at", "updated_at"])
    write_audit(actor=actor, action="group_archive", instance=group, request=request)
    return group


@transaction.atomic
def restore_group(actor, group, request=None):
    membership = GroupMembership.objects.filter(
        group=group, user=actor, status=GroupMembership.Status.ACTIVE, role=GroupMembership.Role.OWNER
    ).first()
    if membership is None:
        raise AuthorizationError("Only the owner can restore this group.")
    group.archived_at = None
    group.save(update_fields=["archived_at", "updated_at"])
    write_audit(actor=actor, action="group_restore", instance=group, request=request)
    return group


@transaction.atomic
def delete_group(actor, group, request=None):
    membership = active_membership(actor, group)
    if membership is None or membership.role != GroupMembership.Role.OWNER:
        raise AuthorizationError("Only the owner can delete this group.")
    if _has_financial_history(group):
        raise DomainError("Archive this group instead. It has expenses or repayments, so it cannot be deleted.")
    write_audit(actor=actor, action="group_delete", instance=group, before={"name": group.name}, request=request)
    group.delete()


def link_group_invitations(user):
    GroupInvitation.objects.filter(
        email__iexact=user.email,
        status=GroupInvitation.Status.PENDING,
        invitee__isnull=True,
        expires_at__gt=timezone.now(),
    ).update(invitee=user)
