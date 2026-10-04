"""Exercise real dashboard validation/queue/save paths with fake historical bars."""
from datetime import date, timedelta
from types import SimpleNamespace
import json
import pytest
from django.utils import timezone
from portfolio.forms import DatasetForm
from research.models import Dataset, Job
from research.datasets import queue_fetch
from research.jobs import work


@pytest.fixture
def dashboard(client, django_user_model):
    client.force_login(django_user_model.objects.create_user(username="dataset-reviewer", is_staff=True))
    return client


@pytest.fixture
def fake_bars(monkeypatch, prices):
    bars = [SimpleNamespace(timestamp=stamp, close=float(value)) for stamp, value in prices.SPY.items()]
    calls = []
    monkeypatch.setattr("marketdata.alpaca_client.get_client", lambda: object())
    def fetch(client, ticker, start, end, **kwargs):
        calls.append(ticker)
        return bars
    monkeypatch.setattr("marketdata.alpaca_client.fetch_daily_bars", fetch)
    monkeypatch.setattr("marketdata.prices.save_daily_bars", lambda ticker, bars: None)
    return calls


def form_data(tickers="SPY", end="2021-12-31"):
    return {"name": "Dashboard dataset", "tickers": tickers, "start": "2020-01-01", "end": end, "feed": "iex", "benchmark": ""}


@pytest.mark.django_db
@pytest.mark.parametrize("count", [1, 100])
def test_dashboard_fetch_progress_save_and_visibility(dashboard, fake_bars, settings, tmp_path, count):
    settings.LAB_DATA_DIR = tmp_path
    tickers = ["SPY"] if count == 1 else [f"T{i:03}" for i in range(count)]
    initial = dashboard.get("/activity/status/?scope=datasets").json()["revision"]
    response = dashboard.post("/datasets/", form_data(", ".join(tickers)))
    assert response.status_code == 302
    assert response.url == "/datasets/#fetch-jobs"
    job = Job.objects.get(kind="dataset")
    assert job.payload["tickers"] == tickers and not Dataset.objects.exists()
    queued = dashboard.get("/activity/status/?scope=datasets").json()["revision"]
    assert queued != initial
    assert b"This is not a saved dataset yet" in dashboard.get("/datasets/").content
    assert work(once=True)["status"] == "succeeded"
    job.refresh_from_db()
    assert fake_bars == tickers and job.result["aligned_rows"] == 420
    ready = dashboard.get("/activity/status/?scope=datasets").json()["revision"]
    assert ready != queued
    assert b"Preview ready" in dashboard.get("/datasets/").content
    accepted = dashboard.post("/datasets/", {"action": "accept", "id": job.pk})
    assert accepted.status_code == 302
    dataset = Dataset.objects.get()
    assert dataset.manifest["assets"] == tickers
    job.refresh_from_db()
    assert job.result["accepted_dataset"] == dataset.pk
    assert dashboard.get("/activity/status/?scope=datasets").json()["revision"] != ready
    assert b"Dashboard dataset" in dashboard.get("/").content
    assert b"Saved as snapshot" in dashboard.get("/datasets/").content
    # Neither following the redirect nor accepting twice produces another job/snapshot.
    dashboard.get(accepted.url)
    dashboard.post("/datasets/", {"action": "accept", "id": job.pk})
    assert Dataset.objects.count() == 1 and Job.objects.count() == 1


@pytest.mark.django_db
def test_today_is_accepted_and_incomplete_day_excluded(dashboard, monkeypatch):
    today = date(2026, 10, 3)
    monkeypatch.setattr("research.datasets.timezone.localdate", lambda: today)
    response = dashboard.post("/datasets/", form_data(end=str(today)))
    assert response.status_code == 302
    job = Job.objects.get()
    assert job.payload["end"] == "2026-10-02" and job.payload["requested_end"] == "2026-10-03"
    # CLI/shared service follows the same rule.
    assert queue_fetch("SPY", "2021-10-03", str(today), "Five years")["end"] == "2026-10-02"


