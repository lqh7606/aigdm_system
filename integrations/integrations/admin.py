from django.contrib import admin

from accounts.admin_permissions import RoleBasedAdminMixin

from .models import FieldMapping, ImportBatch, ImportTemplate, IntegrationSource, IntegrationTask


@admin.register(IntegrationSource)
class IntegrationSourceAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "source_kind", "adapter_path", "is_active")
    list_filter = ("source_kind", "is_active")
    search_fields = ("code", "name")


@admin.register(IntegrationTask)
class IntegrationTaskAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("source", "task_type", "status", "pulled_count", "created_at")
    list_filter = ("status", "task_type", "source")


@admin.register(FieldMapping)
class FieldMappingAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("source", "source_field", "target_model", "target_field", "required")
    list_filter = ("source", "target_model", "required")


@admin.register(ImportBatch)
class ImportBatchAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("file_name", "import_kind", "status", "total_rows", "success_rows", "failed_rows", "overwritten_rows", "created_at")
    list_filter = ("import_kind", "status", "source")
    search_fields = ("file_name",)


@admin.register(ImportTemplate)
class ImportTemplateAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "template_kind", "file_format", "is_active", "updated_at")
    list_filter = ("template_kind", "file_format", "is_active")
    search_fields = ("code", "name")
