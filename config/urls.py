from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path


def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("", include("apps.accounts.urls")),
    path("friends/", include("apps.friends.urls")),
    path("groups/", include("apps.groups.urls")),
    path("expenses/", include("apps.expenses.urls")),
    path("", include("apps.settlements.urls")),
    path("", include("apps.reports.urls")),
    path("recurring/", include("apps.recurring.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("categories/", include("apps.categories.urls")),
    path("budgets/", include("apps.budgets.urls")),
]
