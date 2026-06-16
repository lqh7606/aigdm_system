import uuid

from .models import AuditLog


def write_audit_log(
    request=None,
    action=AuditLog.Action.VIEW,
    target_type="",
    target_id="",
    summary="",
    metadata=None,
    before=None,
    after=None,
    success=True,
    failure_reason="",
    confirmation=None,
    request_id="",
):
    user = None
    ip_address = None
    resolved_request_id = request_id
    if request is not None:
        user = request.user if getattr(request.user, "is_authenticated", False) else None
        ip_address = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR"))
        if ip_address and "," in ip_address:
            ip_address = ip_address.split(",", 1)[0].strip()
        resolved_request_id = (
            request_id
            or request.META.get("HTTP_X_REQUEST_ID")
            or getattr(request, "request_id", "")
            or uuid.uuid4().hex
        )
    return AuditLog.objects.create(
        user=user,
        action=action,
        target_type=target_type,
        target_id=str(target_id or ""),
        summary=summary,
        ip_address=ip_address,
        request_id=resolved_request_id,
        before_json=before or {},
        after_json=after or {},
        success=success,
        failure_reason=failure_reason,
        confirmation_json=confirmation or {},
        metadata_json=metadata or {},
    )
