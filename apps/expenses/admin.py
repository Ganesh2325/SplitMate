from django.contrib import admin

from apps.expenses.models import (
    Expense,
    ExpenseAttachment,
    ExpenseComment,
    ExpenseItem,
    ExpensePayer,
    ExpenseRevision,
    ExpenseShare,
    ExpenseTemplate,
    SavedSplitPreference,
)


class PayerInline(admin.TabularInline):
    model = ExpensePayer
    extra = 0
    can_delete = False
    readonly_fields = ("user", "amount")

    def has_add_permission(self, request, obj=None):
        return False


class ShareInline(admin.TabularInline):
    model = ExpenseShare
    extra = 0
    can_delete = False
    readonly_fields = ("user", "amount", "percentage", "weight")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("description", "amount", "currency", "expense_date", "status", "group", "created_by")
    list_filter = ("status", "currency", "split_method")
    search_fields = ("description", "created_by__username", "group__name")
    raw_id_fields = ("group", "created_by", "category", "voided_by")
    readonly_fields = (
        "amount",
        "currency",
        "split_method",
        "status",
        "client_token",
        "created_at",
        "updated_at",
        "voided_at",
        "void_reason",
    )
    inlines = [PayerInline, ShareInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExpenseRevision)
class RevisionAdmin(admin.ModelAdmin):
    list_display = ("expense", "number", "actor", "created_at")
    readonly_fields = ("expense", "number", "actor", "reason", "before", "after", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExpenseComment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("expense", "author", "created_at", "hidden_at")
    search_fields = ("body", "author__username")
    raw_id_fields = ("expense", "author", "hidden_by")


@admin.register(ExpenseAttachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "expense", "uploaded_by", "size", "created_at")
    raw_id_fields = ("expense", "uploaded_by")


@admin.register(ExpenseItem)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("description", "expense", "line_total")
    raw_id_fields = ("expense",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(ExpenseTemplate)
admin.site.register(SavedSplitPreference)
