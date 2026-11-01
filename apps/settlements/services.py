import uuid
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.accounts.models import User
from apps.common.audit import write_audit
from apps.common.exceptions import AuthorizationError, DomainError
from apps.common.money import format_money, quantize_amount
from apps.friends.services import are_friends
from apps.groups.access import active_membership, is_manager
from apps.groups.models import Group, GroupMembership
from apps.notifications.services import notify, record_activity
from apps.settlements.balances import group_nets, group_pairwise, person_expense_map
from apps.settlements.models import InformalDebt, InformalDebtRepayment, Settlement, SettlementReversal

ZERO = Decimal("0")


def _uuid(value):
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def settlement_limit(payer, recipient, currency, group=None):
    if payer.id == recipient.id:
        return ZERO
    if group is not None:
        nets = group_nets(group, currency)
        payer_net = nets.get(payer.id, ZERO)
        recipient_net = nets.get(recipient.id, ZERO)
        pool = min(-payer_net, recipient_net) if payer_net < 0 and recipient_net > 0 else ZERO
        pairwise = group_pairwise(group, currency).get((payer.id, recipient.id), ZERO)
        return max(pool, pairwise)
    balance = person_expense_map(payer)[currency][recipient.id]
    return -balance if balance < 0 else ZERO


def _can_record(actor, payer, recipient, group):
    if group is not None:
        membership = active_membership(actor, group)
        if membership is None or membership.role == GroupMembership.Role.VIEWER:
            raise AuthorizationError("You cannot record a repayment in this group.")
        if not is_manager(membership) and actor.id not in {payer.id, recipient.id}:
            raise AuthorizationError("You can record your own repayment, or an admin can record one.")
        known = set(
            GroupMembership.objects.filter(group=group, user__in=[payer, recipient]).values_list(
                "user_id", flat=True
            )
        )
        if payer.id not in known or recipient.id not in known:
            raise DomainError("Both people need to belong to this group.")
        if group.currency != currency_of(group):
            pass
        return
    if actor.id not in {payer.id, recipient.id}:
        raise AuthorizationError("You can record a repayment you are part of.")
    if not _personally_connected(payer, recipient):
        raise DomainError("Settle with a friend, or with someone you already share an expense with.")


def currency_of(group):
    return group.currency


def _personally_connected(payer, recipient):
    from apps.expenses.models import Expense

    if are_friends(payer, recipient):
        return True
    return (
        Expense.objects.filter(group__isnull=True)
        .filter(Q(payers__user=payer) | Q(shares__user=payer))
        .filter(Q(payers__user=recipient) | Q(shares__user=recipient))
        .exists()
        or Settlement.objects.filter(group__isnull=True)
        .filter(Q(payer=payer, recipient=recipient) | Q(payer=recipient, recipient=payer))
        .exists()
    )


def record_settlement(
    *,
    actor,
    payer,
    recipient,
    amount,
    currency,
    settled_on,
    method="cash",
    group=None,
    note="",
    reference="",
    client_token,
    is_advance=False,
    request=None,
):
    if payer.id == recipient.id:
        raise DomainError("Choose two different people.", field="recipient")
    amount = quantize_amount(amount, currency)
    token = _uuid(client_token)
    existing = Settlement.objects.filter(created_by=actor, client_token=token).first()
    if existing:
        return existing
    if group is not None and currency != group.currency:
        raise DomainError("Use the group's currency.", field="currency")
    if group is not None and group.is_archived:
        raise DomainError("This group is archived.")
    _can_record(actor, payer, recipient, group)
    try:
        with transaction.atomic():
            if group is not None:
                Group.objects.select_for_update().get(pk=group.pk)
            else:
                list(User.objects.select_for_update().filter(pk__in=sorted([payer.id, recipient.id])).order_by("pk"))
            limit = settlement_limit(payer, recipient, currency, group)
            if amount > limit and not is_advance:
                shown = format_money(limit, currency)
                raise DomainError(
                    f"The outstanding amount in this direction is {shown}. "
                    "Tick “Record as an advance” to store a larger payment.",
                    field="amount",
                )
            if limit == 0 and not is_advance:
                raise DomainError(
                    "Nothing is outstanding in this direction. Tick “Record as an advance” if this payment should still be stored.",
                    field="amount",
                )
            settlement = Settlement.objects.create(
                payer=payer,
                recipient=recipient,
                amount=amount,
                currency=currency,
                settled_on=settled_on,
                method=method or "cash",
                reference=(reference or "")[:80],
                note=(note or "")[:255],
                group=group,
                created_by=actor,
                is_advance=bool(is_advance and amount > limit),
                client_token=token,
            )
            write_audit(
                actor=actor,
                action="settlement_record",
                instance=settlement,
                after={
                    "payer": payer.username,
                    "recipient": recipient.username,
                    "amount": str(amount),
                    "currency": currency,
                    "group_id": group.id if group else None,
                    "advance": settlement.is_advance,
                },
                request=request,
            )
    except IntegrityError:
        existing = Settlement.objects.filter(created_by=actor, client_token=token).first()
        if existing:
            return existing
        raise
    path = f"/settlements/{settlement.pk}/"
    message = (
        f"{payer.display_name} paid {recipient.display_name} {format_money(amount, currency)}."
    )
    notify(
        [payer, recipient],
        actor=actor,
        verb="settlement_record",
        message=message,
        path=path,
        email_kind="settlement",
    )
    record_activity(
        actor=actor,
        verb="settlement_record",
        summary=message,
        group=group,
        path=path,
        viewer_ids=None if group else [payer.id, recipient.id],
    )
    return settlement


