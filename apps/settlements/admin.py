from django.contrib import admin

from apps.settlements.models import InformalDebt, InformalDebtRepayment, Settlement, SettlementReversal


@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = ("payer", "recipient", "amount", "currency", "settled_on", "status", "group")
    list_filter = ("status", "currency", "method")
    search_fields = ("payer__username", "recipient__username", "reference")
    raw_id_fields = ("payer", "recipient", "group", "created_by")
    readonly_fields = ("amount", "currency", "status", "client_token", "is_advance", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SettlementReversal)
class ReversalAdmin(admin.ModelAdmin):
    list_display = ("settlement", "actor", "created_at")
    readonly_fields = ("settlement", "actor", "reason", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InformalDebt)
class DebtAdmin(admin.ModelAdmin):
    list_display = ("creditor", "debtor", "amount", "currency", "status", "borrowed_on")
    list_filter = ("status", "currency")
    search_fields = ("creditor__username", "debtor__username")
    raw_id_fields = ("creditor", "debtor", "created_by")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InformalDebtRepayment)
class DebtRepaymentAdmin(admin.ModelAdmin):
    list_display = ("debt", "amount", "paid_on", "status")
    raw_id_fields = ("debt", "recorded_by", "reversed_by")

    def has_delete_permission(self, request, obj=None):
        return False
