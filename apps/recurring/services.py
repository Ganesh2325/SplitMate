import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import DomainError
from apps.expenses.services import category_or_error, create_expense
from apps.recurring.models import RecurringExpense, RecurringExpenseOccurrence
from apps.recurring.schedule import next_date


def _token(recurring_id, scheduled_for):
    return uuid.uuid5(uuid.NAMESPACE_URL, f"splitmate:recurring:{recurring_id}:{scheduled_for.isoformat()}")


def create_recurring(*, actor, description, amount, currency, frequency, start_date, end_date=None, group=None, category=None, split_method, payload, request=None):
    if end_date and end_date < start_date:
        raise DomainError("The end date must be on or after the start date.", field="end_date")
    if frequency not in {choice[0] for choice in RecurringExpense._meta.get_field("frequency").choices}:
        raise DomainError("Choose how often this repeats.", field="frequency")
    # Validate the payload by planning one expense without saving a second copy.
    from apps.expenses.planning import plan_split

    plan_split(
        actor=actor,
        amount=amount,
        currency=currency,
        split_method=split_method,
        participant_ids=payload.get("participant_ids") or [],
        payers={int(key): value for key, value in payload.get("payers", {}).items()},
        group=group,
        exact={int(key): value for key, value in payload.get("exact", {}).items()},
        percentages={int(key): value for key, value in payload.get("percentages", {}).items()},
        weights={int(key): value for key, value in payload.get("weights", {}).items()},
        items=payload.get("items") or [],
        tax=payload.get("tax") or 0,
        discount=payload.get("discount") or 0,
        tip=payload.get("tip") or 0,
        adjustment_method=payload.get("adjustment_method") or "proportional",
        expense_date=start_date,
    )
    return RecurringExpense.objects.create(
        owner=actor,
        group=group,
        category=category,
        description=description.strip()[:200],
        amount=amount,
        currency=currency,
        split_method=split_method,
        frequency=frequency,
        anchor_day=start_date.day,
        start_date=start_date,
        next_occurrence=start_date,
        end_date=end_date,
        payload=payload,
    )


def _generate_one(recurring, scheduled_for):
    payload = recurring.payload or {}
    category = recurring.category
    if category is None:
        category = category_or_error(recurring.owner, payload.get("category_id"), recurring.group)
    return create_expense(
        actor=recurring.owner,
        description=recurring.description,
        amount=recurring.amount,
        currency=recurring.currency,
        expense_date=scheduled_for,
        split_method=recurring.split_method,
        participant_ids=payload.get("participant_ids") or [],
        payers={int(key): Decimal(str(value)) for key, value in payload.get("payers", {}).items()},
        category=category,
        client_token=_token(recurring.id, scheduled_for),
        group=recurring.group,
        notes=payload.get("notes") or "",
        tags=payload.get("tags") or [],
        exact={int(key): Decimal(str(value)) for key, value in payload.get("exact", {}).items()},
        percentages={int(key): Decimal(str(value)) for key, value in payload.get("percentages", {}).items()},
        weights={int(key): Decimal(str(value)) for key, value in payload.get("weights", {}).items()},
        items=payload.get("items") or [],
        tax=payload.get("tax") or 0,
        discount=payload.get("discount") or 0,
        tip=payload.get("tip") or 0,
        adjustment_method=payload.get("adjustment_method") or "proportional",
    )


def process_due_recurring(today=None, limit=366):
    today = today or timezone.localdate()
    created = 0
    ids = list(
        RecurringExpense.objects.filter(
            status=RecurringExpense.Status.ACTIVE, next_occurrence__lte=today
        ).values_list("id", flat=True)
    )
    for recurring_id in ids:
        with transaction.atomic():
            recurring = RecurringExpense.objects.select_for_update().get(pk=recurring_id)
            guard = 0
            while (
                recurring.status == RecurringExpense.Status.ACTIVE
                and recurring.next_occurrence
                and recurring.next_occurrence <= today
                and guard < limit
            ):
                guard += 1
                scheduled = recurring.next_occurrence
                if recurring.end_date and scheduled > recurring.end_date:
                    recurring.status = RecurringExpense.Status.CANCELLED
                    recurring.next_occurrence = None
                    recurring.save(update_fields=["status", "next_occurrence", "updated_at"])
                    break
                occurrence, _created = RecurringExpenseOccurrence.objects.get_or_create(
                    recurring=recurring,
                    scheduled_for=scheduled,
                    defaults={"status": RecurringExpenseOccurrence.Status.PENDING},
                )
                if occurrence.status == RecurringExpenseOccurrence.Status.GENERATED and occurrence.expense_id:
                    recurring.next_occurrence = next_date(scheduled, recurring.frequency, recurring.anchor_day)
                    recurring.save(update_fields=["next_occurrence", "updated_at"])
                    continue
                try:
                    expense = _generate_one(recurring, scheduled)
                except (DomainError, Exception) as exc:
                    if not isinstance(exc, DomainError):
                        message = "This occurrence could not be created."
                    else:
                        message = str(exc)
                    occurrence.status = RecurringExpenseOccurrence.Status.FAILED
                    occurrence.message = message[:500]
                    occurrence.save(update_fields=["status", "message"])
                    recurring.status = RecurringExpense.Status.PAUSED
                    recurring.save(update_fields=["status", "updated_at"])
                    break
                occurrence.status = RecurringExpenseOccurrence.Status.GENERATED
                occurrence.expense = expense
                occurrence.message = ""
                occurrence.save(update_fields=["status", "expense", "message"])
                created += 1
                upcoming = next_date(scheduled, recurring.frequency, recurring.anchor_day)
                if recurring.end_date and upcoming > recurring.end_date:
                    recurring.status = RecurringExpense.Status.CANCELLED
                    recurring.next_occurrence = None
                else:
                    recurring.next_occurrence = upcoming
                recurring.save(update_fields=["status", "next_occurrence", "updated_at"])
    return created
