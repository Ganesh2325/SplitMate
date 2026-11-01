from django.urls import path

from apps.reports import views

app_name = "reports"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("reports/", views.reports, name="home"),
    path("reports/export/<str:export_format>/", views.export_report, name="export"),
]
