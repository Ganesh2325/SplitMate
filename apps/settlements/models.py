import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.constants import CURRENCY_CHOICES, PAYMENT_METHODS


class Settlement(models.Model):
    class Status(models.TextChoices):
        RECORDED = "recorded", "Recorded"
        REVERSED = "reversed", "Reversed"

    payer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="repayments_made"
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="repayments_received"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES)
    settled_on = models.DateField()
    method = models.CharField(max_length=16, choices=PAYMENT_METHODS, default="cash")
    reference = models.CharField(max_length=80, blank=True)
    note = models.CharField(max_length=255, blank=True)
    group = models.ForeignKey(
        "groups.Group", null=True, blank=True, on_delete=models.PROTECT, related_name="settlements"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="settlements_recorded"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECORDED)
    is_advance = models.BooleanField(default=False)
    client_token = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="settlement_amount_positive"),
            models.UniqueConstraint(
                fields=["created_by", "client_token"], name="unique_settlement_client_token"
            ),
        ]
        indexes = [
            models.Index(fields=["group", "status", "currency"]),
            models.Index(fields=["payer", "status"]),
            models.Index(fields=["recipient", "status"]),
            models.Index(fields=["settled_on"]),
        ]


class SettlementReversal(models.Model):
    settlement = models.OneToOneField(
        Settlement, on_delete=models.PROTECT, related_name="reversal"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="settlement_reversals"
    )
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)


class InformalDebt(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        SETTLED = "settled", "Settled"
        VOID = "void", "Voided"

    creditor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="debts_lent"
    )
    debtor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="debts_borrowed"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="INR")
    borrowed_on = models.DateField()
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="debts_recorded"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    void_reason = models.CharField(max_length=255, blank=True)
    client_token = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="debt_amount_positive"),
            models.UniqueConstraint(
                fields=["created_by", "client_token"], name="unique_debt_client_token"
            ),
        ]
        indexes = [models.Index(fields=["creditor", "status"]), models.Index(fields=["debtor", "status"])]


class InformalDebtRepayment(models.Model):
    class Status(models.TextChoices):
        RECORDED = "recorded", "Recorded"
        REVERSED = "reversed", "Reversed"

    debt = models.ForeignKey(InformalDebt, on_delete=models.PROTECT, related_name="repayments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_on = models.DateField()
    note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="debt_repayments_recorded"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECORDED)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="debt_repayments_reversed",
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversal_reason = models.CharField(max_length=255, blank=True)
    client_token = models.UUIDField(default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="debt_repayment_positive"),
            models.UniqueConstraint(
                fields=["recorded_by", "client_token"], name="unique_debt_repayment_token"
            ),
        ]
