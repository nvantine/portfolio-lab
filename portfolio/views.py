"""Authenticated operator pages, using the same services as the CLI."""
import json
import plotly.graph_objects as go
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from portfolio.forms import ExperimentForm
from research.models import Dataset, Experiment, Job
from research.services import queue_experiment
from research.reporting import report, safe_markdown
from strategies.catalog import catalog, METHODS
from paper.models import PaperSession
from portfolio.activity import activity_state, live_context

operator = user_passes_test(lambda user: user.is_authenticated and user.is_staff)


@operator
def home(request):
    form = ExperimentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            from research.commands import dispatch
            queued = dispatch({"group": "experiments", "action": "run", "config": form.config()}, user=request.user)[0]
            return redirect("run", key=queued["run_id"])
        except ValueError as exc:
            form.add_error(None, str(exc))
    trash = request.GET.get("trash") == "1"
    query = Experiment.objects.filter(trashed_at__isnull=not trash)
    return render(request, "portfolio/home.html", {"form": form, "datasets": Dataset.objects.all(), "runs": query[:100], "trash": trash, "methods": catalog(), "jobs": Job.objects.order_by("-created_at")[:12], **live_context("research")})


@operator
@require_POST
def run_action(request, key, action):
    from research.services import trash_run
    if action not in {"trash", "restore"}:
        return HttpResponse(status=400)
    try:
        trash_run(key, restore=action == "restore")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("home")


@operator
def datasets_page(request):
    from portfolio.forms import DatasetForm
    from research.commands import dispatch
    from marketdata.universe import DEFAULT_ETFS
    from datetime import timedelta
    from django.utils import timezone
    action = request.POST.get("action", "create")
    today = timezone.localdate()
    form = DatasetForm(request.POST if request.method == "POST" and action == "create" else None, initial={"start": today - timedelta(days=365*5), "end": today, "feed": "iex"})
    outcome = None
    status = 200
    if request.method == "POST":
        try:
            if action == "create" and form.is_valid():
                outcome = dispatch(dict(form.cleaned_data, group="datasets", action="create"), user=request.user)
            elif action in {"accept", "refresh", "demo"}:
                outcome = dispatch({"group": "datasets", "action": action, "id": request.POST.get("id"), "accept_reduced": request.POST.get("accept_reduced") == "on"}, user=request.user)
            elif action != "create":
                raise ValueError("Unknown dataset action")
            if outcome:
                if "job_id" in outcome:
                    messages.success(request, f"Fetch queued for {outcome['symbols']} symbols through {outcome['end']}. Review the preview below when it finishes, then click Save dataset snapshot.")
                    return redirect("/datasets/#fetch-jobs")
                messages.success(request, f"Dataset snapshot {outcome['dataset']} saved. It is available in Research.")
                return redirect("/datasets/#saved-datasets")
            status = 400
        except ValueError as exc:
            if action == "create": form.add_error(None, str(exc))
            else: messages.error(request, str(exc))
            status = 400
    return render(request, "portfolio/datasets.html", {"form": form, "datasets": Dataset.objects.all(), "jobs": Job.objects.filter(kind="dataset").order_by("-created_at")[:30], "preset": " ".join(DEFAULT_ETFS), **live_context("datasets")}, status=status)


@operator
def strategies_page(request):
    from portfolio.forms import RecipeForm
    from research.commands import dispatch
    from research.models import StrategyVersion
    form = RecipeForm(request.POST or None)
    if request.method == "POST":
        try:
            action = request.POST.get("action", "recipe")
            if action == "recipe" and form.is_valid():
                data = dict(form.cleaned_data)
                name = data.pop("name")
                dispatch({"group": "strategies", "action": "recipe", "name": name, "recipe": data}, user=request.user)
                messages.success(request, "Recipe version registered. Select it in Research to run an experiment.")
                return redirect("strategies")
            elif action in {"register", "notebook"}:
                upload = request.FILES.get("source")
                if upload and upload.size > 1_000_000: raise ValueError("Source exceeds 1 MB")
                source = upload.read().decode("utf-8") if upload else request.POST.get("source", "")
                command = {"group": "strategies", "action": "register", "source": source, "name": request.POST.get("name", "")}
                if action == "notebook": command = {"group": "notebooks", "action": "run", "source": source, "dataset": int(request.POST["dataset"])}
                outcome = dispatch(command, user=request.user)
                messages.success(request, "Source registered/submitted. Notebook results appear under Jobs.")
                if action == "notebook": return redirect("notebook", key=outcome["job_id"])
                return redirect("strategies")
        except (ValueError, UnicodeError) as exc:
            messages.error(request, str(exc))
    return render(request, "portfolio/strategies.html", {"form": form, "strategies": StrategyVersion.objects.all(), "datasets": Dataset.objects.all(), "jobs": Job.objects.filter(kind="notebook").order_by("-created_at")[:12], **live_context("strategies")})


@operator
def activity_status(request):
    try: return JsonResponse(activity_state(request.GET.get("scope", "datasets")), headers={"Cache-Control": "no-store"})
    except ValueError: return JsonResponse({"error": "Unknown page scope"}, status=400)


