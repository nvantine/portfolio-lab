from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("results/", views.results, name="results"),
    path("compare/", views.compare, name="compare"),
    path("datasets/", views.datasets_page, name="datasets"),
    path("activity/status/", views.activity_status, name="activity-status"),
    path("strategies/", views.strategies_page, name="strategies"),
    path("runs/<uuid:key>/", views.results, name="run"),
    path("runs/<uuid:key>/<str:action>/", views.run_action, name="run-action"),
    path("jobs/<uuid:key>/status/", views.job_status, name="job-status"),
    path("jobs/<uuid:key>/cancel/", views.cancel_job, name="cancel-job"),
    path("runs/<uuid:key>/export/<str:format>/", views.run_download, name="run-download"),
    path("notebooks/<uuid:key>/", views.notebook_review, name="notebook"),
    path("paper/", views.paper_page, name="paper"),
    path("paper/<str:action>/<str:key>/", views.paper_action, name="paper-action"),
]
