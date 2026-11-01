from django.urls import path

from apps.budgets import views

app_name = "budgets"

urlpatterns = [
    path("", views.budget_list, name="list"),
    path("add/", views.budget_create, name="add"),
    path("<int:pk>/toggle/", views.budget_toggle, name="toggle"),
]
