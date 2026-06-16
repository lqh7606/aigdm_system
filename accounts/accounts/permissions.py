from dataclasses import dataclass

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from audit.models import AuditLog
from audit.services import write_audit_log
from common.api import error

from .models import UserProfile


class PermissionAction:
    VIEW_RECORDS = "view_records"
    VIEW_LABS = "view_labs"
    VIEW_RISK = "view_risk"
    VIEW_FOLLOWUPS = "view_followups"
    VIEW_INTEGRATIONS = "view_integrations"
    VIEW_SYSTEM_CONFIG = "view_system_config"
    VIEW_AUDIT_LOG = "view_audit_log"
    CREATE_RECORD = "create_record"
    UPDATE_RECORD = "update_record"
    REQUEST_RECORD_DELETION = "request_record_deletion"
    APPROVE_RECORD_DELETION = "approve_record_deletion"
    MERGE_RECORD = "merge_record"
    CREATE_LAB_RESULT = "create_lab_result"
    CONFIRM_LAB_ABNORMAL = "confirm_lab_abnormal"
    CONFIRM_OGTT_OUTCOME = "confirm_ogtt_outcome"
    RUN_RISK_ASSESSMENT = "run_risk_assessment"
    EXECUTE_FOLLOWUP_TASK = "execute_followup_task"
    CONFIRM_FOLLOWUP_OUTCOME = "confirm_followup_outcome"
    UPLOAD_EXCEL_IMPORT = "upload_excel_import"
    RUN_INTEGRATION_TASK = "run_integration_task"
    SUPPLEMENT_WHITELIST_FIELDS = "supplement_whitelist_fields"
    MANAGE_USERS = "manage_users"
    MANAGE_MODEL_CONFIG = "manage_model_config"
    MANAGE_SYSTEM_CONFIG = "manage_system_config"
    MANAGE_SYSTEM_NOTICE = "manage_system_notice"
    EXPORT_AUDIT_LOG = "export_audit_log"


FORMAL_ROLES = {
    UserProfile.Role.DOCTOR,
    UserProfile.Role.NURSE,
    UserProfile.Role.DEPARTMENT_HEAD,
    UserProfile.Role.ADMIN,
}
ALL_COMPATIBLE_ROLES = FORMAL_ROLES | {UserProfile.Role.MANAGER}
LEGACY_ROLE_ALIASES = {UserProfile.Role.MANAGER: UserProfile.Role.DEPARTMENT_HEAD}

DOCTOR_ROLES = {UserProfile.Role.DOCTOR}
NURSE_ROLES = {UserProfile.Role.NURSE}
DEPARTMENT_HEAD_ROLES = {UserProfile.Role.DEPARTMENT_HEAD}
ADMIN_ROLES = {UserProfile.Role.ADMIN}
CLINICAL_READ_ROLES = DOCTOR_ROLES | NURSE_ROLES | DEPARTMENT_HEAD_ROLES


ACTION_ALLOWED_ROLES = {
    PermissionAction.VIEW_RECORDS: CLINICAL_READ_ROLES,
    PermissionAction.VIEW_LABS: CLINICAL_READ_ROLES,
    PermissionAction.VIEW_RISK: CLINICAL_READ_ROLES,
    PermissionAction.VIEW_FOLLOWUPS: CLINICAL_READ_ROLES,
    PermissionAction.VIEW_INTEGRATIONS: ADMIN_ROLES | NURSE_ROLES,
    PermissionAction.VIEW_SYSTEM_CONFIG: ADMIN_ROLES,
    PermissionAction.VIEW_AUDIT_LOG: ADMIN_ROLES,
    PermissionAction.CREATE_RECORD: DOCTOR_ROLES,
    PermissionAction.UPDATE_RECORD: DOCTOR_ROLES | NURSE_ROLES,
    PermissionAction.REQUEST_RECORD_DELETION: DOCTOR_ROLES,
    PermissionAction.APPROVE_RECORD_DELETION: ADMIN_ROLES,
    PermissionAction.MERGE_RECORD: DOCTOR_ROLES,
    PermissionAction.CREATE_LAB_RESULT: DOCTOR_ROLES | NURSE_ROLES,
    PermissionAction.CONFIRM_LAB_ABNORMAL: DOCTOR_ROLES,
    PermissionAction.CONFIRM_OGTT_OUTCOME: DOCTOR_ROLES,
    PermissionAction.RUN_RISK_ASSESSMENT: DOCTOR_ROLES,
    PermissionAction.EXECUTE_FOLLOWUP_TASK: DOCTOR_ROLES | NURSE_ROLES,
    PermissionAction.CONFIRM_FOLLOWUP_OUTCOME: DOCTOR_ROLES,
    PermissionAction.UPLOAD_EXCEL_IMPORT: NURSE_ROLES,
    PermissionAction.RUN_INTEGRATION_TASK: ADMIN_ROLES,
    PermissionAction.SUPPLEMENT_WHITELIST_FIELDS: NURSE_ROLES,
    PermissionAction.MANAGE_USERS: ADMIN_ROLES,
    PermissionAction.MANAGE_MODEL_CONFIG: ADMIN_ROLES,
    PermissionAction.MANAGE_SYSTEM_CONFIG: ADMIN_ROLES,
    PermissionAction.MANAGE_SYSTEM_NOTICE: ADMIN_ROLES,
    PermissionAction.EXPORT_AUDIT_LOG: ADMIN_ROLES,
}


