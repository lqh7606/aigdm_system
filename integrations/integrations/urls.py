from django.urls import path

from . import views

app_name = "integrations"

urlpatterns = [
    path("", views.integration_home, name="home"),
    path("run-mock-pull/", views.run_mock_pull_view, name="run_mock_pull"),
    path("imports/template/download/", views.download_import_template, name="download_import_template"),
    path("imports/upload/", views.upload_import_file, name="upload_import_file"),
    path("api/v1/integrations/imports/precheck/", views.import_precheck_api, name="api_precheck"),
    path("api/v1/integrations/tasks/", views.integration_tasks_api, name="api_tasks"),
]


