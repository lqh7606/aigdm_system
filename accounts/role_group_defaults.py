from dataclasses import dataclass

from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from .admin_permissions import MODEL_VIEW_ROLES, MODEL_WRITE_ROLES
from .models import UserProfile
from .permissions import LEGACY_ROLE_ALIASES, permission_specs_for_role


WRITE_ACTIONS = ("add", "change", "delete")


@dataclass(frozen=True)
class RoleGroupSyncResult:
    role: str
    group_name: str
    created: bool
    permission_count: int


DEFAULT_ROLE_GROUP_NAMES = {
    UserProfile.Role.DOCTOR: UserProfile.Role.DOCTOR.label,
    UserProfile.Role.NURSE: UserProfile.Role.NURSE.label,
    UserProfile.Role.DEPARTMENT_HEAD: UserProfile.Role.DEPARTMENT_HEAD.label,
    UserProfile.Role.ADMIN: UserProfile.Role.ADMIN.label,
}

LEGACY_ROLE_GROUP_NAMES = {
    UserProfile.Role.MANAGER: UserProfile.Role.MANAGER.label,
}


def _model_for_key(model_key):
    app_label, model_name = model_key.split(".", 1)
    if model_key == "accounts.user":
        app_label = "auth"
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


def _permission_specs_for_role(role):
    role = LEGACY_ROLE_ALIASES.get(role, role)
    specs = set()
    for model_key, roles in MODEL_VIEW_ROLES.items():
        if role in roles:
            model = _model_for_key(model_key)
            if model is not None:
                specs.add((model_key, f"view_{model._meta.model_name}"))
    for model_key, roles in MODEL_WRITE_ROLES.items():
        if role in roles:
            model = _model_for_key(model_key)
            if model is None:
                continue
            specs.add((model_key, f"view_{model._meta.model_name}"))
            for action in WRITE_ACTIONS:
                specs.add((model_key, f"{action}_{model._meta.model_name}"))
    for app_label, model_name, codename in permission_specs_for_role(role):
        specs.add((f"{app_label}.{model_name}", codename))
    return specs


def default_permissions_for_role(role):
    permissions = {}
    for model_key, codename in sorted(_permission_specs_for_role(role)):
        model = _model_for_key(model_key)
        if model is None:
            continue
        content_type = ContentType.objects.get_for_model(model)
        permission = Permission.objects.filter(content_type=content_type, codename=codename).first()
        if permission is not None:
            permissions[permission.pk] = permission
    return list(permissions.values())


def apply_default_role_group_permissions():
    results = []
    for role, group_name in DEFAULT_ROLE_GROUP_NAMES.items():
        group, created = Group.objects.get_or_create(name=group_name)
        permissions = default_permissions_for_role(role)
        group.permissions.set(permissions)
        results.append(
            RoleGroupSyncResult(
                role=role,
                group_name=group_name,
                created=created,
                permission_count=len(permissions),
            )
        )
    for role, group_name in LEGACY_ROLE_GROUP_NAMES.items():
        group = Group.objects.filter(name=group_name).first()
        if group is None:
            continue
        permissions = default_permissions_for_role(role)
        group.permissions.set(permissions)
        results.append(
            RoleGroupSyncResult(
                role=role,
                group_name=group_name,
                created=False,
                permission_count=len(permissions),
            )
        )
    return results
