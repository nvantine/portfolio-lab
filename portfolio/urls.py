from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("results/", views.results, name="results"),
    path("compare/", views.compare, name="compare"),
    path("runs/<uuid:key>/", views.results, name="run"),
    path("notebooks/<uuid:key>/", views.notebook_review, name="notebook"),
    path("paper/", views.paper_page, name="paper"),
    path("paper/<str:action>/<str:key>/", views.paper_action, name="paper-action"),
]