def reverse_settlement(settlement, *, actor, reason, request=None):
    reason = (reason or "").strip()
    if not reason:
        raise DomainError("Enter a reason.", field="reason")
    allowed = {settlement.created_by_id, settlement.payer_id, settlement.recipient_id}
    if settlement.group_id:
        membership = active_membership(actor, settlement.group)
        if is_manager(membership):
            allowed.add(actor.id)
    if actor.id not in allowed:
        raise AuthorizationError("You cannot reverse this repayment.")
    with transaction.atomic():
        locked = Settlement.objects.select_for_update().get(pk=settlement.pk)
        if locked.status != Settlement.Status.RECORDED:
            raise DomainError("This repayment was already reversed.")
        locked.status = Settlement.Status.REVERSED
        locked.save(update_fields=["status"])
        reversal = SettlementReversal.objects.create(settlement=locked, actor=actor, reason=reason[:255])
        write_audit(
            actor=actor,
            action="settlement_reverse",
            instance=locked,
            after={"status": "reversed", "reason": reason[:255]},
            reason=reason,
            request=request,
        )
    message = f"{actor.display_name} reversed a repayment of {format_money(locked.amount, locked.currency)}."
    notify(
        [locked.payer, locked.recipient],
        actor=actor,
        verb="settlement_reverse",
        message=message,
        path=f"/settlements/{locked.pk}/",
        email_kind="settlement",
    )
    record_activity(
        actor=actor,
        verb="settlement_reverse",
        summary=message,
        group=locked.group,
        path=f"/settlements/{locked.pk}/",
        viewer_ids=None if locked.group_id else [locked.payer_id, locked.recipient_id],
    )
    return reversal


def _refresh_debt_status(debt):
    paid = debt.repayments.filter(status=InformalDebtRepayment.Status.RECORDED).aggregate(total=Sum("amount"))[
        "total"
    ] or ZERO
    if debt.status == InformalDebt.Status.VOID:
        return debt
    debt.status = InformalDebt.Status.SETTLED if paid >= debt.amount else InformalDebt.Status.OPEN
    debt.save(update_fields=["status"])
    return debt


def record_debt(*, actor, creditor, debtor, amount, currency, borrowed_on, notes="", client_token, request=None):
    if creditor.id == debtor.id:
        raise DomainError("Choose two different people.")
    if actor.id not in {creditor.id, debtor.id}:
        raise AuthorizationError("You can record a loan you are part of.")
    if not are_friends(creditor, debtor) and actor.id not in {creditor.id, debtor.id}:
        raise AuthorizationError()
    if not are_friends(creditor, debtor):
        raise DomainError("Record a loan with a friend.")
    amount = quantize_amount(amount, currency)
    token = _uuid(client_token)
    existing = InformalDebt.objects.filter(created_by=actor, client_token=token).first()
    if existing:
        return existing
    try:
        with transaction.atomic():
            debt = InformalDebt.objects.create(
                creditor=creditor,
                debtor=debtor,
                amount=amount,
                currency=currency,
                borrowed_on=borrowed_on,
                notes=(notes or "")[:4000],
                created_by=actor,
                client_token=token,
            )
            write_audit(
                actor=actor,
                action="debt_record",
                instance=debt,
                after={"amount": str(amount), "currency": currency},
                request=request,
            )
    except IntegrityError:
        return InformalDebt.objects.get(created_by=actor, client_token=token)
    notify(
        [creditor, debtor],
        actor=actor,
        verb="debt_record",
        message=f"{actor.display_name} recorded a loan of {format_money(amount, currency)}.",
        path=f"/debts/{debt.pk}/",
        email_kind="settlement",
    )
    return debt


