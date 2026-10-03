"""Human-approved paper lifecycle; uncertain submissions are never retried."""
import hashlib
import json
from decimal import Decimal, ROUND_DOWN

from django.db import transaction
from marketdata.universe import DEFAULT_ETFS
from paper.models import PaperSession, PaperOrder
from research.models import Experiment
from research.services import digest, materialize, provenance

TERMINAL = {"filled", "canceled", "expired", "rejected", "replaced"}


def fingerprint(run):
    strategy = hashlib.sha256(run.strategy.source.encode()).hexdigest() if run.strategy else None
    return digest({"config": run.config, "dataset": run.dataset.digest, "strategy": strategy,
                   "provenance": run.provenance, "results": run.results})


@transaction.atomic
def approve(run_id, user, budget=10000):
    if not user.is_authenticated or not user.is_staff:
        raise ValueError("Operator authentication is required")
    run = Experiment.objects.select_related("dataset", "strategy").get(pk=run_id)
    if run.status != "succeeded" or run.config.get("window") != "validation":
        raise ValueError("Approve a successful validation experiment")
    frame = materialize(run.dataset)
    if set(frame.columns) - set(DEFAULT_ETFS) or run.dataset.manifest["source"].startswith("Synthetic"):
        raise ValueError("Paper execution needs an Alpaca snapshot of the ETF allowlist")
    cap = float(run.config.get("parameters", {}).get("cap", .2))
    if cap > .2 or cap <= 0 or not 100 <= float(budget) <= 10000:
        raise ValueError("Paper limits: budget $100–$10,000; position cap at most 20%")
    if PaperSession.objects.filter(revoked=False).exists():
        raise ValueError("Revoke the existing session before approving another")
    if PaperOrder.objects.exclude(status__in=TERMINAL).exists():
        raise ValueError("Reconcile all earlier orders before approving a new session")
    current = provenance()
    if any(run.provenance.get(key) != current[key] for key in ("source_digest", "lock_digest")):
        raise ValueError("Evaluator changed since this run. Rerun and review before approval")
    return PaperSession.objects.create(experiment=run, approved_by=user, fingerprint=fingerprint(run), budget=budget)


def status():
    return {"endpoint": "https://paper-api.alpaca.markets", "sessions": list(PaperSession.objects.values("id", "experiment_id", "active", "revoked", "budget", "approved_at")),
            "orders": list(PaperOrder.objects.order_by("-pk").values("client_order_id", "symbol", "side", "qty", "status", "filled_qty")[:100])}


def observe(session, message):
    session.observations = (session.observations + [message])[-200:]
    session.save(update_fields=["observations"])


def reconcile(session, broker):
    uncertain = False
    for intent in PaperOrder.objects.filter(session=session).exclude(status__in=TERMINAL):
        order = broker.lookup(intent.client_order_id)
        if order is None:
            # Includes a crash between persisting intent and sending it. Do not
            # guess whether a request reached Alpaca; keep it blocked for review.
            intent.status = "unknown"
            uncertain = True
        else:
            intent.broker_id = str(order.id)
            intent.status = getattr(order.status, "value", str(order.status))
            intent.filled_qty = Decimal(str(order.filled_qty or 0))
            intent.filled_price = Decimal(str(order.filled_avg_price)) if order.filled_avg_price else None
        intent.save()
    return uncertain


