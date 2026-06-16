from django.urls import path

from . import views

app_name = "audit"

urlpatterns = [
    path("", views.audit_list, name="list"),
    path("api/v1/audit/logs/", views.audit_logs_api, name="api_logs"),
]


