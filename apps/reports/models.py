from django.conf import settings
from django.db import models

from apps.common.constants import CURRENCY_CHOICES


class ExchangeRate(models.Model):
    """Stored for the record. Group accounting does not convert currencies."""

    base_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES)
    quote_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES)
    rate = models.DecimalField(max_digits=18, decimal_places=8)
    effective_on = models.DateField()
    source = models.CharField(max_length=80, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exchange_rates_added",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["base_currency", "quote_currency", "effective_on"])]


class DataExportJob(models.Model):
    class Format(models.TextChoices):
        CSV = "csv", "CSV"
        XLSX = "xlsx", "Excel"
        PDF = "pdf", "PDF"

    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="export_jobs"
    )
    export_format = models.CharField(max_length=8, choices=Format.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.COMPLETED)
    filters = models.JSONField(default=dict)
    row_count = models.PositiveIntegerField(default=0)
    message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
