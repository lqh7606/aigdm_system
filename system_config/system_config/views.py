from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render

from accounts.permissions import PermissionAction, has_action_permission, permission_denied_response
from audit.models import AuditLog
from audit.services import write_audit_log
from common.api import error, ok, parse_json_body

from .deployment import build_deployment_report
from .model_lifecycle import ModelLifecycleError, activate_model_version
from .models import ModelVersion, RetentionPolicy, RuleConfig, ThresholdConfig


def _is_system_admin(user):
    return has_action_permission(user, PermissionAction.MANAGE_SYSTEM_CONFIG)


def model_versions(request):
    if not _is_system_admin(request.user):
        raise PermissionDenied("没有权限访问模型配置。")
    versions = ModelVersion.objects.all()
    production = versions.filter(status=ModelVersion.Status.PRODUCTION).first()
    return render(
        request,
        "system_config/model_versions.html",
        {
            "versions": versions,
            "production": production,
        },
    )


def config_home(request):
    if not _is_system_admin(request.user):
        raise PermissionDenied("没有权限访问系统配置。")
    return render(
        request,
        "system_config/config_home.html",
        {
            "rules": RuleConfig.objects.all(),
            "thresholds": ThresholdConfig.objects.all(),
            "policies": RetentionPolicy.objects.all(),
        },
    )


def deployment_status(request):
    if not _is_system_admin(request.user):
        raise PermissionDenied("没有权限访问部署状态。")
    return render(
        request,
        "system_config/deployment_status.html",
        {"report": build_deployment_report()},
    )


def model_version_payload(item):
    return {
        "id": item.pk,
        "版本编码": item.version_code,
        "名称": item.display_name,
        "状态": item.get_status_display(),
        "model_type": item.model_type,
        "模型类型": item.get_model_type_display(),
        "文件路径": item.artifact_path,
        "SHA256": item.sha256,
        "启用时间": item.activated_at,
        "前序版本ID": item.predecessor_id,
        "特征结构": item.feature_schema_json,
        "验证报告": item.validation_report_json,
    }


def model_versions_api(request):
    if request.method == "GET":
        if not _is_system_admin(request.user):
            return permission_denied_response(request, PermissionAction.MANAGE_MODEL_CONFIG, message="没有权限访问模型配置。")
        return ok([model_version_payload(item) for item in ModelVersion.objects.all()])
    if request.method != "POST":
        return error("不支持的请求方法。", status=405, code="METHOD_NOT_ALLOWED")
    if not _is_system_admin(request.user):
        return permission_denied_response(request, PermissionAction.MANAGE_MODEL_CONFIG, message="没有权限执行模型配置操作。")
    payload = parse_json_body(request)
    action = payload.get("action")
    try:
        if action == "activate":
            version = get_object_or_404(ModelVersion, pk=payload.get("model_version_id"))
            activated = activate_model_version(version)
            write_audit_log(
                request,
                AuditLog.Action.ACTIVATE_MODEL,
                "ModelVersion",
                activated.pk,
                f"启用模型版本：{activated.version_code}",
                confirmation={"confirmed": bool(payload.get("confirm"))},
                metadata={"action": action, "model_type": activated.model_type},
            )
            return ok(model_version_payload(activated))
        if action == "rollback":
            current = (
                ModelVersion.objects.filter(status=ModelVersion.Status.PRODUCTION)
                .order_by("-activated_at")
                .first()
            )
            if not current or not current.predecessor_id:
                return error("没有可回滚的前序模型版本。", code="NO_PREDECESSOR")
            predecessor = current.predecessor
            predecessor.status = ModelVersion.Status.STAGED
            predecessor.save(update_fields=["status", "updated_at"])
            activated = activate_model_version(predecessor)
            write_audit_log(
                request,
                AuditLog.Action.ACTIVATE_MODEL,
                "ModelVersion",
                activated.pk,
                f"回滚模型版本：{activated.version_code}",
                confirmation={"confirmed": bool(payload.get("confirm"))},
                metadata={"action": action, "model_type": activated.model_type},
            )
            return ok(model_version_payload(activated))
    except ModelLifecycleError as exc:
        return error(str(exc), code="MODEL_LIFECYCLE_ERROR")
    return error("未知模型操作。", code="UNKNOWN_ACTION")


def configs_api(request):
    if request.method != "GET":
        return error("不支持的请求方法。", status=405, code="METHOD_NOT_ALLOWED")
    if not _is_system_admin(request.user):
        return permission_denied_response(request, PermissionAction.MANAGE_SYSTEM_CONFIG, message="没有权限访问系统配置。")
    return ok(
        {
            "规则": [
                {"编码": item.code, "名称": item.name, "启用": item.is_active, "配置": item.config_json}
                for item in RuleConfig.objects.all()
            ],
            "阈值": [
                {
                    "编码": item.code,
                    "名称": item.name,
                    "分类": item.category,
                    "版本": item.version,
                    "范围": item.scope_type,
                    "科室ID": item.department_id,
                    "阈值": str(item.value),
                    "单位": item.unit,
                    "单位规则": item.unit_rule_json,
                    "启用": item.is_active,
                }
                for item in ThresholdConfig.objects.select_related("department").all()
            ],
            "保留策略": [
                {"编码": item.code, "名称": item.name, "保留天数": item.retention_days, "动作": item.action}
                for item in RetentionPolicy.objects.all()
            ],
        }
    )
