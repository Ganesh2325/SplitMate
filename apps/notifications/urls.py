from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("<int:pk>/", views.notification_open, name="open"),
    path("read-all/", views.notification_read_all, name="read_all"),
]