ACTION_PERMISSION_SPECS = {
    PermissionAction.RUN_RISK_ASSESSMENT: ("risk", "riskassessment", "run_risk_assessment"),
    PermissionAction.CONFIRM_LAB_ABNORMAL: ("labs", "labresult", "confirm_lab_abnormal"),
    PermissionAction.CONFIRM_OGTT_OUTCOME: ("labs", "ogttoutcome", "confirm_ogtt_outcome"),
    PermissionAction.EXECUTE_FOLLOWUP_TASK: ("followups", "followuptask", "execute_followup_task"),
    PermissionAction.CONFIRM_FOLLOWUP_OUTCOME: ("followups", "followuptask", "confirm_followup_outcome"),
    PermissionAction.UPLOAD_EXCEL_IMPORT: ("integrations", "importbatch", "upload_excel_import"),
    PermissionAction.SUPPLEMENT_WHITELIST_FIELDS: ("maternal_records", "maternalrecord", "supplement_whitelist_fields"),
    PermissionAction.MANAGE_MODEL_CONFIG: ("system_config", "modelversion", "manage_model_config"),
    PermissionAction.EXPORT_AUDIT_LOG: ("audit", "auditlog", "export_audit_log"),
}


NURSE_RECORD_FIELD_WHITELIST = {
    "last_menstrual_period",
    "current_weight_kg",
    "phone",
    "pregnancy_count",
    "birth_count",
    "systolic_bp",
    "diastolic_bp",
    "height_cm",
    "pre_preg_weight_kg",
}

NURSE_FORBIDDEN_FIELD_NAMES = {
    "diagnosis",
    "diagnosis_conclusion",
    "risk_level",
    "risk_probability",
    "model_output",
    "model_version",
    "doctor_confirmation",
    "confirmation_opinion",
    "diabetes_before_pregnancy",
    "multiple_pregnancy",
}


@dataclass(frozen=True)
class RoleActionSpec:
    action: str
    roles: set


def effective_role(user):
    if not getattr(user, "is_authenticated", False):
        return None
    if getattr(user, "is_superuser", False):
        return UserProfile.Role.ADMIN
    profile = getattr(user, "userprofile", None)
    if not profile:
        return None
    return LEGACY_ROLE_ALIASES.get(profile.role, profile.role)


def raw_role(user):
    profile = getattr(user, "userprofile", None)
    return profile.role if profile else None


def has_action_permission(user, action):
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    role = effective_role(user)
    if role in ACTION_ALLOWED_ROLES.get(action, set()):
        return True
    spec = ACTION_PERMISSION_SPECS.get(action)
    if not spec:
        return False
    app_label, _model_name, codename = spec
    return user.has_perm(f"{app_label}.{codename}")


def permission_specs_for_role(role):
    role = LEGACY_ROLE_ALIASES.get(role, role)
    specs = set()
    for action, roles in ACTION_ALLOWED_ROLES.items():
        if role not in roles:
            continue
        spec = ACTION_PERMISSION_SPECS.get(action)
        if spec:
            specs.add(spec)
    return specs


def visible_records_for_user(user, purpose="clinical"):
    from maternal_records.models import MaternalRecord

    queryset = MaternalRecord.objects.select_related("department", "primary_doctor")
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    if getattr(user, "is_superuser", False):
        return queryset

    profile = getattr(user, "userprofile", None)
    if not profile:
        return queryset.filter(primary_doctor=user)

    role = effective_role(user)
    if role == UserProfile.Role.ADMIN:
        if purpose in {"audit", "troubleshooting"}:
            return queryset
        return queryset.none()

    grant_filter = Q(access_grants__is_active=True, access_grants__user=user)
    if profile.department_id:
        grant_filter |= Q(
            access_grants__is_active=True,
            access_grants__department=profile.department,
            access_grants__role__in=["", role],
        )

    if role == UserProfile.Role.DEPARTMENT_HEAD:
        if not profile.department_id:
            return queryset.none()
        return queryset.filter(department=profile.department).distinct()

    if role == UserProfile.Role.DOCTOR:
        return queryset.filter(Q(primary_doctor=user) | grant_filter).distinct()

    if role == UserProfile.Role.NURSE:
        assigned_filter = Q(followup_chains__tasks__assigned_to=user)
        return queryset.filter(assigned_filter | grant_filter).distinct()

    return queryset.none()


