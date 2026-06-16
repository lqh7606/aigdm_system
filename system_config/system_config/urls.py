from django.urls import path

from . import views


app_name = "system_config"

urlpatterns = [
    path("configs/", views.config_home, name="config_home"),
    path("api/v1/system/models/", views.model_versions_api, name="api_models"),
    path("api/v1/system/configs/", views.configs_api, name="api_configs"),
]