@operator
def job_status(request, key):
    from research.jobs import public_job, health
    return JsonResponse(dict(public_job(get_object_or_404(Job, pk=key)), health=health()))


@operator
@require_POST
def cancel_job(request, key):
    from research.commands import dispatch
    try: dispatch({"group": "jobs", "action": "cancel", "id": str(key)}, user=request.user)
    except ValueError as exc: messages.error(request, str(exc))
    return redirect("home")


@operator
def run_download(request, key, format):
    from research.commands import dispatch
    if format == "json":
        value = dispatch({"group": "runs", "action": "show", "id": str(key)}, user=request.user)
        response = HttpResponse(json.dumps(value, indent=2, default=str), content_type="application/json")
    elif format == "md":
        value = dispatch({"group": "reports", "action": "export", "id": str(key)}, user=request.user)
        response = HttpResponse(value["markdown"], content_type="text/markdown")
    else: return HttpResponse(status=400)
    response["Content-Disposition"] = f'attachment; filename="experiment-{key}.{format}"'
    return response


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
        signed = any(weight < 0 for row in value["weights"] for weight in row.values())
        figure.add_trace(go.Scatter(x=dates, y=[row[ticker] for row in value["weights"]], stackgroup=None if signed else "one", name=ticker))
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
    for index, figure in enumerate(figures):
        if index < 6: figure.update_layout(meta={"sync_time": True})
        figure.update_layout(template="plotly_white", height=360, margin=dict(l=45, r=20, t=50, b=35))
    return [figure.to_json() for figure in figures]


@operator
def results(request, key=None):
    run = get_object_or_404(Experiment, pk=key) if key else Experiment.objects.filter(trashed_at__isnull=True).first()
    plots = charts(run.results) if run and run.status == "succeeded" else []
    job = Job.objects.filter(experiment=run).first() if run else None
    return render(request, "portfolio/results.html", {"run": run, "job": job, "plots": plots, "formula": METHODS.get(run.config.get("method"), ("", ""))[0] if run else "", "assumptions": METHODS.get(run.config.get("method"), ("", ""))[1] if run else "", "parameters": run.config if run else {}, "report": safe_markdown(report(run)) if run else ""})


@operator
def notebook_review(request, key):
    return render(request, "portfolio/notebook.html", {"job": get_object_or_404(Job, pk=key, kind="notebook")})


@operator
@require_POST
def paper_action(request, action, key):
    from research.commands import dispatch
    try:
        if action in {"activate", "approve"}:
            dispatch({"group": "strategies", "action": "activate", "run": key, "budget": request.POST.get("budget", 1000), "scheduled": request.POST.get("scheduled") == "on"}, user=request.user)
        elif action in {"pause", "resume", "close", "revoke"}:
            dispatch({"group": "strategies", "action": action, "session": int(key)}, user=request.user)
        elif action in {"cycle", "tick"}:
            dispatch({"group": "strategies", "action": "cycle"}, user=request.user)
        elif action == "limits":
            dispatch({"group": "strategies", "action": "limits", "budget": request.POST["budget"], "cap": float(request.POST["cap"])}, user=request.user)
        elif action == "adopt":
            dispatch({"group": "strategies", "action": "adopt", "session": int(key), "symbol": request.POST["symbol"], "qty": int(request.POST["qty"])}, user=request.user)
        else:
            return HttpResponse(status=400)
        messages.success(request, "Strategy action completed. Review strategy and order state.")
    except Exception as exc:
        messages.error(request, str(exc) if isinstance(exc, ValueError) else "Strategy action failed. Check broker configuration locally.")
    return redirect("paper")


@operator
def paper_page(request):
    from paper.account import status
    from research.jobs import health
    return render(request, "portfolio/paper.html", {"state": status(), "health": health(), "sessions": PaperSession.objects.all(), "runs": Experiment.objects.filter(trashed_at__isnull=True, status="succeeded", config__window="validation")[:100]})


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
    figure.update_layout(meta={"sync_time": True})
    drawdown = go.Figure()
    for run in runs:
        if run.status == "succeeded": drawdown.add_trace(go.Scatter(x=run.results["dates"], y=run.results["drawdown"], name=f"{run.config['method']} · {str(run.pk)[:8]}"))
    drawdown.update_layout(template="plotly_white", title="Drawdown comparison", meta={"sync_time": True})
    signatures = {(r.dataset_id, r.config.get("window"), r.config.get("seed"), r.config.get("parameters", {}).get("cost_bps", 10)) for r in runs}
    metric_names = sorted({name for run in runs for name in run.results.get("metrics", {})})
    return render(request, "portfolio/compare.html", {"runs": runs, "metric_names": metric_names, "available": Experiment.objects.filter(trashed_at__isnull=True, status="succeeded")[:100], "mismatch": len(signatures) > 1, "ids": ids, "plots": [figure.to_json(), drawdown.to_json()] if runs else []})
