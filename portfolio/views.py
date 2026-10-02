"""Phase 1 placeholder pages."""

from django.shortcuts import render


def home(request):
    return render(request, "portfolio/home.html")


def results(request):
    return render(request, "portfolio/results.html")
