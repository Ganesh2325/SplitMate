from django.contrib import admin

from apps.friends.models import FriendInvitation, Friendship


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ("requester", "addressee", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("requester__username", "addressee__username")
    raw_id_fields = ("user_low", "user_high", "requester", "addressee")


@admin.register(FriendInvitation)
class FriendInvitationAdmin(admin.ModelAdmin):
    list_display = ("inviter", "email", "status", "expires_at")
    list_filter = ("status",)
    search_fields = ("email", "inviter__username")
    raw_id_fields = ("inviter", "accepted_user")
