"""Trusted application services shared by the operator UI and CLI."""
import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from django.conf import settings
from django.db import transaction

from backtest.engine import evaluate
from marketdata.models import PricePoint
from research.models import Dataset, Experiment, Job, StrategyVersion
from strategies.builtin import target_weights, covariance
from strategies.catalog import METHODS, COVARIANCES


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def freeze_frame(frame, name="ETF snapshot", source="Alpaca IEX, adjustment=all", extra_manifest=None):
    frame = frame.sort_index().sort_index(axis=1)
    if frame.index.has_duplicates or frame.columns.has_duplicates:
        raise ValueError("Duplicate dates or symbols")
    before = len(frame)
    frame = frame.dropna()
    if len(frame) < 250 or not np.isfinite(frame.to_numpy()).all() or (frame <= 0).any().any():
        raise ValueError("Need at least 250 aligned, positive daily closes")
    snapshot = {"dates": [str(day.date()) for day in frame.index], "tickers": list(frame.columns), "prices": frame.to_numpy().tolist()}
    manifest = {"source": source, "aligned_rows": len(frame), "dropped_rows": before - len(frame),
                "train_end": int(len(frame) * .6), "validation_end": int(len(frame) * .8),
                "alignment": "Common observed dates; no forward fill", "schema": 1}
    manifest.update(extra_manifest or {})
    dataset, _ = Dataset.objects.get_or_create(digest=digest({"snapshot": snapshot, "manifest": manifest}), defaults={"name": name, "snapshot": snapshot, "manifest": manifest})
    return dataset


def freeze_prices(tickers, name="ETF snapshot"):
    rows = list(PricePoint.objects.filter(asset__ticker__in=tickers).values_list("date", "asset__ticker", "adjusted_close"))
    if not rows:
        raise ValueError("No cached prices. Run data refresh first")
    frame = pd.DataFrame(rows, columns=["date", "ticker", "price"])
    frame["price"] = frame["price"].astype(float)
    frame = frame.pivot(index="date", columns="ticker", values="price")
    frame.index = pd.to_datetime(frame.index)
    missing = set(tickers) - set(frame.columns)
    if missing:
        raise ValueError("Missing cached assets: " + ", ".join(sorted(missing)))
    return freeze_frame(frame, name)


def materialize(dataset):
    if digest({"snapshot": dataset.snapshot, "manifest": dataset.manifest}) != dataset.digest:
        raise ValueError("Dataset integrity check failed")
    return pd.DataFrame(dataset.snapshot["prices"], index=pd.to_datetime(dataset.snapshot["dates"]), columns=dataset.snapshot["tickers"])


def register_strategy(name, source):
    if not name or len(name) > 120 or len(source.encode()) > 100_000:
        raise ValueError("Strategy needs a short name and source under 100 KB")
    import ast
    tree = ast.parse(source)
    if not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "target_weights" for node in tree.body):
        raise ValueError("Define target_weights(history, current_weights, parameters)")
    value, _ = StrategyVersion.objects.get_or_create(digest=hashlib.sha256(source.encode()).hexdigest(), defaults={"name": name, "source": source})
    return value


def register_recipe(name, recipe):
    from strategies.recipes import validate_recipe
    validate_recipe(recipe)
    validate_config({"dataset": 1, "parameters": recipe.get("parameters", {})})
    if not name or len(name) > 120:
        raise ValueError("Supply a short strategy name")
    value, _ = StrategyVersion.objects.get_or_create(digest=digest({"recipe": recipe}), defaults={"name": name, "source": "", "kind": "recipe", "recipe": recipe})
    return value


