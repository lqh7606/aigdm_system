from django.urls import path

from . import views


app_name = "risk"

urlpatterns = [
    path("", views.assessment_list, name="list"),
    path("records/<int:record_id>/preview/", views.preview_record_assessment, name="preview_record"),
    path("records/<int:record_id>/assess/", views.assess_record, name="assess_record"),
    path("api/v1/risk/assessments/", views.assessments_api, name="api_assessments"),
]

