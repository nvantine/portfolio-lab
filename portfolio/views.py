"""Authenticated operator pages, using the same services as the CLI."""
import json
import plotly.graph_objects as go
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from portfolio.forms import ExperimentForm
from research.models import Dataset, Experiment, Job
from research.services import queue_experiment
from research.reporting import report, safe_markdown
from strategies.catalog import catalog, METHODS
from paper.models import PaperSession

operator = user_passes_test(lambda user: user.is_authenticated and user.is_staff)


@operator
def home(request):
    form = ExperimentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            queued = queue_experiment(form.config())
            return redirect("run", key=queued["run_id"])
        except ValueError as exc:
            form.add_error(None, str(exc))
    return render(request, "portfolio/home.html", {"form": form, "datasets": Dataset.objects.all(), "runs": Experiment.objects.all()[:20], "methods": catalog(), "jobs": Job.objects.order_by("-created_at")[:12]})


def charts(value):
    figures = []
    dates = value["dates"]
    wealth = go.Figure(go.Scatter(x=dates, y=value["wealth"], name="Strategy"))
    for name, baseline in value.get("benchmarks", {}).items():
        wealth.add_trace(go.Scatter(x=dates, y=baseline["wealth"], name=name))
    wealth.update_layout(title="Growth of $1 after modeled costs")
    figures.append(wealth)
    for field, title in [("drawdown", "Drawdown"), ("turnover", "Traded fraction")]:
        figure = go.Figure(go.Scatter(x=dates, y=value[field]))
        figure.update_layout(title=title)
        figures.append(figure)
    last = value["weights"][-1]
    figure = go.Figure(go.Bar(x=list(last), y=list(last.values())))
    figure.update_layout(title=f"Last allocation · cash {1 - sum(last.values()):.1%}")
    figures.append(figure)
    figure = go.Figure()
    for ticker in last:
        figure.add_trace(go.Scatter(x=dates, y=[row[ticker] for row in value["weights"]], stackgroup="one", name=ticker))
    figure.update_layout(title="Allocations through time")
    figures.append(figure)
    import pandas as pd
    rolling = pd.Series(value["returns"]).rolling(21).std() * 252**.5
    figure = go.Figure(go.Scatter(x=dates, y=rolling.tolist()))
    figure.update_layout(title="Rolling 21-session annualized volatility")
    figures.append(figure)
    sigma = value["covariance"]
    figure = go.Figure(go.Heatmap(z=sigma["values"], x=sigma["tickers"], y=sigma["tickers"], colorscale="Viridis"))
    figure.update_layout(title="Covariance at evaluation end")
    figures.append(figure)
    frontier = value["frontier"]
    figure = go.Figure(go.Scatter(x=[p["volatility"] for p in frontier], y=[p["return"] for p in frontier], mode="lines+markers"))
    figure.update_layout(title="Estimated constrained efficient frontier", xaxis_title="Annualized volatility", yaxis_title="Estimated annual return")
    figures.append(figure)
    figure = go.Figure()
    simulation = value["simulation"]
    for label, values in simulation["fan"].items():
        figure.add_trace(go.Scatter(y=values, name=label))
    figure.update_layout(title="Physical GBM-style simulation · training data only")
    figures.append(figure)
    for figure in figures:
        figure.update_layout(template="plotly_white", height=360, margin=dict(l=45, r=20, t=50, b=35))
    return [figure.to_json() for figure in figures]


@operator
def results(request, key=None):
    run = get_object_or_404(Experiment, pk=key) if key else Experiment.objects.first()
    plots = charts(run.results) if run and run.status == "succeeded" else []
    return render(request, "portfolio/results.html", {"run": run, "plots": plots, "formula": METHODS[run.config["method"]][0] if run else "", "assumptions": METHODS[run.config["method"]][1] if run else "", "parameters": json.dumps(run.config, indent=2) if run else "", "report": safe_markdown(report(run)) if run else ""})


@operator
def notebook_review(request, key):
    return render(request, "portfolio/notebook.html", {"job": get_object_or_404(Job, pk=key, kind="notebook")})


@operator
@require_POST
def paper_action(request, action, key):
    from paper.services import approve, stop, tick
    try:
        if action == "approve":
            approve(key, request.user, budget=request.POST.get("budget", 10000))
        elif action == "pause":
            stop(key)
        elif action == "revoke":
            stop(key, revoke=True)
        elif action == "tick":
            tick(key)
        else:
            return HttpResponse(status=400)
        messages.success(request, "Paper action completed. Review session and order state.")
    except Exception as exc:
        messages.error(request, str(exc) if isinstance(exc, ValueError) else "Paper action failed. Check broker configuration locally.")
    return redirect("paper")


@operator
def paper_page(request):
    from paper.services import status
    return render(request, "portfolio/paper.html", {"state": status(), "sessions": PaperSession.objects.all(), "runs": Experiment.objects.filter(status="succeeded", config__window="validation")[:20]})


@operator
def compare(request):
    ids = request.GET.get("ids", "")
    import uuid
    try:
        keys = [uuid.UUID(key.strip()) for key in ids.split(",") if key.strip()]
    except ValueError:
        return HttpResponse("Use valid comma-separated run UUIDs", status=400)
    if len(keys) > 20:
        return HttpResponse("Compare at most 20 runs", status=400)
    runs = list(Experiment.objects.filter(pk__in=keys))
    figure = go.Figure()
    for run in runs:
        if run.status == "succeeded":
            figure.add_trace(go.Scatter(x=run.results["dates"], y=run.results["wealth"], name=f"{run.config['method']} · {str(run.pk)[:8]}"))
    figure.update_layout(template="plotly_white", title="Growth of $1")
    return render(request, "portfolio/compare.html", {"runs": runs, "ids": ids, "plot": figure.to_json() if runs else None})
