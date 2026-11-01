import uuid
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.categories.models import ExpenseCategory
from apps.common.audit import write_audit
from apps.common.exceptions import AuthorizationError, DomainError
from apps.common.money import quantize_amount
from apps.expenses.access import can_edit_expense
from apps.expenses.models import (
    Expense,
    ExpenseItem,
    ExpenseItemShare,
    ExpensePayer,
    ExpenseRevision,
    ExpenseShare,
    ExpenseTag,
    ExpenseTagAssignment,
)
from apps.expenses.planning import SplitPlan, normalize_tags, plan_split
from apps.notifications.services import notify, record_activity


def _uuid(value):
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _snapshot(expense):
    expense = Expense.objects.prefetch_related("payers__user", "shares__user").get(pk=expense.pk)
    return {
        "description": expense.description,
        "amount": str(expense.amount),
        "currency": expense.currency,
        "split_method": expense.split_method,
        "status": expense.status,
        "expense_date": expense.expense_date.isoformat(),
        "group_id": expense.group_id,
        "category_id": expense.category_id,
        "notes": expense.notes,
        "payers": [
            {"user_id": row.user_id, "username": row.user.username, "amount": str(row.amount)}
            for row in expense.payers.all()
        ],
        "shares": [
            {"user_id": row.user_id, "username": row.user.username, "amount": str(row.amount)}
            for row in expense.shares.all()
        ],
    }


