from django.contrib import admin
from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import path, reverse

from accounts.admin_permissions import RoleBasedAdminMixin
from accounts.permissions import PermissionAction, has_action_permission

from .model_lifecycle import (
    ModelLifecycleError,
    activate_model_version,
    create_release_from_uploaded_file,
    normalize_version_code,
)
from .models import ModelVersion, RetentionPolicy, RuleConfig, SystemNotice, ThresholdConfig


def _can_manage_system_notice(user):
    if getattr(user, "is_superuser", False):
        return True
    return has_action_permission(user, PermissionAction.MANAGE_SYSTEM_NOTICE)


class ModelVersionUploadForm(forms.Form):
    model_file = forms.FileField(label="PKL模型文件", help_text="仅支持 .pkl 文件。")
    model_type = forms.ChoiceField(label="模型类型", choices=ModelVersion.ModelType.choices, initial=ModelVersion.ModelType.FULL)
    version_code = forms.CharField(label="版本编码", required=False, max_length=120, help_text="留空时系统自动生成。")
    display_name = forms.CharField(label="显示名称", required=False, max_length=200, help_text="留空时使用文件名。")

    def clean_model_file(self):
        uploaded_file = self.cleaned_data["model_file"]
        if not uploaded_file.name.lower().endswith(".pkl"):
            raise forms.ValidationError("仅支持上传 .pkl 模型文件。")
        return uploaded_file

    def clean_version_code(self):
        version_code = self.cleaned_data.get("version_code", "").strip()
        if not version_code:
            return ""
        normalized = normalize_version_code(version_code)
        if normalized != version_code:
            raise forms.ValidationError("版本编码只能包含英文字母、数字、下划线和短横线。")
        return normalized


@admin.register(ModelVersion)
class ModelVersionAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    change_list_template = "admin/system_config/modelversion/change_list.html"
    list_display = ("version_code", "model_type", "model_family", "status", "activated_at", "updated_at")
    list_filter = ("status", "model_type", "model_family")
    search_fields = ("version_code", "display_name", "artifact_path")
    readonly_fields = (
        "status",
        "status_message",
        "activated_at",
        "retired_at",
        "predecessor",
        "created_at",
        "updated_at",
    )
    actions = ("activate_selected_model_version",)

    @admin.action(description="启用所选模型版本")
    def activate_selected_model_version(self, request, queryset):
        if not self.has_change_permission(request):
            raise PermissionDenied
        if queryset.count() != 1:
            self.message_user(request, "每次只能启用一个模型版本，请只勾选一条记录。", messages.ERROR)
            return

        version = queryset.get()
        current_codes = list(
            ModelVersion.objects.filter(
                model_type=version.model_type,
                status=ModelVersion.Status.PRODUCTION,
            )
            .exclude(pk=version.pk)
            .values_list("version_code", flat=True)
        )
        try:
            activated = activate_model_version(version)
        except ModelLifecycleError as exc:
            self.message_user(request, f"模型版本 {version.version_code} 启用失败：{exc}", messages.ERROR)
            return

        if current_codes:
            retired_summary = "、".join(current_codes)
            self.message_user(
                request,
                f"模型版本 {activated.version_code} 已启用为生产版本，旧生产版本 {retired_summary} 已自动停用。",
                messages.SUCCESS,
            )
        else:
            self.message_user(request, f"模型版本 {activated.version_code} 已启用为生产版本。", messages.SUCCESS)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "upload-pkl/",
                self.admin_site.admin_view(self.upload_pkl),
                name="system_config_modelversion_upload_pkl",
            ),
        ]
        return custom_urls + urls

    def upload_pkl(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        if request.method == "POST":
            form = ModelVersionUploadForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    version = create_release_from_uploaded_file(
                        form.cleaned_data["model_file"],
                        form.cleaned_data["model_type"],
                        version_code=form.cleaned_data.get("version_code") or None,
                        display_name=form.cleaned_data.get("display_name") or None,
                    )
                except ModelLifecycleError as exc:
                    self.message_user(request, f"模型上传或验证失败：{exc}", messages.ERROR)
                else:
                    feature_count = len((version.feature_schema_json or {}).get("feature_order") or [])
                    self.message_user(
                        request,
                        f"模型版本 {version.version_code} 已上传并验证通过，特征数 {feature_count}，SHA256 {version.sha256[:12]}...",
                        messages.SUCCESS,
                    )
                    return redirect(reverse("admin:system_config_modelversion_change", args=[version.pk]))
        else:
            form = ModelVersionUploadForm()

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "上传PKL模型",
            "form": form,
            "has_view_permission": self.has_view_permission(request),
        }
        return render(request, "admin/system_config/modelversion/upload_pkl.html", context)


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
