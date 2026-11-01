def write_audit(*, actor, action, instance, before=None, after=None, reason="", request=None):
    from apps.audit.models import AuditLog

    user = actor if getattr(actor, "is_authenticated", False) else None
    if user is not None and not getattr(user, "pk", None):
        user = None
    AuditLog.objects.create(
        actor=user,
        action=action,
        object_type=instance._meta.label,
        object_id=str(instance.pk),
        before=before,
        after=after,
        reason=(reason or "")[:255],
        request_id=(getattr(request, "request_id", "") or "")[:64],
    )
