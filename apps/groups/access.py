from apps.groups.models import GroupMembership


def active_membership(user, group):
    if not getattr(user, "is_authenticated", False):
        return None
    return (
        GroupMembership.objects.filter(
            group=group, user=user, status=GroupMembership.Status.ACTIVE
        )
        .select_related("group")
        .first()
    )


def is_manager(membership):
    return bool(
        membership
        and membership.role in {GroupMembership.Role.OWNER, GroupMembership.Role.ADMIN}
    )


def can_add_expense(membership):
    return bool(
        membership
        and not membership.group.is_archived
        and membership.role
        in {GroupMembership.Role.OWNER, GroupMembership.Role.ADMIN, GroupMembership.Role.MEMBER}
    )
