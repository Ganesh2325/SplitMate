from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.notifications.models import Notification


@login_required
def notification_list(request):
    queryset = Notification.objects.filter(recipient=request.user).select_related("actor")
    page = Paginator(queryset, 20).get_page(request.GET.get("page"))
    return render(request, "notifications/list.html", {"page_obj": page, "notifications": page.object_list})


@login_required
def notification_open(request, pk):
    item = Notification.objects.filter(pk=pk, recipient=request.user).first()
    if item is None:
        return redirect("notifications:list")
    if item.read_at is None:
        item.read_at = timezone.now()
        item.save(update_fields=["read_at"])
    return redirect(item.path or "notifications:list")


@login_required
@require_POST
def notification_read_all(request):
    Notification.objects.filter(recipient=request.user, read_at__isnull=True).update(read_at=timezone.now())
    return redirect("notifications:list")
