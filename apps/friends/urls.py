from django.urls import path

from apps.friends import views

app_name = "friends"

urlpatterns = [
    path("", views.friend_list, name="list"),
    path("add/", views.friend_add, name="add"),
    path("requests/", views.friend_requests, name="requests"),
    path("requests/<int:pk>/", views.friend_respond, name="respond"),
    path("invite/<str:token>/", views.friend_email_link, name="email_invite"),
    path("email-invites/<int:pk>/accept/", views.friend_email_accept, name="email_accept"),
    path("<int:pk>/", views.friend_detail, name="detail"),
    path("<int:pk>/remove/", views.friend_remove, name="remove"),
    path("<int:pk>/block/", views.friend_block, name="block"),
]
