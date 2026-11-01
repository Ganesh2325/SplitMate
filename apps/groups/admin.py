from django.contrib import admin

from apps.groups.models import Group, GroupInvitation, GroupMembership, GroupMembershipEvent


class MembershipInline(admin.TabularInline):
    model = GroupMembership
    extra = 0
    raw_id_fields = ("user",)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "group_type", "currency", "created_by", "archived_at")
    list_filter = ("group_type", "currency")
    search_fields = ("name",)
    raw_id_fields = ("created_by",)
    inlines = [MembershipInline]


@admin.register(GroupMembership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("group", "user", "role", "status")
    list_filter = ("role", "status")
    search_fields = ("group__name", "user__username")
    raw_id_fields = ("group", "user")


@admin.register(GroupInvitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("group", "invitee", "email", "status", "expires_at")
    list_filter = ("status",)
    search_fields = ("group__name", "email", "invitee__username")
    raw_id_fields = ("group", "inviter", "invitee")


@admin.register(GroupMembershipEvent)
class MembershipEventAdmin(admin.ModelAdmin):
    list_display = ("group", "user", "actor", "action", "created_at")
    search_fields = ("group__name", "user__username")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
