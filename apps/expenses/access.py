from apps.groups.access import active_membership
from apps.groups.models import GroupMembership


def can_view_expense(user, expense):
    if not getattr(user, "is_authenticated", False):
        return False
    if expense.created_by_id == user.id:
        return True
    if expense.payers.filter(user=user).exists() or expense.shares.filter(user=user).exists():
        return True
    return bool(expense.group_id and active_membership(user, expense.group))


def can_edit_expense(user, expense):
    if expense.status != expense.Status.ACTIVE:
        return False
    if expense.group_id:
        if expense.group.is_archived:
            return False
        membership = active_membership(user, expense.group)
        if membership is None or membership.role == GroupMembership.Role.VIEWER:
            return False
        if membership.role in {GroupMembership.Role.OWNER, GroupMembership.Role.ADMIN}:
            return True
        return expense.created_by_id == user.id
    return expense.created_by_id == user.id
