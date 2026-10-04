"""Background market fetch with explicit preview acceptance and frozen inputs."""
from datetime import date, timedelta
import re
import pandas as pd
from alpaca.data.enums import DataFeed
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from research.models import Job
from research.services import freeze_frame


def symbols(values):
    if isinstance(values, str):
        values = values.replace(",", " ").split()
    result = list(dict.fromkeys(str(t).strip().upper() for t in values))
    if not result or any(not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,11}", t) for t in result):
        raise ValueError("Enter ticker symbols such as AAPL, MSFT or SPY, separated by spaces or commas. Market-cap rankings and descriptions are not resolved automatically.")
    return result


def queue_fetch(tickers, start, end, name, feed="iex", benchmark="SPY", parent=None):
    tickers = symbols(tickers)
    try: first, last = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    except ValueError: raise ValueError("Dates must use YYYY-MM-DD") from None
    today = timezone.localdate()
    if last > today:
        raise ValueError("End date cannot be in the future")
    requested_end = last
    if last == today:
        last -= timedelta(days=1)
    if first >= last:
        raise ValueError("Start date must be before the end of the completed historical date range")
    if feed not in {"iex", "sip"}:
        raise ValueError("Feed must be iex or sip; SIP requires entitlement")
    if not name or len(name) > 120:
        raise ValueError("Supply a dataset name under 120 characters")
    benchmark = symbols([benchmark])[0] if benchmark else ""
    job = Job.objects.create(kind="dataset", payload={"tickers": tickers, "start": str(first), "end": str(last), "requested_end": str(requested_end), "name": name, "feed": feed, "benchmark": benchmark, "parent": parent})
    return {"job_id": str(job.pk), "status": job.status, "end": str(last), "requested_end": str(requested_end), "symbols": len(tickers)}


def fetch_preview(payload, progress=None):
    from marketdata.alpaca_client import get_client, fetch_daily_bars
    from marketdata.prices import save_daily_bars
    try: client = get_client()
    except ImproperlyConfigured:
        raise ValueError("Historical Alpaca credentials are missing. Set ALPACA_API_KEY and ALPACA_SECRET_KEY in the project .env file, then restart the worker.") from None
    series, coverage, failures = {}, {}, {}
    tickers = list(dict.fromkeys(payload["tickers"] + ([payload["benchmark"]] if payload["benchmark"] else [])))
    for index, ticker in enumerate(tickers):
        if progress: progress(completed=index, total=len(tickers), current=ticker)
        try:
            bars = fetch_daily_bars(client, ticker, date.fromisoformat(payload["start"]), date.fromisoformat(payload["end"]), feed=DataFeed(payload["feed"]))
            if not bars:
                raise ValueError("No bars")
            values = pd.Series({bar.timestamp.date(): float(bar.close) for bar in bars}, name=ticker).sort_index()
            series[ticker] = values
            coverage[ticker] = {"rows": len(values), "first": str(values.index[0]), "last": str(values.index[-1])}
            # The legacy cache is explicitly IEX only; never contaminate it with SIP.
            if payload["feed"] == "iex":
                save_daily_bars(ticker, bars)
        except Exception:
            failures[ticker] = "Daily bars unavailable; check symbol, dates, feed entitlement, and API configuration"
    if progress: progress(completed=len(tickers), total=len(tickers), current="")
    if not series:
        raise ValueError("No usable daily bars; check local credentials, dates, and symbols")
    frame = pd.DataFrame(series).sort_index()
    aligned = frame.dropna()
    return {"coverage": coverage, "failures": failures, "observed_rows": len(frame), "aligned_rows": len(aligned), "lost_dates": len(frame) - len(aligned),
            "snapshot": {"dates": [str(day) for day in frame.index], "tickers": list(frame), "prices": frame.astype(object).where(frame.notna(), None).to_numpy().tolist()}}


def accept_preview(job_id, accept_reduced=False):
    job = Job.objects.filter(pk=job_id, kind="dataset", status="succeeded").first()
    if job is None: raise ValueError("Choose a completed dataset-fetch preview before saving")
    value = job.result
    if (value["failures"] or value["lost_dates"]) and not accept_reduced:
        raise ValueError("Review coverage and explicitly accept reduced symbols/dates")
    snapshot = value["snapshot"]
    frame = pd.DataFrame(snapshot["prices"], index=pd.to_datetime(snapshot["dates"]), columns=snapshot["tickers"], dtype=float)
    assets = [ticker for ticker in job.payload["tickers"] if ticker in frame]
    if not assets:
        raise ValueError("No selected assets remain")
    manifest = {"assets": assets, "benchmark": job.payload["benchmark"] if job.payload["benchmark"] in frame else "", "feed": job.payload["feed"], "request": job.payload, "coverage": value["coverage"], "excluded": value["failures"], "parent": job.payload.get("parent")}
    dataset = freeze_frame(frame, job.payload["name"], f"Alpaca {job.payload['feed'].upper()}, adjustment=all", extra_manifest=manifest)
    job.result = dict(value, accepted_dataset=dataset.pk)
    job.save(update_fields=["result"])
    return {"dataset": dataset.pk, "digest": dataset.digest, "manifest": dataset.manifest}
