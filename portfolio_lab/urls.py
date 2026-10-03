"""URL routing for the local dashboard."""

from django.urls import include, path

urlpatterns = [path("", include("portfolio.urls")), path("", include("django.contrib.auth.urls"))]
