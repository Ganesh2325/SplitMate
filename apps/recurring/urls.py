from django.urls import path

from apps.recurring import views

app_name = "recurring"

urlpatterns = [
    path("", views.recurring_list, name="list"),
    path("add/", views.recurring_create, name="add"),
    path("<int:pk>/status/", views.recurring_status, name="status"),
]
