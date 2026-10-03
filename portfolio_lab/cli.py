"""JSON CLI. LAB_SOCKET selects an unprivileged Hermes client with no Django load."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import sys


def parser():
    root = argparse.ArgumentParser(prog="portfolio-lab")
    groups = root.add_subparsers(dest="group", required=True)
    methods = groups.add_parser("methods").add_subparsers(dest="action", required=True)
    methods.add_parser("list")
    data = groups.add_parser("data").add_subparsers(dest="action", required=True)
    refresh = data.add_parser("refresh")
    refresh.add_argument("tickers", nargs="*")
    refresh.add_argument("--start")
    refresh.add_argument("--end")
    datasets = groups.add_parser("datasets").add_subparsers(dest="action", required=True)
    datasets.add_parser("list")
    freeze = datasets.add_parser("freeze")
    freeze.add_argument("tickers", nargs="+")
    freeze.add_argument("--name", default="ETF snapshot")
    demo = datasets.add_parser("demo")
    demo.add_argument("--seed", type=int, default=42)
    strategies = groups.add_parser("strategies").add_subparsers(dest="action", required=True)
    strategies.add_parser("list")
    register = strategies.add_parser("register")
    register.add_argument("source")
    register.add_argument("--name", required=True)
    experiments = groups.add_parser("experiments").add_subparsers(dest="action", required=True)
    for name in ("run", "sweep"):
        command = experiments.add_parser(name)
        command.add_argument("config")
    notebooks = groups.add_parser("notebooks").add_subparsers(dest="action", required=True)
    notebook = notebooks.add_parser("run")
    notebook.add_argument("source")
    notebook.add_argument("--dataset", required=True, type=int)
    jobs = groups.add_parser("jobs").add_subparsers(dest="action", required=True)
    status = jobs.add_parser("status")
    status.add_argument("id", nargs="?")
    work = jobs.add_parser("work")
    work.add_argument("--once", action="store_true")
    runs = groups.add_parser("runs").add_subparsers(dest="action", required=True)
    runs.add_parser("list")
    show = runs.add_parser("show")
    show.add_argument("id")
    compare = runs.add_parser("compare")
    compare.add_argument("ids", nargs="+")
    reports = groups.add_parser("reports").add_subparsers(dest="action", required=True)
    export = reports.add_parser("export")
    export.add_argument("id")
    export.add_argument("--output", required=True)
    paper = groups.add_parser("paper").add_subparsers(dest="action", required=True)
    paper.add_parser("status")
    tick = paper.add_parser("tick")
    tick.add_argument("--session", required=True, type=int)
    serve = groups.add_parser("serve")
    serve.add_argument("--socket", required=True)
    return root


def initialize():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portfolio_lab.settings")
    import django
    django.setup()


def prepare(args):
    values = vars(args).copy()
    if args.group == "experiments":
        values["config"] = json.loads(Path(args.config).read_text())
    if args.group in ("strategies", "notebooks") and args.action in ("register", "run"):
        source = Path(args.source)
        if source.stat().st_size > 1_000_000:
            raise ValueError("Source file exceeds 1 MB")
        values["source"] = source.read_text()
    if args.group == "reports":
        values.pop("output")
    return values


def dispatch(values, agent=False):
    group, action = values["group"], values.get("action")
    from research import services
    from research.models import Dataset, Experiment, Job, StrategyVersion
    if group == "methods":
        from strategies.catalog import catalog
        return catalog()
    if group == "datasets":
        if action == "list":
            return list(Dataset.objects.values("id", "name", "digest", "manifest"))
        if agent:
            raise ValueError("Agents may list operator-frozen datasets only")
        if action == "demo":
            import numpy as np
            import pandas as pd
            rng = np.random.default_rng(values["seed"])
            frame = pd.DataFrame(100*np.exp(np.cumsum(rng.normal(.0003, .012, (630, 6)), axis=0)), index=pd.bdate_range("2022-01-03", periods=630), columns=["SPY", "QQQ", "AGG", "GLD", "TLT", "EFA"])
            dataset = services.freeze_frame(frame, "SYNTHETIC demonstration", "Synthetic seeded independent Gaussian daily log returns")
        else:
            dataset = services.freeze_prices([t.upper() for t in values["tickers"]], values["name"])
        return {"dataset": dataset.pk, "digest": dataset.digest, "manifest": dataset.manifest}
    if group == "data":
        if agent:
            raise ValueError("Only the operator refreshes market data")
        from django.core.management import call_command
        out, err = io.StringIO(), io.StringIO()
        options = {key: values[key] for key in ("start", "end") if values.get(key)}
        call_command("refresh_prices", *values["tickers"], stdout=out, stderr=err, **options)
        return {"status": "refreshed", "messages": out.getvalue().splitlines(), "diagnostics": err.getvalue().splitlines()}
    if group == "strategies":
        if action == "list":
            return list(StrategyVersion.objects.values("name", "digest"))
        strategy = services.register_strategy(values["name"], values["source"])
        return {"name": strategy.name, "digest": strategy.digest}
    if group == "experiments":
        configs = values["config"] if action == "sweep" else [values["config"]]
        if not isinstance(configs, list) or not 1 <= len(configs) <= 12:
            raise ValueError("A sweep must contain 1–12 experiment configs")
        if agent and Job.objects.filter(status__in=["queued", "running"]).count() + len(configs) > 24:
            raise ValueError("Agent queue limit reached; wait for existing jobs")
        if agent:
            from django.utils import timezone
            if Experiment.objects.filter(created_at__date=timezone.localdate()).count() + len(configs) > 24:
                raise ValueError("Daily research budget of 24 trials reached")
        return [services.queue_experiment(config, agent) for config in configs]
    if group == "notebooks":
        if agent and Job.objects.filter(status__in=["queued", "running"]).count() >= 24:
            raise ValueError("Agent queue limit reached")
        if agent:
            from django.utils import timezone
            if Job.objects.filter(kind="notebook", created_at__date=timezone.localdate()).count() >= 4:
                raise ValueError("Daily notebook budget of four jobs reached")
        return services.queue_notebook(values["dataset"], json.loads(values["source"]))
    if group == "jobs":
        from research.jobs import public_job, work
        if action == "work":
            if agent:
                raise ValueError("Only the trusted operator starts workers")
            return work(values["once"])
        if values.get("id"):
            return public_job(Job.objects.get(pk=values["id"]))
        return [public_job(job) for job in Job.objects.order_by("-created_at")[:24]]
    if group == "runs":
        def summary(run):
            return {"id": str(run.pk), "dataset": run.dataset_id, "method": run.config.get("method"), "status": run.status, "metrics": run.results.get("metrics", {}), "error": run.error}
        if action == "list":
            query = Experiment.objects.exclude(config__window="holdout") if agent else Experiment.objects.all()
            return [summary(run) for run in query[:50]]
        if action == "compare":
            if len(values["ids"]) > 20:
                raise ValueError("Compare at most 20 runs")
            runs = [Experiment.objects.get(pk=key) for key in values["ids"]]
            if agent and any(run.config.get("window") == "holdout" for run in runs):
                raise ValueError("Holdout results are reserved for the operator")
            return [summary(run) for run in runs]
        run = Experiment.objects.get(pk=values["id"])
        if agent and run.config.get("window") == "holdout":
            raise ValueError("Holdout results are reserved for the operator")
        return dict(summary(run), config=run.config, provenance=run.provenance, results=run.results)
    if group == "reports":
        from research.reporting import report
        run = Experiment.objects.get(pk=values["id"])
        if agent and run.config.get("window") == "holdout":
            raise ValueError("Holdout results are reserved for the operator")
        return {"markdown": report(run)}
    if group == "paper":
        from paper.services import status, tick
        if action == "status":
            return status()
        if agent:
            raise ValueError("Agents cannot execute or approve paper orders")
        return tick(values["session"])
    raise ValueError("Unsupported command")


def remote(path, values):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(30)
        client.connect(path)
        client.sendall(json.dumps(values).encode() + b"\n")
        stream = client.makefile("rb")
        line = stream.readline(20_000_001)
        if len(line) > 20_000_000:
            raise ValueError("Service response exceeded limit")
        result = json.loads(line)
        if not result["ok"]:
            raise ValueError(result["error"])
        return result["result"]


def main():
    args = parser().parse_args()
    try:
        values = prepare(args)
        if os.getenv("LAB_SOCKET"):
            result = remote(os.environ["LAB_SOCKET"], values)
        else:
            initialize()
            if args.group == "serve":
                from research.rpc import serve
                serve(args.socket)
                return
            with contextlib.redirect_stdout(sys.stderr):
                result = dispatch(values)
        if args.group == "reports":
            Path(args.output).write_text(result["markdown"])
            result = {"output": str(Path(args.output).resolve())}
        print(json.dumps(result, allow_nan=False, default=str))
    except Exception as exc:
        # Only controlled application validation text is shown, not API responses.
        message = str(exc) if isinstance(exc, (ValueError, FileNotFoundError)) else "Command failed. Check identifiers, credentials, or runtime configuration locally."
        print(json.dumps({"error": message}), file=sys.stderr)
        raise SystemExit(1) from None
