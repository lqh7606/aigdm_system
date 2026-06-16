from django.urls import path

from . import views


app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("api/v1/dashboard/metrics/", views.metrics_api, name="api_metrics"),
]