def audit_permission_denied(request, action, target_type="", target_id="", reason=""):
    if request is None:
        return
    write_audit_log(
        request,
        AuditLog.Action.ACCESS_DENIED,
        target_type or "Permission",
        target_id,
        reason or f"权限拒绝：{action}",
        success=False,
        failure_reason=reason or action,
        metadata={"permission_action": action},
    )


def _safe_referer_or_home(request):
    referer = request.META.get("HTTP_REFERER") or ""
    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return referer
    return "/"


def permission_denied_response(request, action, target_type="", target_id="", message="没有权限执行该操作。"):
    audit_permission_denied(request, action, target_type=target_type, target_id=target_id, reason=message)
    if getattr(request, "path", "").startswith("/api/"):
        return error(message, status=403, code="GDM-403-001")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        messages.error(request, message)
        return redirect(_safe_referer_or_home(request))
    return render(
        request,
        "errors/403.html",
        {"error_code": "GDM-403-001", "message": message},
        status=403,
    )


def require_action_or_response(request, action, target_type="", target_id="", message="没有权限执行该操作。"):
    if has_action_permission(request.user, action):
        return None
    return permission_denied_response(request, action, target_type=target_type, target_id=target_id, message=message)


def allowed_record_update_fields_for_user(user):
    role = effective_role(user)
    if role == UserProfile.Role.DOCTOR:
        return None
    if role == UserProfile.Role.NURSE and has_action_permission(user, PermissionAction.SUPPLEMENT_WHITELIST_FIELDS):
        return set(NURSE_RECORD_FIELD_WHITELIST)
    return set()


def validate_record_update_fields(user, submitted_fields):
    allowed = allowed_record_update_fields_for_user(user)
    if allowed is None:
        return True, []
    submitted = {field for field in submitted_fields if field not in {"csrfmiddlewaretoken"}}
    forbidden = sorted((submitted - allowed) | (submitted & NURSE_FORBIDDEN_FIELD_NAMES))
    return not forbidden, forbidden


def permission_context(request):
    user = getattr(request, "user", None)
    return {
        "effective_role": effective_role(user),
        "can_view_records": has_action_permission(user, PermissionAction.VIEW_RECORDS),
        "can_view_labs": has_action_permission(user, PermissionAction.VIEW_LABS),
        "can_view_risk": has_action_permission(user, PermissionAction.VIEW_RISK),
        "can_view_followups": has_action_permission(user, PermissionAction.VIEW_FOLLOWUPS),
        "can_view_integrations": has_action_permission(user, PermissionAction.VIEW_INTEGRATIONS),
        "can_view_system_config": has_action_permission(user, PermissionAction.VIEW_SYSTEM_CONFIG),
        "can_create_record": has_action_permission(user, PermissionAction.CREATE_RECORD),
        "can_update_record": has_action_permission(user, PermissionAction.UPDATE_RECORD),
        "can_request_record_deletion": has_action_permission(user, PermissionAction.REQUEST_RECORD_DELETION),
        "can_merge_record": has_action_permission(user, PermissionAction.MERGE_RECORD),
        "can_create_lab_result": has_action_permission(user, PermissionAction.CREATE_LAB_RESULT),
        "can_confirm_lab": has_action_permission(user, PermissionAction.CONFIRM_LAB_ABNORMAL),
        "can_confirm_ogtt": has_action_permission(user, PermissionAction.CONFIRM_OGTT_OUTCOME),
        "can_run_risk_assessment": has_action_permission(user, PermissionAction.RUN_RISK_ASSESSMENT),
        "can_execute_followup": has_action_permission(user, PermissionAction.EXECUTE_FOLLOWUP_TASK),
        "can_confirm_followup_outcome": has_action_permission(user, PermissionAction.CONFIRM_FOLLOWUP_OUTCOME),
        "can_upload_excel_import": has_action_permission(user, PermissionAction.UPLOAD_EXCEL_IMPORT),
        "can_run_integration_task": has_action_permission(user, PermissionAction.RUN_INTEGRATION_TASK),
        "can_supplement_whitelist_fields": has_action_permission(user, PermissionAction.SUPPLEMENT_WHITELIST_FIELDS),
        "can_manage_admin_backend": has_action_permission(user, PermissionAction.MANAGE_USERS)
        or has_action_permission(user, PermissionAction.MANAGE_MODEL_CONFIG),
    }