def repay_debt(debt, *, actor, amount, paid_on, note="", client_token, request=None):
    if debt.status == InformalDebt.Status.VOID:
        raise DomainError("This loan was voided.")
    if actor.id not in {debt.creditor_id, debt.debtor_id, debt.created_by_id}:
        raise AuthorizationError("You cannot record a payment on this loan.")
    amount = quantize_amount(amount, debt.currency)
    token = _uuid(client_token)
    existing = InformalDebtRepayment.objects.filter(recorded_by=actor, client_token=token).first()
    if existing:
        return existing
    with transaction.atomic():
        locked = InformalDebt.objects.select_for_update().get(pk=debt.pk)
        paid = locked.repayments.filter(status=InformalDebtRepayment.Status.RECORDED).aggregate(total=Sum("amount"))[
            "total"
        ] or ZERO
        outstanding = locked.amount - paid
        if amount > outstanding:
            raise DomainError(
                f"The outstanding loan is {format_money(outstanding, locked.currency)}.",
                field="amount",
            )
        try:
            with transaction.atomic():
                repayment = InformalDebtRepayment.objects.create(
                    debt=locked,
                    amount=amount,
                    paid_on=paid_on,
                    note=(note or "")[:255],
                    recorded_by=actor,
                    client_token=token,
                )
        except IntegrityError:
            return InformalDebtRepayment.objects.get(recorded_by=actor, client_token=token)
        _refresh_debt_status(locked)
        write_audit(
            actor=actor,
            action="debt_repay",
            instance=repayment,
            after={"amount": str(amount)},
            request=request,
        )
    return repayment


def reverse_debt_repayment(repayment, *, actor, reason, request=None):
    reason = (reason or "").strip()
    if not reason:
        raise DomainError("Enter a reason.", field="reason")
    debt = repayment.debt
    if actor.id not in {debt.creditor_id, debt.debtor_id, repayment.recorded_by_id}:
        raise AuthorizationError("You cannot reverse this payment.")
    with transaction.atomic():
        locked = InformalDebtRepayment.objects.select_for_update().get(pk=repayment.pk)
        if locked.status != InformalDebtRepayment.Status.RECORDED:
            raise DomainError("This payment was already reversed.")
        locked.status = InformalDebtRepayment.Status.REVERSED
        locked.reversed_by = actor
        locked.reversed_at = timezone.now()
        locked.reversal_reason = reason[:255]
        locked.save()
        _refresh_debt_status(locked.debt)
        write_audit(actor=actor, action="debt_repayment_reverse", instance=locked, reason=reason, request=request)
    return locked


def void_debt(debt, *, actor, reason, request=None):
    reason = (reason or "").strip()
    if not reason:
        raise DomainError("Enter a reason.", field="reason")
    if actor.id not in {debt.creditor_id, debt.debtor_id, debt.created_by_id}:
        raise AuthorizationError("You cannot void this loan.")
    with transaction.atomic():
        locked = InformalDebt.objects.select_for_update().get(pk=debt.pk)
        if locked.status == InformalDebt.Status.VOID:
            raise DomainError("This loan is already voided.")
        locked.status = InformalDebt.Status.VOID
        locked.void_reason = reason[:255]
        locked.save(update_fields=["status", "void_reason"])
        write_audit(actor=actor, action="debt_void", instance=locked, reason=reason, request=request)
    return locked


def debt_outstanding(debt):
    paid = debt.repayments.filter(status=InformalDebtRepayment.Status.RECORDED).aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"]
    return debt.amount - paid
