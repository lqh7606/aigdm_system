from django.contrib import admin
from django.urls import include, path
from accounts.admin_permissions import RoleBasedAdminAuthenticationForm, can_access_admin

from dashboard import views as dashboard_views
from followups import views as followup_views
from integrations import views as integration_views
from labs import views as lab_views
from maternal_records import views as maternal_views
from risk import views as risk_views
from system_config import views as system_views

urlpatterns = [
    path("accounts/", include("accounts.urls")),
    path("admin/", admin.site.urls),
    path("", include("dashboard.urls")),
    path("records/", include("maternal_records.urls")),
    path("labs/", include("labs.urls")),
    path("integrations/", include("integrations.urls")),
    path("system/", include("system_config.urls")),
    path("risk/", include("risk.urls")),
    path("followups/", include("followups.urls")),
    path("api/v1/maternal-records/", maternal_views.maternal_records_api, name="api_v1_maternal_records"),
    path("api/v1/labs/results/", lab_views.lab_results_api, name="api_v1_lab_results"),
    path("api/v1/labs/results/<int:pk>/confirm/", lab_views.confirm_lab_api, name="api_v1_lab_confirm"),
    path("api/v1/labs/ogtt-outcomes/<int:pk>/confirm/", lab_views.confirm_ogtt_api, name="api_v1_ogtt_confirm"),
    path("api/v1/integrations/imports/precheck/", integration_views.import_precheck_api, name="api_v1_import_precheck"),
    path("api/v1/integrations/tasks/", integration_views.integration_tasks_api, name="api_v1_integration_tasks"),
    path("api/v1/risk/assessments/", risk_views.assessments_api, name="api_v1_risk_assessments"),
    path("api/v1/followups/tasks/", followup_views.followup_tasks_api, name="api_v1_followup_tasks"),
    path("api/v1/followups/tasks/<int:pk>/result/", followup_views.complete_task_api, name="api_v1_followup_task_result"),
    path("api/v1/system/models/", system_views.model_versions_api, name="api_v1_system_models"),
    path("api/v1/system/configs/", system_views.configs_api, name="api_v1_system_configs"),
    path("api/v1/dashboard/metrics/", dashboard_views.metrics_api, name="api_v1_dashboard_metrics"),
]

admin.site.site_header = "妊娠期糖尿病辅助诊疗系统"
admin.site.site_title = "AIGDM 管理后台"
admin.site.index_title = "系统管理"
admin.site.has_permission = lambda request: can_access_admin(request.user)
admin.site.login_form = RoleBasedAdminAuthenticationForm

handler403 = "accounts.views.permission_denied_page"

_ADMIN_APP_LABELS = {
    "maternal_records": "孕产妇档案",
    "labs": "检验数据",
    "risk": "风险评估",
    "followups": "随访闭环",
    "integrations": "数据接入",
    "system_config": "系统配置",
    "accounts": "用户与机构",
    "audit": "审计日志",
}

_ADMIN_APP_ORDER = {
    "maternal_records": 10,
    "labs": 20,
    "risk": 30,
    "followups": 40,
    "integrations": 50,
    "system_config": 60,
    "accounts": 70,
    "audit": 80,
}

_ADMIN_MODEL_ORDER = {
    "accounts": {
        "User": 10,
        "Group": 20,
        "Department": 30,
    },
}


def _admin_model_sort_key(app_label, model):
    model_order = _ADMIN_MODEL_ORDER.get(app_label, {})
    return (model_order.get(model.get("object_name"), 100), model.get("name", ""))


def _custom_admin_app_list(request, app_label=None):
    build_app_label = None if app_label in {"accounts", "auth"} else app_label
    app_dict = admin.site._build_app_dict(request, build_app_label)
    grouped_apps = {}

    for source_label, source_app in app_dict.items():
        target_label = "accounts" if source_label == "auth" else source_label
        target_app = grouped_apps.setdefault(
            target_label,
            {
                "name": _ADMIN_APP_LABELS.get(target_label, source_app["name"]),
                "app_label": target_label,
                "app_url": source_app.get("app_url", ""),
                "has_module_perms": source_app.get("has_module_perms", False),
                "models": [],
            },
        )

        if source_label == "accounts":
            target_app["app_url"] = source_app.get("app_url", target_app["app_url"])

        target_app["has_module_perms"] = target_app["has_module_perms"] or source_app.get("has_module_perms", False)
        target_app["models"].extend(source_app["models"])

    app_list = [
        app
        for app in grouped_apps.values()
        if app["models"] and (app_label not in {"accounts", "auth"} or app["app_label"] == "accounts")
    ]

    for app in app_list:
        app["name"] = _ADMIN_APP_LABELS.get(app["app_label"], app["name"])
        app["models"].sort(key=lambda model: _admin_model_sort_key(app["app_label"], model))

    app_list.sort(key=lambda app: (_ADMIN_APP_ORDER.get(app["app_label"], 100), app["name"]))
    return app_list


admin.site.get_app_list = _custom_admin_app_list

