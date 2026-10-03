"""URL routing for the local dashboard."""

from django.urls import include, path
from django.contrib.auth.views import LoginView, LogoutView

urlpatterns = [path("", include("portfolio.urls")), path("login/", LoginView.as_view(), name="login"), path("logout/", LogoutView.as_view(), name="logout")]
