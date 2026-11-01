from django.contrib import admin

from apps.budgets.models import Budget, BudgetAlert


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "scope", "limit_amount", "currency", "is_active")
    list_filter = ("scope", "period", "is_active")
    search_fields = ("name", "owner__username")
    raw_id_fields = ("owner", "group", "category")


@admin.register(BudgetAlert)
class BudgetAlertAdmin(admin.ModelAdmin):
    list_display = ("budget", "period_key", "threshold", "created_at")

    def has_change_permission(self, request, obj=None):
        return False
