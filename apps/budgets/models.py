from django.conf import settings
from django.db import models

from apps.common.constants import CURRENCY_CHOICES


class Budget(models.Model):
    class Scope(models.TextChoices):
        PERSONAL = "personal", "Personal shares"
        GROUP = "group", "Group spending"

    class Period(models.TextChoices):
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"
        CUSTOM = "custom", "Custom range"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="budgets"
    )
    group = models.ForeignKey(
        "groups.Group", null=True, blank=True, on_delete=models.CASCADE, related_name="budgets"
    )
    category = models.ForeignKey(
        "categories.ExpenseCategory",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="budgets",
    )
    name = models.CharField(max_length=80)
    limit_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="INR")
    scope = models.CharField(max_length=16, choices=Scope.choices, default=Scope.PERSONAL)
    period = models.CharField(max_length=16, choices=Period.choices, default=Period.MONTHLY)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["owner", "is_active"])]


class BudgetAlert(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="alerts")
    period_key = models.CharField(max_length=32)
    threshold = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["budget", "period_key", "threshold"], name="unique_budget_alert"
            ),
        ]
