from django.contrib import admin

from accounts.admin_permissions import RoleBasedAdminMixin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "target_type", "target_id", "summary", "ip_address")
    list_filter = ("action", "target_type", "created_at")
    search_fields = ("summary", "target_id", "user__username")
    readonly_fields = ("created_at",)
