from django.urls import path

from . import views

app_name = "followups"

urlpatterns = [
    path("", views.followup_home, name="home"),
    path("tasks/<int:pk>/", views.task_detail, name="task_detail"),
    path("tasks/<int:pk>/complete/", views.complete_task, name="complete_task"),
    path("tasks/<int:pk>/cancel/", views.cancel_task, name="cancel_task"),
    path("tasks/<int:pk>/confirm-outcome/", views.confirm_task_outcome, name="confirm_task_outcome"),
    path("api/v1/followups/tasks/", views.followup_tasks_api, name="api_tasks"),
    path("api/v1/followups/tasks/<int:pk>/result/", views.complete_task_api, name="api_complete_task"),
]