@pytest.mark.django_db
@pytest.mark.parametrize("changes,message", [
    ({"tickers": "top 100 market cap nasdaq tickers"}, "Enter ticker symbols"),
    ({"end": "bad-date"}, "Enter a valid date"),
    ({"start": "2022-01-01"}, "Start date must be before"),
    ({"end": str(timezone.localdate()+timedelta(days=1))}, "End date cannot be in the future"),
    ({"feed": "invalid"}, "Select a valid choice"),
    ({"name": ""}, "This field is required"),
])
def test_rejected_submission_is_prominent_and_creates_no_job(dashboard, changes, message):
    response = dashboard.post("/datasets/", form_data() | changes)
    assert response.status_code == 400
    assert b"Dataset was not queued" in response.content
    assert message.encode() in response.content
    assert not Job.objects.exists() and not Dataset.objects.exists()


@pytest.mark.django_db
def test_missing_credentials_are_friendly_and_progress_is_observable(dashboard, settings, tmp_path):
    settings.LAB_DATA_DIR = tmp_path
    settings.ALPACA_API_KEY = settings.ALPACA_SECRET_KEY = ""
    dashboard.post("/datasets/", form_data())
    assert work(once=True)["status"] == "failed"
    assert "Historical Alpaca credentials are missing" in Job.objects.get().error
    assert b"Historical Alpaca credentials are missing" in dashboard.get("/datasets/").content


@pytest.mark.django_db
def test_activity_revision_is_small_stable_and_protected(dashboard, client):
    queued = queue_fetch("SPY", "2020-01-01", "2021-12-31", "Preview")
    job = Job.objects.get(pk=queued["job_id"])
    job.status = "running"
    job.result = {"progress": {"completed": 0, "total": 1, "current": "SPY"}, "snapshot": {"private_prices": "x"*100_000}}
    job.save()
    first = dashboard.get("/activity/status/?scope=datasets")
    assert len(first.content) < 1000 and b"private_prices" not in first.content
    assert first.json()["revision"] == dashboard.get("/activity/status/?scope=datasets").json()["revision"]
    job.result["progress"]["completed"] = 1
    job.save()
    assert first.json()["revision"] != dashboard.get("/activity/status/?scope=datasets").json()["revision"]
    assert dashboard.get("/activity/status/?scope=bad").status_code == 400
    dashboard.logout()
    assert client.get("/activity/status/?scope=datasets").status_code == 302


@pytest.mark.django_db
def test_short_history_and_reduced_preview_remain_explicit(dashboard):
    response = queue_fetch("SPY", "2020-01-01", "2021-12-31", "Short history")
    job = Job.objects.get(pk=response["job_id"])
    pending = dashboard.post("/datasets/", {"action": "accept", "id": job.pk})
    assert pending.status_code == 400 and b"completed dataset-fetch preview" in pending.content
    job.status = "succeeded"
    job.result = {"aligned_rows": 10, "lost_dates": 0, "coverage": {}, "failures": {}}
    job.save()
    assert b"Not enough common history" in dashboard.get("/datasets/").content
    job.result["aligned_rows"], job.result["lost_dates"] = 300, 1
    job.save()
    response = dashboard.post("/datasets/", {"action": "accept", "id": job.pk})
    assert response.status_code == 400
    assert b"explicitly accept reduced" in response.content


@pytest.mark.django_db
def test_live_hooks_and_notebook_redirect(dashboard, prices, monkeypatch):
    from research.services import freeze_frame
    dataset = freeze_frame(prices)
    job = Job.objects.create(kind="notebook", payload={"dataset": dataset.pk})
    monkeypatch.setattr("research.services.queue_notebook", lambda *args: {"job_id": str(job.pk), "status": "queued"})
    response = dashboard.post("/strategies/", {"action": "notebook", "dataset": dataset.pk, "source": json.dumps({})})
    assert response.status_code == 302 and response.url == f"/notebooks/{job.pk}/"
    assert b"data-job-status" in dashboard.get(response.url).content
    for url in ("/", "/datasets/", "/strategies/"):
        page = dashboard.get(url)
        assert b"data-live-status" in page.content and b"data-live-region" in page.content


def test_symbol_normalization_and_form_hints():
    form = DatasetForm(form_data("aapl,\nMSFT AAPL"))
    assert form.is_valid(), form.errors
    assert form.cleaned_data["tickers"] == ["AAPL", "MSFT"]
