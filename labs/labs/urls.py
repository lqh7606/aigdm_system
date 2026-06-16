from django.urls import path

from . import views

app_name = "labs"

urlpatterns = [
    path("", views.lab_list, name="list"),
    path("records/search/", views.record_search, name="record_search"),
    path("create/", views.create_result, name="create_result"),
    path("<int:pk>/confirm/", views.confirm_lab, name="confirm"),
    path("ogtt/<int:record_id>/calculate/", views.calculate_ogtt, name="calculate_ogtt"),
    path("ogtt-outcomes/<int:pk>/confirm/", views.confirm_ogtt, name="confirm_ogtt"),
    path("api/v1/labs/results/", views.lab_results_api, name="api_results"),
    path("api/v1/labs/results/<int:pk>/confirm/", views.confirm_lab_api, name="api_confirm"),
    path("api/v1/labs/ogtt-outcomes/<int:pk>/confirm/", views.confirm_ogtt_api, name="api_ogtt_confirm"),
]


