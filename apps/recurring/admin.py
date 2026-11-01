from django.contrib import admin

from apps.recurring.models import RecurringExpense, RecurringExpenseOccurrence


@admin.register(RecurringExpense)
class RecurringAdmin(admin.ModelAdmin):
    list_display = ("description", "amount", "currency", "frequency", "status", "next_occurrence", "owner")
    list_filter = ("status", "frequency", "currency")
    search_fields = ("description", "owner__username")
    raw_id_fields = ("owner", "group", "category")


@admin.register(RecurringExpenseOccurrence)
class OccurrenceAdmin(admin.ModelAdmin):
    list_display = ("recurring", "scheduled_for", "status", "expense")
    list_filter = ("status",)
    raw_id_fields = ("recurring", "expense")

    def has_delete_permission(self, request, obj=None):
        return False
