from django.contrib import admin

from apps.notifications.models import Activity, Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "verb", "message", "read_at", "created_at")
    list_filter = ("verb",)
    search_fields = ("recipient__username", "message")
    raw_id_fields = ("recipient", "actor")


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("actor", "verb", "summary", "created_at")
    search_fields = ("summary", "actor__username")
    raw_id_fields = ("actor", "group")

    def has_change_permission(self, request, obj=None):
        return False
