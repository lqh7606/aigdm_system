from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import path

from .admin_permissions import RoleBasedAdminMixin
from .models import Department, UserProfile
from .role_group_defaults import apply_default_role_group_permissions


def _profile_role(user):
    profile = getattr(user, "userprofile", None)
    return profile.role if profile else None


def _is_manager_user(user):
    return False


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    extra = 0
    max_num = 1
    fields = ("role", "department", "data_scope", "mobile")
    verbose_name = "用户档案"
    verbose_name_plural = "用户档案"

try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class UserWithProfileAdmin(RoleBasedAdminMixin, DjangoUserAdmin):
    inlines = (UserProfileInline,)

    def get_fieldsets(self, request, obj=None):
        if _is_manager_user(request.user) and obj is not None:
            return (
                (None, {"fields": ("username", "password")}),
                ("个人信息", {"fields": ("first_name", "last_name", "email")}),
                ("状态", {"fields": ("is_active",)}),
                ("重要日期", {"fields": ("last_login", "date_joined")}),
            )
        return super().get_fieldsets(request, obj=obj)

    def save_model(self, request, obj, form, change):
        if _is_manager_user(request.user):
            obj.is_staff = False
            obj.is_superuser = False
        super().save_model(request, obj, form, change)
        if _is_manager_user(request.user):
            manager_profile = request.user.userprofile
            UserProfile.objects.get_or_create(
                user=obj,
                defaults={
                    "role": UserProfile.Role.DOCTOR,
                    "department": manager_profile.department,
                    "data_scope": UserProfile.DataScope.DEPARTMENT,
                },
            )


@admin.register(Group)
class GroupWithRoleAdmin(RoleBasedAdminMixin, DjangoGroupAdmin):
    change_list_template = "admin/auth/group/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "apply-default-role-permissions/",
                self.admin_site.admin_view(self.apply_default_role_permissions),
                name="auth_group_apply_default_role_permissions",
            ),
        ]
        return custom_urls + urls

    def apply_default_role_permissions(self, request):
        if request.method != "POST":
            return redirect("admin:auth_group_changelist")
        if not self.has_change_permission(request):
            raise PermissionDenied

        results = apply_default_role_group_permissions()
        summary = "；".join(f"{item.group_name} {item.permission_count} 项" for item in results)
        self.message_user(request, f"已应用默认角色组权限：{summary}。", messages.SUCCESS)
        return redirect("admin:auth_group_changelist")


@admin.register(Department)
class DepartmentAdmin(RoleBasedAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "department_type", "is_active")
    list_filter = ("department_type", "is_active")
    search_fields = ("code", "name")
