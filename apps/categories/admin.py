from django.contrib import admin

from apps.categories.models import ExpenseCategory


@admin.register(ExpenseCategory)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_system", "owner", "group")
    list_filter = ("is_system",)
    search_fields = ("name", "slug")
    raw_id_fields = ("owner", "group")
