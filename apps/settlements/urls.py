from django.urls import path

from apps.settlements import views

app_name = "settlements"

urlpatterns = [
    path("balances/", views.balance_list, name="balances"),
    path("balances/with/<int:pk>/", views.balance_with, name="with"),
    path("settle/", views.settle, name="settle"),
    path("settlements/", views.settlement_list, name="history"),
    path("settlements/<int:pk>/", views.settlement_detail, name="detail"),
    path("settlements/<int:pk>/reverse/", views.settlement_reverse, name="reverse"),
    path("debts/", views.debt_list, name="debts"),
    path("debts/add/", views.debt_create, name="debt_add"),
    path("debts/<int:pk>/", views.debt_detail, name="debt_detail"),
    path("debts/<int:pk>/pay/", views.debt_repay, name="debt_pay"),
    path("debts/repayments/<int:pk>/reverse/", views.debt_repayment_reverse, name="debt_reverse"),
]
