from django.conf import settings
from django.db import models

from apps.common.constants import CURRENCY_CHOICES, FREQUENCIES, SPLIT_METHODS


class RecurringExpense(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        CANCELLED = "cancelled", "Cancelled"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recurring_expenses"
    )
    group = models.ForeignKey(
        "groups.Group",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="recurring_expenses",
    )
    category = models.ForeignKey(
        "categories.ExpenseCategory",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="recurring_expenses",
    )
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="INR")
    split_method = models.CharField(max_length=16, choices=SPLIT_METHODS)
    frequency = models.CharField(max_length=16, choices=FREQUENCIES)
    anchor_day = models.PositiveSmallIntegerField(default=1)
    start_date = models.DateField()
    next_occurrence = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["status", "next_occurrence"])]


class RecurringExpenseOccurrence(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        GENERATED = "generated", "Generated"
        FAILED = "failed", "Failed"

    recurring = models.ForeignKey(
        RecurringExpense, on_delete=models.CASCADE, related_name="occurrences"
    )
    scheduled_for = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    expense = models.ForeignKey(
        "expenses.Expense",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="recurring_occurrences",
    )
    message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["recurring", "scheduled_for"], name="unique_recurring_occurrence"
            ),
        ]
        indexes = [models.Index(fields=["status", "scheduled_for"])]
