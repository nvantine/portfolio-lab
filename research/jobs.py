"""Serial durable queue; a host lock prevents concurrent consumers."""
import fcntl
import json
import time

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from research.models import Job, Dataset, ServiceHeartbeat


def heartbeat(name, **details):
    ServiceHeartbeat.objects.update_or_create(name=name, defaults={"updated_at": timezone.now(), "details": details})


def health():
    now = timezone.now()
    return {item.name: {"available": (now - item.updated_at).total_seconds() < 90, "updated_at": item.updated_at.isoformat(), **item.details} for item in ServiceHeartbeat.objects.all()}
from research.services import run_experiment, materialize


def public_job(job):
    return {"id": str(job.pk), "kind": job.kind, "status": job.status, "run_id": str(job.experiment_id) if job.experiment_id else None, "error": job.error, "result": job.result}


def perform(job):
    try:
        if job.kind == "experiment":
            run = job.experiment
            run.status = "running"
            run.save(update_fields=["status"])
            run.results = run_experiment(run)
            # Guarantee JSON never contains NaN/Infinity.
            json.dumps(run.results, allow_nan=False)
            run.status = "succeeded"
            run.save(update_fields=["results", "status"])
            job.result = {"run_id": str(run.pk)}
        elif job.kind == "notebook":
            from workers.isolation import StrategyProcess
            dataset = Dataset.objects.get(pk=job.payload["dataset"])
            frame = materialize(dataset).iloc[:dataset.manifest["train_end"]]
            with StrategyProcess() as worker:
                job.result = worker.request({"action": "notebook", "notebook": job.payload["notebook"], "dates": [str(day.date()) for day in frame.index], "tickers": list(frame.columns), "prices": frame.to_numpy().tolist()})
                job.result["worker_image"] = worker.image_digest
        else:
            raise ValueError("Unknown job type")
        job.status = "succeeded"
    except Exception as exc:
        from workers.isolation import IsolationError
        # Generated exception strings never leave the container. Host errors are
        # restricted to value/runtime errors; SDK errors can contain credentials.
        job.error = str(exc)[:500] if isinstance(exc, (ValueError, IsolationError)) else "Job failed; inspect the input and local configuration"
        job.status = "failed"
        if job.experiment_id:
            job.experiment.status, job.experiment.error = "failed", job.error
            job.experiment.save(update_fields=["status", "error"])
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "result", "error", "finished_at"])


def work(once=False):
    settings.LAB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with (settings.LAB_DATA_DIR / "worker.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("A queue worker is already running") from exc
        # A previous owner crashed. Record failures rather than silently rerun.
        for stale in Job.objects.filter(status="running"):
            stale.status, stale.error, stale.finished_at = "failed", "Worker interrupted; submit a new trial", timezone.now()
            stale.save()
            if stale.experiment_id:
                stale.experiment.status, stale.experiment.error = "failed", stale.error
                stale.experiment.save()
        while True:
            heartbeat("worker", status="ready")
            with transaction.atomic():
                job = Job.objects.filter(status="queued").order_by("created_at").first()
                if job:
                    job.status, job.started_at = "running", timezone.now()
                    job.save(update_fields=["status", "started_at"])
            if job:
                perform(job)
            if once:
                return public_job(job) if job else {"status": "idle"}
            if not job:
                time.sleep(1)
