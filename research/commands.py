"""One application command interface for the dashboard and owner-authorized CLI."""
import json
from django.db import transaction
from research import services
from research.models import Dataset, Experiment, Job, StrategyVersion


def dispatch(values, user=None):
    group, action = values["group"], values.get("action")
    if group == "methods":
        from strategies.catalog import catalog
        from strategies.recipes import SIGNALS, ALLOCATORS
        values = catalog()
        for item in values:
            if item["name"] == "recipe": item.update(signals=SIGNALS, allocators=ALLOCATORS)
        return values
    if group == "datasets":
        from research.datasets import queue_fetch, accept_preview
        if action == "list": return list(Dataset.objects.values("id", "name", "digest", "manifest"))
        if action == "create": return queue_fetch(values["tickers"], values["start"], values["end"], values["name"], values.get("feed", "iex"), values.get("benchmark", "SPY"))
        if action == "accept": return accept_preview(values["id"], values.get("accept_reduced", False))
        if action == "refresh":
            dataset = Dataset.objects.get(pk=values["id"])
            request = dataset.manifest.get("request")
            if not request: raise ValueError("Legacy/synthetic snapshots need a new dataset request")
            from datetime import date, timedelta
            return queue_fetch(request["tickers"], request["start"], values.get("end") or str(date.today()-timedelta(days=1)), dataset.name, request["feed"], request["benchmark"], dataset.pk)
        if action == "demo":
            import numpy as np
            import pandas as pd
            rng = np.random.default_rng(values.get("seed", 42))
            frame = pd.DataFrame(100*np.exp(np.cumsum(rng.normal(.0003, .012, (630, 6)), axis=0)), index=pd.bdate_range("2022-01-03", periods=630), columns=["SPY", "QQQ", "AGG", "GLD", "TLT", "EFA"])
            dataset = services.freeze_frame(frame, "SYNTHETIC demonstration", "Synthetic seeded independent Gaussian daily log returns")
        elif action == "freeze": dataset = services.freeze_prices(values["tickers"], values.get("name", "Snapshot"))
        else: raise ValueError("Unknown dataset action")
        return {"dataset": dataset.pk, "digest": dataset.digest, "manifest": dataset.manifest}
    if group == "data":
        # Historical refresh uses the same queued preview flow and explicit feed.
        from datetime import date, timedelta
        from marketdata.universe import DEFAULT_ETFS
        from research.datasets import queue_fetch
        return queue_fetch(values.get("tickers") or DEFAULT_ETFS, values.get("start") or "2020-01-01", values.get("end") or str(date.today()-timedelta(days=1)), "Market refresh", values.get("feed", "iex"))
    if group == "strategies":
        if action == "list": return list(StrategyVersion.objects.values("name", "digest", "kind", "recipe"))
        if action == "show":
            strategy = StrategyVersion.objects.get(digest=values["id"])
            return {"name": strategy.name, "digest": strategy.digest, "kind": strategy.kind, "source": strategy.source, "recipe": strategy.recipe}
        if action in {"register", "recipe"}:
            strategy = services.register_strategy(values["name"], values["source"]) if action == "register" else services.register_recipe(values["name"], values["recipe"])
            return {"name": strategy.name, "digest": strategy.digest, "kind": strategy.kind}
        from paper import account
        if action == "status": return account.status()
        if action == "activate": return account.activate(values["run"], values["budget"], user=user, scheduled=values.get("scheduled", True))
        if action == "cycle": return account.cycle()
        if action in {"pause", "resume", "close", "revoke"}: return account.control(values["session"], action)
        if action == "adopt": return account.adopt(values["session"], values["symbol"], values["qty"])
        if action == "limits": return account.set_limits(values.get("budget"), values.get("cap"))
    if group == "experiments":
        configs = values["config"] if action == "sweep" else [values["config"]]
        if not isinstance(configs, list) or not configs: raise ValueError("Supply at least one configuration")
        with transaction.atomic(): return [services.queue_experiment(config) for config in configs]
    if group == "notebooks":
        source = values["source"]
        return services.queue_notebook(values["dataset"], json.loads(source) if isinstance(source, str) else source)
    if group == "jobs":
        from research.jobs import public_job, work, health
        if action == "health": return health()
        if action == "work": return work(values.get("once", False))
        if action == "cancel":
            with transaction.atomic():
                job = Job.objects.get(pk=values["id"])
                if job.status != "queued": raise ValueError("Only queued jobs can be canceled")
                job.status = "canceled"
                job.save(update_fields=["status"])
                if job.experiment_id:
                    job.experiment.status = "canceled"
                    job.experiment.save(update_fields=["status"])
            return public_job(job)
        if values.get("id"): return public_job(Job.objects.get(pk=values["id"]))
        return [public_job(job) for job in Job.objects.order_by("-created_at")[:100]]
    if group == "runs":
        def summary(run):
            return {"id": str(run.pk), "dataset": run.dataset_id, "method": run.config.get("method"), "status": run.status, "metrics": run.results.get("metrics", {}), "error": run.error, "trashed": bool(run.trashed_at)}
        if action in {"trash", "restore"}: return services.trash_run(values["id"], restore=action == "restore")
        if action == "list": return [summary(run) for run in Experiment.objects.filter(trashed_at__isnull=not values.get("trash", False))[:100]]
        if action == "compare":
            runs = [Experiment.objects.get(pk=key) for key in values["ids"]]
            signatures = {(r.dataset_id, r.config.get("window"), r.config.get("seed"), r.config.get("parameters", {}).get("cost_bps", 10)) for r in runs}
            return {"runs": [summary(run) for run in runs], "matching_assumptions": len(signatures) <= 1}
        run = Experiment.objects.get(pk=values["id"])
        return dict(summary(run), config=run.config, provenance=run.provenance, results=run.results)
    if group == "reports":
        from research.reporting import report
        return {"markdown": report(Experiment.objects.get(pk=values["id"]))}
    if group == "paper":
        return dispatch(dict(values, group="strategies", action="status" if action == "status" else "cycle"), user=user)
    if group == "scheduler":
        from research.scheduler import work
        return work(values.get("once", False))
    raise ValueError("Unsupported command")
