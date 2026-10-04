"""JSON CLI. LAB_SOCKET selects an owner-authorized socket client with no Django load."""
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
    app = groups.add_parser("app").add_subparsers(dest="action", required=True)
    app.add_parser("run").add_argument("--port", type=int, default=8000)
    for action in ("trash", "restore"):
        runs.add_parser(action).add_argument("id")
    runs.choices["list"].add_argument("--trash", action="store_true")
    create = datasets.add_parser("create")
    create.add_argument("tickers", nargs="+")
    create.add_argument("--start", required=True)
    create.add_argument("--end", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--feed", choices=["iex", "sip"], default="iex")
    create.add_argument("--benchmark", default="SPY")
    accept = datasets.add_parser("accept")
    accept.add_argument("id")
    accept.add_argument("--accept-reduced", action="store_true")
    refresh_dataset = datasets.add_parser("refresh")
    refresh_dataset.add_argument("id", type=int)
    refresh_dataset.add_argument("--end")
    strategies.add_parser("show").add_argument("id")
    recipe = strategies.add_parser("recipe")
    recipe.add_argument("recipe")
    recipe.add_argument("--name", required=True)
    strategies.add_parser("status")
    activate = strategies.add_parser("activate")
    activate.add_argument("run")
    activate.add_argument("--budget", required=True, type=float)
    activate.add_argument("--manual", action="store_true")
    strategies.add_parser("cycle")
    for action in ("pause", "resume", "close", "revoke"):
        strategies.add_parser(action).add_argument("session", type=int)
    adopt = strategies.add_parser("adopt")
    adopt.add_argument("session", type=int)
    adopt.add_argument("symbol")
    adopt.add_argument("qty", type=int)
    limits = strategies.add_parser("limits")
    limits.add_argument("--budget", type=float)
    limits.add_argument("--cap", type=float)
    jobs.add_parser("health")
    jobs.add_parser("cancel").add_argument("id")
    scheduler = groups.add_parser("scheduler").add_subparsers(dest="action", required=True)
    scheduler.add_parser("work").add_argument("--once", action="store_true")
    for command in (create, refresh_dataset, experiments.choices["run"], experiments.choices["sweep"], notebook, refresh):
        command.add_argument("--wait", action="store_true")
    return root


def initialize():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portfolio_lab.settings")
    import django
    django.setup()


def prepare(args):
    values = vars(args).copy()
    values.pop("wait", None)
    if args.group == "strategies" and args.action == "activate":
        values["scheduled"] = not values.pop("manual", False)
    if args.group == "strategies" and args.action == "recipe":
        values["recipe"] = json.loads(Path(args.recipe).read_text())
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
    # Deprecated argument retained for callers; every authorized client is equal.
    from research.commands import dispatch as application_command
    return application_command(values)


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
        service_command = args.group in {"app", "serve", "scheduler"} or args.group == "jobs" and args.action == "work"
        if service_command:
            initialize()
            if args.group == "app":
                from portfolio_lab.app import run
                run(args.port)
                return
            if args.group == "serve":
                from research.rpc import serve
                serve(args.socket)
                return
            result = dispatch(values)
        elif os.getenv("LAB_SOCKET"):
            result = remote(os.environ["LAB_SOCKET"], values)
        else:
            initialize()
            if args.group == "serve":
                from research.rpc import serve
                serve(args.socket)
                return
            with contextlib.redirect_stdout(sys.stderr):
                result = dispatch(values)
        if getattr(args, "wait", False):
            import time
            items = result if isinstance(result, list) else [result]
            done = []
            for item in items:
                while True:
                    query = {"group": "jobs", "action": "status", "id": item["job_id"]}
                    value = remote(os.environ["LAB_SOCKET"], query) if os.getenv("LAB_SOCKET") else dispatch(query)
                    if value["status"] in {"succeeded", "failed", "canceled"}: break
                    time.sleep(1)
                if value["status"] != "succeeded": raise ValueError(value["error"] or value["status"])
                done.append(value)
            result = done
        if args.group == "reports":
            Path(args.output).write_text(result["markdown"])
            result = {"output": str(Path(args.output).resolve())}
        print(json.dumps(result, allow_nan=False, default=str))
    except Exception as exc:
        # Only controlled application validation text is shown, not API responses.
        message = str(exc) if isinstance(exc, (ValueError, FileNotFoundError)) else "Command failed. Check identifiers, credentials, or runtime configuration locally."
        print(json.dumps({"error": message}), file=sys.stderr)
        raise SystemExit(1) from None
