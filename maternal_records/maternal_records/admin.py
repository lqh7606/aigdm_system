from django.contrib import admin

from accounts.admin_permissions import RecordScopedAdminMixin, RoleBasedAdminMixin
from accounts.permissions import PermissionAction, has_action_permission

from .models import FieldSource, MaternalRecord, MergeRecord, RecordAccessGrant, RecordDeletionRequest
from .services import approve_deletion_request, reject_deletion_request


def _can_review_deletion_requests(user):
    if getattr(user, "is_superuser", False):
        return True
    return has_action_permission(user, PermissionAction.APPROVE_RECORD_DELETION)


class FieldSourceInline(admin.TabularInline):
    model = FieldSource
    extra = 0
    readonly_fields = ("captured_at",)


@admin.register(MaternalRecord)
class MaternalRecordAdmin(RecordScopedAdminMixin, admin.ModelAdmin):
    maternal_record_lookup = "self"
    list_display = ("record_no", "name", "age", "gestational_week", "pre_preg_bmi", "status", "source_type")
    list_filter = ("status", "source_type", "diabetes_before_pregnancy")
    search_fields = ("record_no", "name", "id_card_masked", "phone_masked")
    inlines = [FieldSourceInline]


@admin.register(MergeRecord)
class MergeRecordAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("source_record", "target_record", "status", "reason", "approved_by", "approved_at")
    list_filter = ("status",)
    search_fields = ("source_record__record_no", "target_record__record_no", "reason")


@admin.register(RecordDeletionRequest)
class RecordDeletionRequestAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("record_label", "status", "approval_action", "requested_by", "requested_at", "reviewed_by", "reviewed_at")
    list_filter = ("status", "approval_action", "requested_at", "reviewed_at")
    search_fields = ("record__record_no", "record__name", "reason", "approval_comment")
    readonly_fields = (
        "record",
        "record_snapshot",
        "requested_by",
        "reason",
        "status",
        "approval_action",
        "approval_comment",
        "reviewed_by",
        "requested_at",
        "reviewed_at",
    )
    actions = ("approve_as_archive", "approve_as_delete", "reject_requests")

    def has_module_permission(self, request):
        return _can_review_deletion_requests(request.user)

    def has_view_permission(self, request, obj=None):
        return _can_review_deletion_requests(request.user)

    def has_change_permission(self, request, obj=None):
        return _can_review_deletion_requests(request.user)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def record_label(self, obj):
        if obj.record_id:
            return obj.record
        return obj.record_snapshot.get("record_no") or "已删除档案"

    record_label.short_description = "档案"

    @admin.action(description="批准并归档所选档案")
    def approve_as_archive(self, request, queryset):
        count = 0
        for deletion_request in queryset.filter(status=RecordDeletionRequest.Status.PENDING):
            approve_deletion_request(
                deletion_request,
                RecordDeletionRequest.ApprovalAction.ARCHIVE,
                reviewer=request.user,
                comment="后台批准归档",
                request=request,
            )
            count += 1
        self.message_user(request, f"已批准归档 {count} 条删除申请。")

    @admin.action(description="批准并物理删除所选档案")
    def approve_as_delete(self, request, queryset):
        count = 0
        for deletion_request in queryset.filter(status=RecordDeletionRequest.Status.PENDING):
            approve_deletion_request(
                deletion_request,
                RecordDeletionRequest.ApprovalAction.DELETE,
                reviewer=request.user,
                comment="后台批准物理删除",
                request=request,
            )
            count += 1
        self.message_user(request, f"已批准物理删除 {count} 条删除申请。")

    @admin.action(description="驳回所选删除申请")
    def reject_requests(self, request, queryset):
        count = 0
        for deletion_request in queryset.filter(status=RecordDeletionRequest.Status.PENDING):
            reject_deletion_request(deletion_request, reviewer=request.user, comment="后台驳回删除申请", request=request)
            count += 1
        self.message_user(request, f"已驳回 {count} 条删除申请。")


@admin.register(FieldSource)
class FieldSourceAdmin(RecordScopedAdminMixin, admin.ModelAdmin):
    maternal_record_lookup = "maternal_record"
    list_display = ("maternal_record", "field_name", "source_type", "source_ref", "captured_at")
    list_filter = ("source_type",)
    search_fields = ("maternal_record__record_no", "maternal_record__name", "field_name")


@admin.register(RecordAccessGrant)
class RecordAccessGrantAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("record", "grant_type", "user", "department", "role", "is_active", "granted_by", "created_at")
    list_filter = ("grant_type", "is_active", "role", "created_at")
    search_fields = ("record__record_no", "record__name", "user__username", "department__name", "reason")
    readonly_fields = ("created_at", "updated_at")
