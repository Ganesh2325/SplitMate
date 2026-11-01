from django.urls import path

from apps.expenses import views

app_name = "expenses"

urlpatterns = [
    path("", views.expense_list, name="list"),
    path("add/", views.expense_form, name="add"),
    path("templates/", views.template_list, name="templates"),
    path("templates/add/", views.template_create, name="template_add"),
    path("templates/<int:pk>/use/", views.template_use, name="template_use"),
    path("templates/<int:pk>/delete/", views.template_delete, name="template_delete"),
    path("preferences/add/", views.preference_create, name="preference_add"),
    path("preferences/<int:pk>/delete/", views.preference_delete, name="preference_delete"),
    path("scan/", views.receipt_scan, name="scan"),
    path("<int:pk>/", views.expense_detail, name="detail"),
    path("<int:pk>/edit/", views.expense_form, name="edit"),
    path("<int:pk>/void/", views.expense_void, name="void"),
    path("<int:pk>/duplicate/", views.expense_duplicate, name="duplicate"),
    path("<int:pk>/comments/", views.expense_comment, name="comment"),
    path("<int:pk>/receipts/", views.expense_receipt, name="receipt"),
    path("receipts/<int:pk>/", views.receipt_download, name="receipt_download"),
    path("receipts/<int:pk>/delete/", views.receipt_delete, name="receipt_delete"),
]
