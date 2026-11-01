from django.urls import path

from apps.groups import views

app_name = "groups"

urlpatterns = [
    path("", views.group_list, name="list"),
    path("create/", views.group_create, name="create"),
    path("invite/<str:token>/", views.group_invite_link, name="invite_link"),
    path("invitations/<int:pk>/", views.group_invite_respond, name="invite_respond"),
    path("<int:pk>/", views.group_detail, name="detail"),
    path("<int:pk>/image/", views.group_image, name="image"),
    path("<int:pk>/members/", views.group_members, name="members"),
    path("<int:pk>/invite/", views.group_invite, name="invite"),
    path("<int:pk>/members/<int:user_id>/", views.group_member_action, name="member_action"),
    path("<int:pk>/leave/", views.group_leave, name="leave"),
    path("<int:pk>/settings/", views.group_settings, name="settings"),
    path("<int:pk>/archive/", views.group_archive, name="archive"),
    path("<int:pk>/balances/", views.group_balances, name="balances"),
    path("<int:pk>/expenses/", views.group_expenses, name="expenses"),
]
