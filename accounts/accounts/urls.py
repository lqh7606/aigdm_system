from django.urls import path

from .views import ChineseLoginView, logout_view, profile_view

app_name = "accounts"

urlpatterns = [
    path("login/", ChineseLoginView.as_view(), name="login"),
    path("profile/", profile_view, name="profile"),
    path("logout/", logout_view, name="logout"),
]

