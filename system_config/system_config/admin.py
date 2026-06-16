from django.contrib import admin

from accounts.admin_permissions import RoleBasedAdminMixin
from accounts.permissions import PermissionAction, has_action_permission

from .models import ModelVersion, RetentionPolicy, RuleConfig, SystemNotice, ThresholdConfig


def _can_manage_system_notice(user):
    if getattr(user, "is_superuser", False):
        return True
    return has_action_permission(user, PermissionAction.MANAGE_SYSTEM_NOTICE)


@admin.register(ModelVersion)
class ModelVersionAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("version_code", "model_type", "model_family", "status", "activated_at", "updated_at")
    list_filter = ("status", "model_type", "model_family")
    search_fields = ("version_code", "display_name", "artifact_path")
    readonly_fields = ("created_at", "updated_at", "activated_at", "retired_at")


@admin.register(RuleConfig)
class RuleConfigAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "description")


@admin.register(ThresholdConfig)
class ThresholdConfigAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "value", "unit", "applies_to", "is_active")
    list_filter = ("is_active", "applies_to")
    search_fields = ("code", "name")


@admin.register(RetentionPolicy)
class RetentionPolicyAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "retention_days", "action", "enabled")
    list_filter = ("enabled",)
    search_fields = ("code", "name", "action")


@admin.register(SystemNotice)
class SystemNoticeAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("title", "notice_type", "importance", "is_pinned", "is_active", "updated_by", "updated_at")
    list_filter = ("notice_type", "importance", "is_pinned", "is_active", "updated_at")
    search_fields = ("title", "content", "link_url")
    readonly_fields = ("created_by", "updated_by", "created_at", "updated_at")

    def has_module_permission(self, request):
        return _can_manage_system_notice(request.user)

    def has_view_permission(self, request, obj=None):
        return _can_manage_system_notice(request.user)

    def has_add_permission(self, request):
        return _can_manage_system_notice(request.user)

    def has_change_permission(self, request, obj=None):
        return _can_manage_system_notice(request.user)

    def has_delete_permission(self, request, obj=None):
        return _can_manage_system_notice(request.user)

    def save_model(self, request, obj, form, change):
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