def provenance():
    import importlib.metadata
    import platform
    root = settings.BASE_DIR
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=False).stdout)
    lock = root / "uv.lock"
    # Also hash source so an uncommitted run still has an identifiable evaluator.
    paths = sorted(p for folder in ("optimizer", "backtest", "strategies", "research", "workers", "paper") for p in (root / folder).rglob("*.py"))
    code = hashlib.sha256(b"".join(str(p.relative_to(root)).encode() + p.read_bytes() for p in paths)).hexdigest()
    versions = {name: importlib.metadata.version(name) for name in ("django", "pandas", "numpy", "scipy", "cvxpy", "scikit-learn", "plotly", "alpaca-py", "nbclient", "nbformat")}
    return {"git_revision": revision, "dirty": dirty, "source_digest": code, "lock_digest": hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else "", "python": platform.python_version(), "platform": platform.platform(), "versions": versions, "engine_schema": 1}


def validate_config(config, agent=False):
    config = dict(config)
    json.dumps(config, allow_nan=False)
    if set(config) - {"dataset", "method", "strategy", "parameters", "seed", "window", "hypothesis", "schema"}:
        raise ValueError("Unknown experiment fields")
    if config.get("schema", 1) != 1 or config.get("window", "validation") not in ("validation", "holdout"):
        raise ValueError("Unsupported schema or window")
    if config.get("method", "min_variance") not in METHODS:
        raise ValueError("Unknown registered method")
    if not isinstance(config.get("dataset"), int) or isinstance(config["dataset"], bool) or config["dataset"] <= 0:
        raise ValueError("Supply an existing positive dataset ID")
    seed = config.get("seed", 42)
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**32:
        raise ValueError("Seed must be an integer between 0 and 2^32-1")
    if not isinstance(config.get("hypothesis", ""), str) or len(config.get("hypothesis", "")) > 4000:
        raise ValueError("Hypothesis must be text under 4000 characters")
    parameters = dict(config.get("parameters", {}))
    allowed = {"cap", "lookback", "covariance", "risk_aversion", "turnover_limit", "cost_bps", "robust_radius", "confidence", "views", "view_uncertainty", "tau", "ridge_alpha", "target_volatility", "rebalance", "recipe", "fixed_weights", "benchmark_weights", "allow_short", "net_exposure", "gross_limit", "short_cap", "borrow_rate", "financing_rate", "ewma_decay", "turnover_penalty_bps"}
    if set(parameters) - allowed:
        raise ValueError("Unknown strategy parameters")
    for key, value in parameters.items():
        if key in {"covariance", "views", "rebalance", "recipe", "fixed_weights", "benchmark_weights", "allow_short"} or key == "turnover_limit" and value is None:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError(f"{key} must be a finite number")
        if value < 0 or key in {"cap", "confidence", "view_uncertainty", "tau", "target_volatility"} and value == 0:
            raise ValueError(f"{key} is outside its permitted range")
    if "lookback" in parameters and not isinstance(parameters["lookback"], int):
        raise ValueError("Lookback must be an integer")
    if not 0 < parameters.get("confidence", .95) < 1 or parameters.get("turnover_limit") is not None and not 0 <= parameters["turnover_limit"] <= 2:
        raise ValueError("Confidence must be in (0, 1); turnover must be in [0, 2]")
    if not 0 <= parameters.get("cost_bps", 10) <= 1000 or parameters.get("rebalance", "monthly") not in {"daily", "weekly", "monthly"}:
        raise ValueError("Costs must be 0–1000 bps; rebalance daily, weekly, or monthly")
    views = parameters.get("views", {})
    if not isinstance(views, dict) or any(not isinstance(key, str) or not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) for key, value in views.items()):
        raise ValueError("Views must map ticker names to finite daily return estimates")
    if parameters.get("covariance", "ledoit_wolf") not in COVARIANCES:
        raise ValueError("Unknown covariance estimator")
    if not isinstance(parameters.get("allow_short", False), bool): raise ValueError("allow_short must be boolean")
    if parameters.get("gross_limit", 1.5) < abs(parameters.get("net_exposure", 1)) or not 0 <= parameters.get("short_cap", .2) <= 1:
        raise ValueError("Invalid signed exposure limits")
    if not 0 < parameters.get("ewma_decay", .94) < 1: raise ValueError("EWMA decay must be in (0, 1)")
    for key in ("fixed_weights", "benchmark_weights"):
        value = parameters.get(key, {})
        if not isinstance(value, dict) or any(not isinstance(t, str) or not isinstance(w, (int, float)) or isinstance(w, bool) or not math.isfinite(w) for t, w in value.items()):
            raise ValueError(f"{key} must map symbols to finite weights")
    if parameters.get("recipe"):
        from strategies.recipes import validate_recipe
        validate_recipe(dict(parameters["recipe"], parameters=parameters))
    if not 0 < float(parameters.get("cap", .2)) <= 1:
        raise ValueError("Position cap must be in (0, 1]")
    if not 10 <= int(parameters.get("lookback", 126)) <= 2520:
        raise ValueError("Lookback must be between 10 and 2520")
    config.update(schema=1, seed=seed, window=config.get("window", "validation"), parameters=parameters, method=config.get("method", "min_variance"))
    return config


