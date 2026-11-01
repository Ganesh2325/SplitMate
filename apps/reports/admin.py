from django.contrib import admin

from apps.reports.models import DataExportJob, ExchangeRate


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ("base_currency", "quote_currency", "rate", "effective_on", "source")
    list_filter = ("base_currency", "quote_currency")


@admin.register(DataExportJob)
class ExportJobAdmin(admin.ModelAdmin):
    list_display = ("user", "export_format", "status", "row_count", "created_at")
    raw_id_fields = ("user",)

    def has_change_permission(self, request, obj=None):
        return False
