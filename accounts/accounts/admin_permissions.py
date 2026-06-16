from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from .permissions import (
    ADMIN_ROLES,
    CLINICAL_READ_ROLES,
    DEPARTMENT_HEAD_ROLES,
    DOCTOR_ROLES,
    NURSE_ROLES,
    effective_role,
)


MODEL_VIEW_ROLES = {
    "auth.group": ADMIN_ROLES,
    "auth.user": ADMIN_ROLES,
    "accounts.user": ADMIN_ROLES,
    "accounts.department": ADMIN_ROLES,
    "audit.auditlog": ADMIN_ROLES,
    "followups.followupchain": CLINICAL_READ_ROLES,
    "followups.followuptask": CLINICAL_READ_ROLES,
    "followups.interventionrecord": CLINICAL_READ_ROLES,
    "followups.systemreminder": CLINICAL_READ_ROLES,
    "integrations.integrationsource": ADMIN_ROLES,
    "integrations.integrationtask": ADMIN_ROLES,
    "integrations.fieldmapping": ADMIN_ROLES,
    "integrations.importbatch": ADMIN_ROLES | NURSE_ROLES,
    "integrations.importtemplate": ADMIN_ROLES | NURSE_ROLES,
    "labs.labresult": CLINICAL_READ_ROLES,
    "labs.ogttoutcome": CLINICAL_READ_ROLES,
    "maternal_records.maternalrecord": CLINICAL_READ_ROLES,
    "maternal_records.mergerecord": DOCTOR_ROLES | DEPARTMENT_HEAD_ROLES,
    "maternal_records.recorddeletionrequest": DOCTOR_ROLES | ADMIN_ROLES,
    "maternal_records.fieldsource": CLINICAL_READ_ROLES,
    "maternal_records.recordaccessgrant": DOCTOR_ROLES | DEPARTMENT_HEAD_ROLES | ADMIN_ROLES,
    "risk.riskassessment": CLINICAL_READ_ROLES,
    "risk.preexclusionrecord": CLINICAL_READ_ROLES,
    "system_config.modelversion": ADMIN_ROLES,
    "system_config.ruleconfig": ADMIN_ROLES,
    "system_config.thresholdconfig": ADMIN_ROLES,
    "system_config.retentionpolicy": ADMIN_ROLES,
    "system_config.systemnotice": ADMIN_ROLES,
}


MODEL_WRITE_ROLES = {
    "auth.group": ADMIN_ROLES,
    "auth.user": ADMIN_ROLES,
    "accounts.user": ADMIN_ROLES,
    "accounts.department": ADMIN_ROLES,
    "followups.followupchain": DOCTOR_ROLES | NURSE_ROLES,
    "followups.followuptask": DOCTOR_ROLES | NURSE_ROLES,
    "followups.interventionrecord": DOCTOR_ROLES,
    "followups.systemreminder": set(),
    "integrations.integrationsource": ADMIN_ROLES,
    "integrations.integrationtask": ADMIN_ROLES,
    "integrations.fieldmapping": ADMIN_ROLES,
    "integrations.importbatch": ADMIN_ROLES,
    "integrations.importtemplate": ADMIN_ROLES,
    "labs.labresult": DOCTOR_ROLES | NURSE_ROLES,
    "labs.ogttoutcome": DOCTOR_ROLES,
    "maternal_records.maternalrecord": DOCTOR_ROLES,
    "maternal_records.mergerecord": DOCTOR_ROLES,
    "maternal_records.recorddeletionrequest": ADMIN_ROLES,
    "maternal_records.fieldsource": set(),
    "maternal_records.recordaccessgrant": DOCTOR_ROLES | ADMIN_ROLES,
    "risk.riskassessment": DOCTOR_ROLES,
    "risk.preexclusionrecord": DOCTOR_ROLES,
    "system_config.modelversion": ADMIN_ROLES,
    "system_config.ruleconfig": ADMIN_ROLES,
    "system_config.thresholdconfig": ADMIN_ROLES,
    "system_config.retentionpolicy": ADMIN_ROLES,
    "system_config.systemnotice": ADMIN_ROLES,
}


def admin_model_key(model):
    if model is get_user_model():
        return "auth.user"
    return f"{model._meta.app_label}.{model._meta.model_name}"


def user_role(user):
    return effective_role(user)


def can_access_admin(user):
    return bool(getattr(user, "is_active", False) and effective_role(user) in ADMIN_ROLES)


def can_view_admin_model(user, model):
    if getattr(user, "is_superuser", False):
        return True
    role = user_role(user)
    key = admin_model_key(model)
    app_label, model_name = key.split(".", 1)
    return (
        role in MODEL_VIEW_ROLES.get(key, set())
        or user.has_perm(f"{app_label}.view_{model_name}")
        or user.has_perm(f"{app_label}.change_{model_name}")
    )


def can_write_admin_model(user, model):
    if getattr(user, "is_superuser", False):
        return True
    role = user_role(user)
    key = admin_model_key(model)
    app_label, model_name = key.split(".", 1)
    return (
        role in MODEL_WRITE_ROLES.get(key, set())
        or user.has_perm(f"{app_label}.add_{model_name}")
        or user.has_perm(f"{app_label}.change_{model_name}")
        or user.has_perm(f"{app_label}.delete_{model_name}")
    )


class RoleBasedAdminAuthenticationForm(AdminAuthenticationForm):
    def confirm_login_allowed(self, user):
        if not can_access_admin(user):
            raise ValidationError("该账号没有管理后台访问权限。", code="invalid_login")


class RoleBasedAdminMixin:
    def has_module_permission(self, request):
        return can_view_admin_model(request.user, self.model)

    def has_view_permission(self, request, obj=None):
        return can_view_admin_model(request.user, self.model)

    def has_add_permission(self, request):
        return can_write_admin_model(request.user, self.model)

    def has_change_permission(self, request, obj=None):
        return can_write_admin_model(request.user, self.model)

    def has_delete_permission(self, request, obj=None):
        return can_write_admin_model(request.user, self.model)


class RecordScopedAdminMixin(RoleBasedAdminMixin):
    maternal_record_lookup = None

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not self.maternal_record_lookup or getattr(request.user, "is_superuser", False):
            return queryset
        from maternal_records.services import visible_records_for_user

        visible_records = visible_records_for_user(request.user)
        if self.maternal_record_lookup == "self":
            return queryset.filter(pk__in=visible_records.values("pk"))
        return queryset.filter(**{f"{self.maternal_record_lookup}__in": visible_records})