def stop(session_id, revoke=False, broker=None):
    session = PaperSession.objects.get(pk=session_id)
    session.active = False
    session.revoked = session.revoked or revoke
    session.save(update_fields=["active", "revoked"])
    # Immediately disable new intents, then wait for an in-flight cycle before
    # requesting cancellation. This closes the stop/submit race.
    import fcntl
    from django.conf import settings
    settings.LAB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    lock = (settings.LAB_DATA_DIR / "paper.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX)
    from paper.broker import PaperBroker
    try:
        broker = broker or PaperBroker()
        reconcile(session, broker)
        for intent in PaperOrder.objects.filter(session=session).exclude(status__in=TERMINAL):
            if intent.broker_id:
                broker.cancel(intent.broker_id)
        observe(session, "Stopped. Cancellation requested; reconcile to confirm all orders are terminal. Positions were retained.")
    except Exception:
        observe(session, "Stopped locally. Broker cancellation could not be confirmed; review open orders in Alpaca paper dashboard.")
    finally:
        lock.close()
    return {"session": session.pk, "active": False, "revoked": session.revoked}


def tick(session_id, broker=None, prices=None):
    # Serialize all paper operations with the database transaction. A pending
    # intent is committed before submission below; a separate file lock spans it.
    import fcntl
    from django.conf import settings
    settings.LAB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with (settings.LAB_DATA_DIR / "paper.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("A paper cycle is already running") from None
        return _tick(session_id, broker, prices)


def _tick(session_id, broker, prices):
    from paper.broker import PaperBroker
    session = PaperSession.objects.select_related("experiment__dataset", "experiment__strategy").get(pk=session_id)
    if not session.active or session.revoked:
        raise ValueError("Paper session is paused or revoked")
    run = session.experiment
    if fingerprint(run) != session.fingerprint:
        raise ValueError("Approval no longer matches the immutable experiment")
    current = provenance()
    if any(run.provenance.get(key) != current[key] for key in ("source_digest", "lock_digest")):
        raise ValueError("Evaluator changed after approval; pause and review a new run")
    broker = broker or PaperBroker()
    if reconcile(session, broker):
        raise ValueError("Uncertain order submission; operator reconciliation is required")
    state = broker.state()
    if not state["open"] or state["blocked"]:
        return {"status": "waiting", "reason": "Market closed or account blocked"}
    if state["open_orders"] or PaperOrder.objects.filter(session=session).exclude(status__in=TERMINAL).exists():
        return {"status": "waiting", "reason": "Open or partially filled orders remain"}
    tickers = run.dataset.snapshot["tickers"]
    if set(state["positions"]) - set(tickers) or any(p["qty"] < 0 or p["qty"] != int(p["qty"]) for p in state["positions"].values()):
        raise ValueError("Use a dedicated paper account with only whole-share allowlisted long positions")
    if prices is None:
        from marketdata.models import PricePoint
        import pandas as pd
        rows = list(PricePoint.objects.filter(asset__ticker__in=tickers).values_list("date", "asset__ticker", "adjusted_close"))
        prices = pd.DataFrame(rows, columns=["date", "ticker", "price"]).pivot(index="date", columns="ticker", values="price").astype(float).dropna()
        prices.index = pd.to_datetime(prices.index)
    prices = prices.loc[:, tickers]
    if prices.empty or prices.index[-1].date() != state["previous_session"]:
        raise ValueError("Refresh all ETF daily bars through the previous market session")
    parameters = dict(run.config.get("parameters", {}), method=run.config["method"])
    parameters.setdefault("cap", .2)
    weights = {t: float(state["positions"].get(t, {}).get("value", 0) / session.budget) for t in tickers}
    month = str(state["date"])[:7]
    if parameters.get("rebalance", "monthly") == "monthly" and session.target_month == month:
        targets = session.targets
    elif run.strategy:
        from workers.isolation import StrategyProcess
        with StrategyProcess(run.strategy.source, run.config["seed"]) as worker:
            if worker.image_digest != run.provenance.get("worker_image"):
                raise ValueError("Worker image changed after approval")
            targets = worker.weights(prices, weights, parameters)
    else:
        from strategies.builtin import target_weights
        targets = target_weights(prices, weights, parameters)
    from backtest.engine import validate_weights
    targets = validate_weights(targets, tickers, .2)
    session.target_month, session.targets = month, targets.to_dict()
    session.save(update_fields=["target_month", "targets"])
    # Adjusted closes are unsuitable order prices; request unadjusted IEX closes.
    if hasattr(broker, "raw_closes"):
        raw = broker.raw_closes(tickers, state["previous_session"])
    else:
        from marketdata.alpaca_client import get_client, fetch_daily_bars
        from alpaca.data.enums import Adjustment
        raw = {}
        for ticker in tickers:
            bars = fetch_daily_bars(get_client(), ticker, state["previous_session"], state["previous_session"], adjustment=Adjustment.RAW)
            if not bars:
                raise ValueError("Unadjusted daily bar missing; cannot size paper order")
            raw[ticker] = Decimal(str(bars[-1].close))
    instructions = []
    for ticker in tickers:
        price = Decimal(str(raw[ticker])).quantize(Decimal(".01"), rounding=ROUND_DOWN)
        if price <= 0:
            raise ValueError("Invalid unadjusted reference price")
        desired = int(Decimal(str(targets[ticker])) * session.budget / price)
        owned = int(state["positions"].get(ticker, {}).get("qty", 0))
        difference = desired - owned
        if difference:
            instructions.append((ticker, "buy" if difference > 0 else "sell", abs(difference), price))
    # Sell first; re-read fills/cash on a later cycle before buying.
    sells = [item for item in instructions if item[1] == "sell"]
    instructions = sells or instructions
    buy_total = sum(qty * price for _, side, qty, price in instructions if side == "buy")
    held_value = sum(p["value"] for p in state["positions"].values())
    if buy_total > state["cash"] or buy_total + held_value > session.budget + Decimal(".01"):
        raise ValueError("Paper cash or experiment budget is insufficient")
    submitted = []
    for ticker, side, qty, price in instructions:
        session.refresh_from_db()
        if not session.active or session.revoked:
            break
        client_id = "pl-" + hashlib.sha256(f"{session.pk}:{state['date']}:{ticker}:{side}".encode()).hexdigest()[:40]
        intent, created = PaperOrder.objects.get_or_create(client_order_id=client_id, defaults={"session": session, "trading_date": state["date"], "symbol": ticker, "side": side, "qty": qty, "limit_price": price})
        if not created:
            continue
        try:
            order = broker.submit(intent)
            intent.broker_id, intent.status = str(order.id), getattr(order.status, "value", str(order.status))
            intent.filled_qty = Decimal(str(order.filled_qty or 0))
            intent.filled_price = Decimal(str(order.filled_avg_price)) if order.filled_avg_price else None
            intent.save(update_fields=["broker_id", "status", "filled_qty", "filled_price"])
            submitted.append(client_id)
        except Exception:
            intent.status, intent.error = "unknown", "Submission outcome uncertain; reconcile before continuing"
            intent.save(update_fields=["status", "error"])
            observe(session, intent.error)
            break
    observe(session, {"date": str(state["date"]), "submitted": submitted, "held_value": str(held_value), "cash": str(state["cash"])})
    return {"status": "evaluated", "submitted": submitted}
