import csv
from io import StringIO

from django.http import HttpResponse
from django.shortcuts import render

from accounts.permissions import PermissionAction, has_action_permission, permission_denied_response
from common.api import error, ok

from .models import AuditLog


def _can_view_audit_logs(user):
    return has_action_permission(user, PermissionAction.VIEW_AUDIT_LOG)


def audit_list(request):
    if not _can_view_audit_logs(request.user):
        return permission_denied_response(request, PermissionAction.VIEW_AUDIT_LOG, message="没有权限访问审计日志。")
    logs = AuditLog.objects.select_related("user")[:100]
    return render(request, "audit/list.html", {"logs": logs})


def _audit_rows(logs):
    return [
        {
            "时间": item.created_at,
            "请求ID": item.request_id,
            "用户": item.user.username if item.user else "系统",
            "操作": item.get_action_display(),
            "对象": item.target_type,
            "对象ID": item.target_id,
            "摘要": item.summary,
            "IP": item.ip_address,
            "成功": item.success,
            "失败原因": item.failure_reason,
            "二次确认": item.confirmation_json,
            "扩展信息": item.metadata_json,
        }
        for item in logs
    ]


def audit_logs_api(request):
    if request.method != "GET":
        return error("不支持的请求方法。", status=405, code="METHOD_NOT_ALLOWED")
    if not _can_view_audit_logs(request.user):
        return permission_denied_response(request, PermissionAction.VIEW_AUDIT_LOG, message="没有权限访问审计日志。")
    rows = _audit_rows(AuditLog.objects.select_related("user")[:200])
    if request.GET.get("format") == "csv":
        if not has_action_permission(request.user, PermissionAction.EXPORT_AUDIT_LOG):
            return permission_denied_response(request, PermissionAction.EXPORT_AUDIT_LOG, message="没有权限导出审计日志。")
        buffer = StringIO()
        fieldnames = ["时间", "请求ID", "用户", "操作", "对象", "对象ID", "摘要", "IP", "成功", "失败原因", "二次确认", "扩展信息"]
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        response = HttpResponse("\ufeff" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="aigdm_audit_logs.csv"'
        return response
    return ok(rows)
