"""Background market fetch with explicit preview acceptance and frozen inputs."""
from datetime import date
import re
import pandas as pd
from alpaca.data.enums import DataFeed
from research.models import Job
from research.services import freeze_frame


def symbols(values):
    if isinstance(values, str):
        values = values.replace(",", " ").split()
    result = list(dict.fromkeys(str(t).strip().upper() for t in values))
    if not result or any(not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,11}", t) for t in result):
        raise ValueError("Supply valid stock or ETF symbols")
    return result


def queue_fetch(tickers, start, end, name, feed="iex", benchmark="SPY", parent=None):
    tickers = symbols(tickers)
    first, last = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    if first >= last or last >= date.today():
        raise ValueError("Choose an ordered historical date range ending before today")
    if feed not in {"iex", "sip"}:
        raise ValueError("Feed must be iex or sip; SIP requires entitlement")
    if not name or len(name) > 120:
        raise ValueError("Supply a dataset name under 120 characters")
    benchmark = symbols([benchmark])[0] if benchmark else ""
    job = Job.objects.create(kind="dataset", payload={"tickers": tickers, "start": str(first), "end": str(last), "name": name, "feed": feed, "benchmark": benchmark, "parent": parent})
    return {"job_id": str(job.pk), "status": job.status}


def fetch_preview(payload):
    from marketdata.alpaca_client import get_client, fetch_daily_bars
    from marketdata.prices import save_daily_bars
    client = get_client()
    series, coverage, failures = {}, {}, {}
    tickers = list(dict.fromkeys(payload["tickers"] + ([payload["benchmark"]] if payload["benchmark"] else [])))
    for ticker in tickers:
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
    if not series:
        raise ValueError("No usable daily bars; check local credentials, dates, and symbols")
    frame = pd.DataFrame(series).sort_index()
    aligned = frame.dropna()
    return {"coverage": coverage, "failures": failures, "observed_rows": len(frame), "aligned_rows": len(aligned), "lost_dates": len(frame) - len(aligned),
            "snapshot": {"dates": [str(day) for day in frame.index], "tickers": list(frame), "prices": frame.astype(object).where(frame.notna(), None).to_numpy().tolist()}}


def accept_preview(job_id, accept_reduced=False):
    job = Job.objects.get(pk=job_id, kind="dataset", status="succeeded")
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
    return {"dataset": dataset.pk, "digest": dataset.digest, "manifest": dataset.manifest}
