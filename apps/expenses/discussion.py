from datetime import timedelta

from django.utils import timezone

from apps.common.audit import write_audit
from apps.common.exceptions import AuthorizationError, DomainError
from apps.expenses.access import can_view_expense
from apps.expenses.models import ExpenseComment
from apps.groups.access import is_manager, active_membership
from apps.notifications.services import notify, record_activity


def add_comment(expense, author, body, request=None):
    if not can_view_expense(author, expense):
        raise AuthorizationError("You cannot comment on this expense.")
    body = (body or "").strip()
    if not body:
        raise DomainError("Write a comment.", field="body")
    if len(body) > 2000:
        raise DomainError("Keep the comment under 2000 characters.", field="body")
    comment = ExpenseComment.objects.create(expense=expense, author=author, body=body)
    from apps.accounts.models import User

    ids = set(expense.shares.values_list("user_id", flat=True)) | set(
        expense.payers.values_list("user_id", flat=True)
    )
    notify(
        list(User.objects.filter(pk__in=ids)),
        actor=author,
        verb="comment",
        message=f"{author.display_name} commented on “{expense.description}”.",
        path=f"/expenses/{expense.pk}/",
        email_kind="comment",
    )
    record_activity(
        actor=author,
        verb="comment",
        summary=f"{author.display_name} commented on “{expense.description}”.",
        group=expense.group,
        path=f"/expenses/{expense.pk}/",
        viewer_ids=None if expense.group_id else list(ids),
    )
    write_audit(actor=author, action="comment_add", instance=comment, request=request)
    return comment


def edit_comment(comment, author, body, request=None):
    if comment.author_id != author.id:
        raise AuthorizationError("You can edit only your own comment.")
    if comment.hidden_at:
        raise DomainError("This comment is hidden.")
    if timezone.now() - comment.created_at > timedelta(minutes=30):
        raise DomainError("Comments can be edited for 30 minutes after they are posted.")
    body = (body or "").strip()
    if not body:
        raise DomainError("Write a comment.", field="body")
    comment.body = body
    comment.edited_at = timezone.now()
    comment.save(update_fields=["body", "edited_at", "updated_at"])
    write_audit(actor=author, action="comment_edit", instance=comment, request=request)
    return comment


def hide_comment(comment, actor, request=None):
    allowed = comment.author_id == actor.id
    if comment.expense.group_id:
        allowed = allowed or is_manager(active_membership(actor, comment.expense.group))
    if not allowed:
        raise AuthorizationError("You cannot hide this comment.")
    comment.hidden_at = timezone.now()
    comment.hidden_by = actor
    comment.save(update_fields=["hidden_at", "hidden_by", "updated_at"])
    write_audit(actor=actor, action="comment_hide", instance=comment, request=request)
    return comment
