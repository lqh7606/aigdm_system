from django import forms
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
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


class UserProfileFormFieldsMixin(forms.Form):
    role = forms.ChoiceField(label="角色", choices=UserProfile.Role.choices, initial=UserProfile.Role.DOCTOR)
    department = forms.ModelChoiceField(label="所属科室", queryset=Department.objects.none(), required=False)
    data_scope = forms.ChoiceField(label="数据范围", choices=UserProfile.DataScope.choices, initial=UserProfile.DataScope.DEPARTMENT)
    mobile = forms.CharField(label="联系电话", max_length=30, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.filter(is_active=True).order_by("name")
        profile = self._profile_instance()
        if profile:
            self.fields["role"].initial = profile.role
            self.fields["department"].initial = profile.department_id
            self.fields["data_scope"].initial = profile.data_scope
            self.fields["mobile"].initial = profile.mobile

    def _profile_instance(self):
        user = getattr(self, "instance", None)
        if not user or not getattr(user, "pk", None):
            return None
        try:
            return user.userprofile
        except UserProfile.DoesNotExist:
            return None

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        department = cleaned_data.get("department")
        if role != UserProfile.Role.ADMIN and not department:
            self.add_error("department", "非系统管理员必须选择所属科室。")
        return cleaned_data

    def profile_defaults(self):
        return {
            "role": self.cleaned_data["role"],
            "department": self.cleaned_data.get("department"),
            "data_scope": self.cleaned_data["data_scope"],
            "mobile": self.cleaned_data.get("mobile", ""),
        }


class UserWithProfileCreationForm(UserProfileFormFieldsMixin, UserCreationForm):
    pass


class UserWithProfileChangeForm(UserProfileFormFieldsMixin, UserChangeForm):
    pass

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
    add_form = UserWithProfileCreationForm
    form = UserWithProfileChangeForm
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "password1", "password2")}),
        ("用户档案", {"fields": ("role", "department", "data_scope", "mobile")}),
    )
    inlines = ()

    def get_fieldsets(self, request, obj=None):
        if _is_manager_user(request.user) and obj is not None:
            return (
                (None, {"fields": ("username", "password")}),
                ("个人信息", {"fields": ("first_name", "last_name", "email")}),
                ("状态", {"fields": ("is_active",)}),
                ("重要日期", {"fields": ("last_login", "date_joined")}),
            )
        fieldsets = super().get_fieldsets(request, obj=obj)
        if obj is not None:
            return fieldsets + (("用户档案", {"fields": ("role", "department", "data_scope", "mobile")}),)
        return fieldsets

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
        elif hasattr(form, "profile_defaults"):
            UserProfile.objects.update_or_create(user=obj, defaults=form.profile_defaults())


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
