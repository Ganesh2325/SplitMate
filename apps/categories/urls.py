from django.urls import path

from apps.categories import views

app_name = "categories"

urlpatterns = [
    path("", views.category_list, name="list"),
    path("add/", views.category_create, name="add"),
    path("<int:pk>/delete/", views.category_delete, name="delete"),
]