def _write_children(expense, plan: SplitPlan):
    ExpensePayer.objects.bulk_create(
        [
            ExpensePayer(expense=expense, user_id=user_id, amount=amount)
            for user_id, amount in plan.payers.items()
        ]
    )
    ExpenseShare.objects.bulk_create(
        [
            ExpenseShare(
                expense=expense,
                user_id=user_id,
                amount=amount,
                percentage=plan.percentages.get(user_id),
                weight=plan.weights.get(user_id),
            )
            for user_id, amount in plan.shares.items()
        ]
    )
    for position, item in enumerate(plan.items):
        row = ExpenseItem.objects.create(
            expense=expense,
            description=item["description"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            line_total=item["line_total"],
            position=position,
        )
        ExpenseItemShare.objects.bulk_create(
            [
                ExpenseItemShare(item=row, user_id=user_id, amount=amount)
                for user_id, amount in item["shares"].items()
            ]
        )


def _replace_tags(expense, actor, tags):
    expense.tag_assignments.all().delete()
    for name in tags:
        tag, _created = ExpenseTag.objects.get_or_create(owner=actor, name=name)
        ExpenseTagAssignment.objects.get_or_create(expense=expense, tag=tag)


def _revision(expense, actor, reason, before, after):
    number = (expense.revisions.order_by("-number").values_list("number", flat=True).first() or 0) + 1
    ExpenseRevision.objects.create(
        expense=expense,
        number=number,
        actor=actor,
        reason=(reason or "")[:255],
        before=before,
        after=after,
    )


def _people_ids(plan: SplitPlan):
    return set(plan.payers) | set(plan.shares)


def _notify_expense(expense, actor, verb, message):
    from apps.accounts.models import User

    ids = set(expense.payers.values_list("user_id", flat=True)) | set(
        expense.shares.values_list("user_id", flat=True)
    )
    users = list(User.objects.filter(pk__in=ids))
    path = f"/expenses/{expense.pk}/"
    notify(users, actor=actor, verb=verb, message=message, path=path, email_kind="expense")
    record_activity(
        actor=actor,
        verb=verb,
        summary=message,
        group=expense.group,
        path=path,
        viewer_ids=None if expense.group_id else list(ids),
    )


def category_or_error(actor, category_id, group):
    try:
        category = ExpenseCategory.objects.get(pk=category_id)
    except ExpenseCategory.DoesNotExist as exc:
        raise DomainError("Choose a category.", field="category") from exc
    if category.is_system:
        return category
    if category.owner_id == actor.id and category.group_id is None:
        return category
    if group is not None and category.group_id == group.id:
        return category
    raise DomainError("You cannot use that category.", field="category")


def create_expense(
    *,
    actor,
    description,
    amount,
    currency,
    expense_date,
    split_method,
    participant_ids,
    payers,
    category,
    client_token,
    group=None,
    notes="",
    tags=None,
    exact=None,
    percentages=None,
    weights=None,
    items=None,
    tax=0,
    discount=0,
    tip=0,
    adjustment_method="proportional",
    request=None,
):
    description = (description or "").strip()
    if not description:
        raise DomainError("Enter a description.", field="description")
    if len(description) > 200:
        raise DomainError("Keep the description under 200 characters.", field="description")
    token = _uuid(client_token)
    existing = Expense.objects.filter(created_by=actor, client_token=token).first()
    if existing:
        return existing
    plan = plan_split(
        actor=actor,
        amount=amount,
        currency=currency,
        split_method=split_method,
        participant_ids=participant_ids,
        payers=payers,
        group=group,
        exact=exact,
        percentages=percentages,
        weights=weights,
        items=items,
        tax=tax,
        discount=discount,
        tip=tip,
        adjustment_method=adjustment_method,
        expense_date=expense_date,
    )
    tag_names = normalize_tags(tags or [])
    try:
        with transaction.atomic():
            expense = Expense.objects.create(
                group=group,
                created_by=actor,
                category=category,
                description=description,
                notes=(notes or "")[:4000],
                amount=plan.amount,
                currency=plan.currency,
                expense_date=expense_date,
                split_method=split_method,
                tax_amount=quantize_amount(tax or 0, currency, allow_zero=True),
                discount_amount=quantize_amount(discount or 0, currency, allow_zero=True),
                tip_amount=quantize_amount(tip or 0, currency, allow_zero=True),
                adjustment_method=adjustment_method,
                client_token=token,
            )
            _write_children(expense, plan)
            _replace_tags(expense, actor, tag_names)
            after = _snapshot(expense)
            _revision(expense, actor, "Created", None, after)
            write_audit(
                actor=actor,
                action="expense_create",
                instance=expense,
                after=after,
                request=request,
            )
    except IntegrityError:
        existing = Expense.objects.filter(created_by=actor, client_token=token).first()
        if existing:
            return existing
        raise
    _notify_expense(expense, actor, "expense_create", f"{actor.display_name} added “{expense.description}”.")
    from apps.budgets.services import check_budgets_for_expense

    check_budgets_for_expense(expense)
    return expense


def update_expense(expense, *, actor, reason="", request=None, **fields):
    if not can_edit_expense(actor, expense):
        raise AuthorizationError("You cannot edit this expense.")
    category = fields["category"]
    group = expense.group
    if fields.get("currency") and fields["currency"] != expense.currency:
        raise DomainError("Currency cannot be changed. Void the expense and add a new one.", field="currency")
    if fields.get("group") is not None and getattr(fields.get("group"), "id", None) != expense.group_id:
        raise DomainError("A saved expense stays in its original group. Void it and add a new one.", field="group")
    plan = plan_split(
        actor=actor,
        amount=fields["amount"],
        currency=expense.currency,
        split_method=fields["split_method"],
        participant_ids=fields["participant_ids"],
        payers=fields["payers"],
        group=group,
        exact=fields.get("exact"),
        percentages=fields.get("percentages"),
        weights=fields.get("weights"),
        items=fields.get("items"),
        tax=fields.get("tax") or 0,
        discount=fields.get("discount") or 0,
        tip=fields.get("tip") or 0,
        adjustment_method=fields.get("adjustment_method") or "proportional",
        expense_date=fields["expense_date"],
        editing=True,
    )
    # Editing keeps the original creator's permission even if a new participant is outside
    # the editor's friend list but inside the group. plan_split already enforces that.
    description = (fields["description"] or "").strip()
    if not description:
        raise DomainError("Enter a description.", field="description")
    tag_names = normalize_tags(fields.get("tags") or [])
    with transaction.atomic():
        locked = Expense.objects.select_for_update().get(pk=expense.pk)
        if locked.status != Expense.Status.ACTIVE:
            raise DomainError("Voided expenses cannot be edited.")
        before = _snapshot(locked)
        locked.description = description
        locked.notes = (fields.get("notes") or "")[:4000]
        locked.amount = plan.amount
        locked.expense_date = fields["expense_date"]
        locked.split_method = fields["split_method"]
        locked.category = category
        locked.tax_amount = quantize_amount(fields.get("tax") or 0, locked.currency, allow_zero=True)
        locked.discount_amount = quantize_amount(fields.get("discount") or 0, locked.currency, allow_zero=True)
        locked.tip_amount = quantize_amount(fields.get("tip") or 0, locked.currency, allow_zero=True)
        locked.adjustment_method = fields.get("adjustment_method") or "proportional"
        locked.save()
        locked.payers.all().delete()
        locked.shares.all().delete()
        locked.items.all().delete()
        _write_children(locked, plan)
        _replace_tags(locked, actor, tag_names)
        after = _snapshot(locked)
        _revision(locked, actor, reason, before, after)
        write_audit(
            actor=actor,
            action="expense_update",
            instance=locked,
            before=before,
            after=after,
            reason=reason,
            request=request,
        )
    _notify_expense(locked, actor, "expense_update", f"{actor.display_name} updated “{locked.description}”.")
    from apps.budgets.services import check_budgets_for_expense

    check_budgets_for_expense(locked)
    return locked


def void_expense(expense, *, actor, reason, request=None):
    if not can_edit_expense(actor, expense):
        raise AuthorizationError("You cannot void this expense.")
    reason = (reason or "").strip()
    if not reason:
        raise DomainError("Enter a reason for voiding this expense.", field="reason")
    with transaction.atomic():
        locked = Expense.objects.select_for_update().get(pk=expense.pk)
        if locked.status != Expense.Status.ACTIVE:
            raise DomainError("This expense is already voided.")
        before = _snapshot(locked)
        locked.status = Expense.Status.VOID
        locked.voided_by = actor
        locked.voided_at = timezone.now()
        locked.void_reason = reason[:255]
        locked.save()
        after = _snapshot(locked)
        _revision(locked, actor, reason, before, after)
        write_audit(
            actor=actor,
            action="expense_void",
            instance=locked,
            before=before,
            after=after,
            reason=reason,
            request=request,
        )
    _notify_expense(locked, actor, "expense_void", f"{actor.display_name} voided “{locked.description}”.")
    return locked


def participant_ids(expense):
    return list(
        set(expense.payers.values_list("user_id", flat=True))
        | set(expense.shares.values_list("user_id", flat=True))
    )
