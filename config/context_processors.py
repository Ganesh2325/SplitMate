def shell(request):
    unread = 0
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        from apps.notifications.models import Notification

        unread = Notification.objects.filter(recipient=user, read_at__isnull=True).count()
    theme = "system"
    if user is not None and user.is_authenticated:
        theme = user.theme or "system"
    return {
        "unread_notifications": unread,
        "user_theme": theme,
        "site_name": "SplitMate",
    }