@transaction.atomic
def queue_experiment(config, agent=False):
    config = validate_config(config, agent)
    dataset = Dataset.objects.get(pk=config["dataset"])
    materialize(dataset)
    strategy = StrategyVersion.objects.get(digest=config["strategy"]) if config.get("strategy") else None
    if strategy and strategy.kind == "recipe":
        if strategy.digest != digest({"recipe": strategy.recipe}): raise ValueError("Recipe integrity check failed")
        config["method"] = "recipe"
        config["parameters"] = strategy.recipe.get("parameters", {}) | config["parameters"] | {"recipe": strategy.recipe}
        config = validate_config(config)
    if config["method"] == "recipe" and not config["parameters"].get("recipe") and not strategy:
        raise ValueError("Select a saved recipe or provide recipe components")
    if strategy and strategy.kind == "python": config["method"] = "custom"
    if config["method"] == "custom" and not strategy: raise ValueError("Custom method requires a registered Python version")
    run = Experiment.objects.create(dataset=dataset, strategy=strategy, config=config, hypothesis=config.get("hypothesis", ""), provenance=provenance())
    job = Job.objects.create(kind="experiment", experiment=run, payload={})
    return {"job_id": str(job.pk), "run_id": str(run.pk), "status": job.status}


def run_experiment(run):
    all_prices = materialize(run.dataset)
    prices = all_prices.loc[:, run.dataset.manifest.get("assets", list(all_prices))]
    config = validate_config(run.config)
    parameters = dict(config["parameters"], method=config["method"])
    if run.strategy and run.strategy.kind == "recipe":
        if run.strategy.digest != digest({"recipe": run.strategy.recipe}): raise ValueError("Recipe integrity check failed")
        parameters = run.strategy.recipe.get("parameters", {}) | config["parameters"] | {"recipe": run.strategy.recipe, "method": "recipe"}
        parameters.pop("method")
        parameters = validate_config(dict(config, parameters=parameters))["parameters"] | {"method": "recipe"}
    start = run.dataset.manifest["train_end"] if config["window"] == "validation" else run.dataset.manifest["validation_end"]
    end = run.dataset.manifest["validation_end"] if config["window"] == "validation" else len(prices)
    parameters.setdefault("cap", .2)
    if run.strategy and run.strategy.kind == "python":
        from workers.isolation import StrategyProcess
        if hashlib.sha256(run.strategy.source.encode()).hexdigest() != run.strategy.digest:
            raise ValueError("Strategy integrity check failed")
        with StrategyProcess(run.strategy.source, seed=config["seed"]) as isolated:
            run.provenance = dict(run.provenance, worker_image=isolated.image_digest)
            run.save(update_fields=["provenance"])
            result = evaluate(prices, isolated.weights, parameters, start, end, config["seed"])
    else:
        result = evaluate(prices, target_weights, parameters, start, end, config["seed"])
    baseline = {key: value for key, value in parameters.items() if key not in {"recipe", "allow_short", "fixed_weights", "net_exposure"}}
    equal = evaluate(prices, target_weights, dict(baseline, method="equal_weight", cap=1, turnover_limit=None), start, end, config["seed"])
    result["benchmarks"] = {"equal_weight": equal}
    benchmark = run.dataset.manifest.get("benchmark", "SPY")
    if benchmark in all_prices:
        result["benchmarks"][benchmark] = evaluate(all_prices[[benchmark]], lambda history, current, params: {benchmark: 1.0}, dict(baseline, cap=1), start, end, config["seed"])
    from optimizer.risk import metrics
    result["metrics"].update(metrics(result["returns"], benchmark=equal["returns"]))
    result["trial_count"] = Experiment.objects.filter(dataset=run.dataset).count()
    result["warning"] = "Repeated validation trials are selection, not independent evidence. Holdout must stay untouched until method selection is final."
    recent = prices.iloc[:end].tail(int(parameters.get("lookback", 126)) + 1).pct_change(fill_method=None).dropna()
    sigma = covariance(recent, parameters.get("covariance", "ledoit_wolf"), parameters.get("ewma_decay", .94))
    result["covariance"] = {"tickers": list(sigma.columns), "values": sigma.to_numpy().tolist()}
    from optimizer.advanced import efficient_frontier
    result["frontier"] = efficient_frontier(sigma, recent.mean(), cap=parameters["cap"]) if not parameters.get("allow_short") and len(prices.columns)*parameters["cap"] >= 1 else []
    result["diagnostics"] = {"note": "Frontier omitted for signed research or an infeasible fully-invested long-only cap."} if not result["frontier"] else {}
    if config["method"] in ("min_variance", "mean_variance", "cvar", "robust") and not run.strategy and not parameters.get("allow_short"):
        from optimizer.advanced import allocation
        fitted = allocation(sigma, recent.mean(), method=config["method"], cap=parameters["cap"], risk_aversion=parameters.get("risk_aversion", 10), scenarios=recent, robust_radius=parameters.get("robust_radius", .001) if config["method"] == "robust" else 0)
        result["diagnostics"] = {"duals": fitted["duals"], "note": "At evaluation end; objective-unit sensitivities, not return forecasts. No trade-cost penalty in this diagnostic fit."}
    last = pd.Series(result["weights"][-1]).reindex(sigma.columns)
    variance = float(last @ sigma @ last)
    result["risk_contributions"] = (last * (sigma @ last) / variance).to_dict() if variance > 0 else {}
    from research.simulation import simulate
    result["simulation"] = simulate(prices.iloc[:start], seed=config["seed"])
    return result


def queue_notebook(dataset_id, notebook):
    import nbformat
    nbformat.validate(nbformat.reads(json.dumps(notebook), as_version=4))
    if len(json.dumps(notebook)) > 1_000_000:
        raise ValueError("Notebook exceeds 1 MB")
    dataset = Dataset.objects.get(pk=dataset_id)
    materialize(dataset)
    job = Job.objects.create(kind="notebook", payload={"dataset": dataset.pk, "notebook": notebook, "notebook_digest": digest(notebook), "provenance": provenance()})
    return {"job_id": str(job.pk), "status": job.status}


@transaction.atomic
def trash_run(run_id, restore=False):
    from django.utils import timezone
    run = Experiment.objects.get(pk=run_id)
    job = Job.objects.filter(experiment=run).first()
    if run.status == "running" or job and job.status == "running":
        raise ValueError("Wait for the running experiment before deleting it")
    if not restore and job and job.status == "queued":
        job.status, job.finished_at = "canceled", timezone.now()
        job.save(update_fields=["status", "finished_at"])
        run.status = "canceled"
    run.trashed_at = None if restore else timezone.now()
    run.save(update_fields=["trashed_at", "status"])
    return {"id": str(run.pk), "trashed": run.trashed_at is not None}
