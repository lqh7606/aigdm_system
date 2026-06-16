from django.urls import path

from . import views

app_name = "maternal_records"

urlpatterns = [
    path("", views.record_list, name="list"),
    path("create/", views.create_record, name="create"),
    path("merge/", views.merge_record_view, name="merge"),
    path("<int:pk>/update/", views.update_record, name="update"),
    path("<int:pk>/delete-request/", views.request_record_deletion, name="delete_request"),
    path("<int:pk>/", views.record_detail, name="detail"),
    path("api/v1/maternal-records/", views.maternal_records_api, name="api_records"),
]


