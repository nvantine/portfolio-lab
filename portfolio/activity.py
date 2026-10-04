"""Small page revisions: polling never downloads stored price snapshots."""
import hashlib
import json
from research.models import Dataset, Experiment, Job, StrategyVersion
from research.jobs import health


def activity_state(scope):
    if scope not in {"datasets", "research", "strategies"}:
        raise ValueError("Unknown page scope")
    jobs = Job.objects.order_by("-created_at")
    if scope == "datasets": jobs = jobs.filter(kind="dataset")
    if scope == "strategies": jobs = jobs.filter(kind="notebook")
    state = {
        "datasets": list(Dataset.objects.order_by("pk").values_list("pk", "digest")),
        "jobs": list(jobs.values("id", "status", "error", "finished_at", "result__progress__completed", "result__accepted_dataset")[:30]),
    }
    if scope in {"research", "strategies"}:
        state["strategies"] = list(StrategyVersion.objects.order_by("pk").values_list("pk", "digest"))
    if scope == "research":
        state["runs"] = list(Experiment.objects.values("id", "status", "trashed_at")[:100])
    encoded = json.dumps(state, sort_keys=True, default=str).encode()
    return {"revision": hashlib.sha256(encoded).hexdigest(), "worker": health().get("worker", {"available": False})}


def live_context(scope):
    return {"live_scope": scope, "live_revision": activity_state(scope)["revision"], "health": health()}
