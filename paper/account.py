"""Account-level netting and durable attribution for multiple long-only sleeves.

Only this service orchestrates new execution. External fills update virtual sleeve
shares/cash transactionally; internal crosses never generate broker orders.
"""
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
import fcntl
import hashlib
import math
from zoneinfo import ZoneInfo
import pandas as pd
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from backtest.engine import validate_weights
from backtest.schedule import period
from paper.models import AccountPolicy, AccountCycle, AccountOrder, PaperSession, PaperOrder
from research.services import digest, materialize, provenance
from paper.services import fingerprint, TERMINAL

D = Decimal
UNIT = D(".000001")


@contextmanager
def locked():
    settings.LAB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with (settings.LAB_DATA_DIR / "paper.lock").open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def broker_client(broker=None):
    if broker is not None: return broker
    from paper.broker import PaperBroker
    return PaperBroker()


def policy():
    return AccountPolicy.objects.get_or_create(pk=1)[0]


def pending():
    return AccountOrder.objects.exclude(status__in=TERMINAL).exists() or PaperOrder.objects.exclude(status__in=TERMINAL).exists()


def set_limits(budget=None, cap=None):
    with locked(), transaction.atomic():
        value = policy()
        amount, position = D(str(budget)) if budget is not None else value.budget, cap if cap is not None else value.cap
        reserved = sum(s.budget for s in PaperSession.objects.filter(revoked=False))
        if not amount.is_finite() or amount < max(reserved, D(100)) or not isinstance(position, (int, float)) or not math.isfinite(position) or not 0 < position <= 1:
            raise ValueError("Limits must cover reserved budgets; cap must be in (0, 1]")
        if any(s.experiment.config.get("parameters", {}).get("cap", .2) > position for s in PaperSession.objects.filter(revoked=False)):
            raise ValueError("Pause/close incompatible strategies before reducing the cap")
        value.budget, value.cap = amount, position
        value.save()
        return {"budget": str(amount), "cap": position}


def check_version(session):
    run = session.experiment
    materialize(run.dataset)
    if run.status != "succeeded" or fingerprint(run) != session.fingerprint:
        raise ValueError("Activation no longer matches the immutable experiment")
    current = provenance()
    if any(run.provenance.get(key) != current[key] for key in ("source_digest", "lock_digest", "versions", "python")):
        raise ValueError("Evaluator changed; rerun the experiment and activate a new version")


def activate(run_id, budget, user=None, scheduled=True, broker=None):
    from research.models import Experiment
    with locked(), transaction.atomic():
        if user is None:
            username = getattr(settings, "LAB_OPERATOR_USERNAME", "")
            query = get_user_model().objects.filter(is_staff=True, is_active=True)
            user = query.get(username=username) if username else query.first()
        if not user or not user.is_staff or not user.is_active: raise ValueError("Create an operator login before activation")
        run = Experiment.objects.select_related("dataset", "strategy").get(pk=run_id)
        if run.status != "succeeded" or run.config.get("window") != "validation" or run.trashed_at:
            raise ValueError("Activate a successful, untrashed validation experiment")
        if not run.dataset.manifest["source"].startswith("Alpaca"):
            raise ValueError("Execution requires a real Alpaca dataset")
        params = run.config.get("parameters", {})
        if params.get("allow_short"): raise ValueError("Signed research cannot execute yet")
        limits = policy()
        amount = D(str(budget))
        if not amount.is_finite() or amount < 100 or params.get("cap", .2) > limits.cap:
            raise ValueError("Budget must be at least $100 and strategy cap within account limits")
        sessions = list(PaperSession.objects.filter(revoked=False))
        if pending(): raise ValueError("Reconcile pending/unknown account orders before activation")
        reserved = sum((s.budget for s in sessions), D(0))
        client = broker_client(broker)
        if hasattr(client, "ensure_assets"):
            client.ensure_assets(run.dataset.manifest.get("assets", run.dataset.snapshot["tickers"]))
        state = client.state()
        equity = state.get("equity", state["cash"] + sum((p["value"] for p in state["positions"].values()), D(0)))
        reserved_cash = sum((s.cash for s in sessions), D(0))
        if reserved + amount > min(limits.budget, equity) or amount > state["cash"] - reserved_cash:
            raise ValueError("Account budget, equity, or unreserved cash is insufficient")
        temporary = PaperSession(experiment=run, fingerprint=fingerprint(run))
        check_version(temporary)
        session = PaperSession.objects.create(experiment=run, approved_by=user, fingerprint=temporary.fingerprint, budget=amount, cash=amount, active=True, state="active", initialized=True, scheduled=scheduled)
        return {"session": session.pk, "state": session.state, "scheduled": scheduled}


def status(broker=None):
    value = policy()
    sessions = list(PaperSession.objects.select_related("experiment").all())
    result = {"account_type": "paper", "limits": {"budget": str(value.budget), "cap": value.cap},
        "sessions": [{"id": s.pk, "run": str(s.experiment_id), "method": s.experiment.config.get("method"), "state": s.state, "scheduled": s.scheduled, "budget": str(s.budget), "cash": str(s.cash), "holdings": s.holdings, "last_cycle": s.last_cycle_at.isoformat() if s.last_cycle_at else None,
                      "next_cycle": "Next eligible exchange session after 09:35 New York; targets follow configured rebalance" if s.scheduled and s.active else "Manual / paused", "observations": s.observations[-8:]} for s in sessions],
        "orders": list(AccountOrder.objects.order_by("-pk").values("client_order_id", "symbol", "side", "qty", "status", "filled_qty", "filled_price", "error")[:100])}
    result["legacy_orders"] = list(PaperOrder.objects.order_by("-pk").values("client_order_id", "symbol", "side", "qty", "status", "filled_qty")[:100])
    try:
        state = broker_client(broker).state()
        managed = {}
        for s in sessions:
            for ticker, qty in s.holdings.items(): managed[ticker] = managed.get(ticker, D(0)) + D(qty)
        result["account"] = {"cash": str(state["cash"]), "equity": str(state.get("equity", "")), "positions": state["positions"],
                             "unmanaged": {t: str(p["qty"] - managed.get(t, D(0))) for t, p in state["positions"].items() if p["qty"] != managed.get(t, D(0))}}
        for row, s in zip(result["sessions"], sessions):
            held = sum((D(qty) * state["positions"].get(t, {}).get("value", D(0)) / state["positions"][t]["qty"] for t, qty in s.holdings.items() if t in state["positions"] and state["positions"][t]["qty"]), D(0))
            row["equity"] = str(s.cash + held)
            row["return"] = float((s.cash + held) / s.budget - 1)
    except Exception:
        result["account"] = {"message": "Account state unavailable; check local broker credentials/configuration"}
    return result


def apply_fill(intent, order):
    """Apply cumulative fills once, including cumulative average-price revisions."""
    qty = D(str(order.filled_qty or 0))
    price = D(str(order.filled_avg_price)) if order.filled_avg_price else None
    if not qty.is_finite() or qty != int(qty) or qty < intent.applied_qty or qty > intent.qty or qty and (price is None or not price.is_finite() or price <= 0):
        raise ValueError("Broker returned inconsistent fills; reconciliation required")
    notional = qty * price if price else D(0)
    qty_delta = int(qty-intent.applied_qty)
    # Proportional fills rounded to whole shares by largest remainder. This keeps
    # sleeves independently closeable with the whole-share limit-order adapter.
    remaining = {sid: D(requested)-D(intent.applied_allocations.get(sid, {}).get("qty", "0")) for sid, requested in intent.allocations.items()}
    total = sum(remaining.values())
    quotas = {sid: D(qty_delta)*amount/total if total else D(0) for sid, amount in remaining.items()}
    assigned = {sid: int(q) for sid, q in quotas.items()}
    residual = qty_delta-sum(assigned.values())
    for sid in sorted(quotas, key=lambda sid: (-(quotas[sid]-assigned[sid]), int(sid)))[:residual]: assigned[sid] += 1
    with transaction.atomic():
        rows = list(intent.allocations.items())
        for session_id, requested in rows:
            previous = intent.applied_allocations.get(session_id, {"qty": "0", "notional": "0"})
            q = D(assigned[session_id])
            allocated_qty = D(previous["qty"])+q
            allocated_notional = allocated_qty*price if price else D(0)
            money = allocated_notional-D(previous["notional"])
            sleeve = PaperSession.objects.get(pk=session_id)
            signed = 1 if intent.side == "buy" else -1
            holding = D(sleeve.holdings.get(intent.symbol, "0")) + signed*q
            if holding < -UNIT: raise ValueError("Fill would create a negative sleeve holding")
            sleeve.holdings[intent.symbol] = str(max(D(0), holding))
            sleeve.cash -= signed*money
            if sleeve.cash < -UNIT: raise ValueError("Broker fill exceeded reserved sleeve cash")
            sleeve.save(update_fields=["holdings", "cash"])
            intent.applied_allocations[session_id] = {"qty": str(allocated_qty), "notional": str(allocated_notional)}
        intent.filled_qty, intent.filled_price = qty, price
        intent.applied_qty, intent.applied_notional = qty, notional
        intent.broker_id = str(order.id)
        intent.status = getattr(order.status, "value", str(order.status))
        intent.save()
        for session_id in intent.allocations:
            sleeve = PaperSession.objects.get(pk=session_id)
            if sleeve.state == "closing" and not any(D(q) for q in sleeve.holdings.values()):
                sleeve.state, sleeve.active, sleeve.revoked = "stopped", False, True
                sleeve.save(update_fields=["state", "active", "revoked"])


def reconcile(broker):
    for intent in AccountOrder.objects.exclude(status__in=TERMINAL):
        order = broker.lookup(intent.client_order_id)
        if order is None:
            intent.status = "unknown"
            intent.save(update_fields=["status"])
        else: apply_fill(intent, order)
    # Old records are retained, and unresolved old orders block new execution.
    from paper.services import reconcile as legacy_reconcile
    for sleeve in PaperSession.objects.filter(paperorder__isnull=False).distinct(): legacy_reconcile(sleeve, broker)
    return pending()


def control(session_id, action, broker=None):
    if action in {"pause", "close", "revoke"}:
        # Disable new intents before waiting for an in-flight account lock.
        PaperSession.objects.filter(pk=session_id).update(active=False)
    with locked():
        sleeve = PaperSession.objects.select_related("experiment").get(pk=session_id)
        if action == "resume":
            if sleeve.revoked or not sleeve.initialized: raise ValueError("Legacy/stopped strategies need explicit adoption or a new activation")
            check_version(sleeve)
            sleeve.state, sleeve.active = "active", True
        elif action in {"pause", "close", "revoke"}:
            if action == "revoke" and any(D(q) for q in sleeve.holdings.values()):
                raise ValueError("Holdings remain; pause or use close-and-stop")
            sleeve.active = action == "close"
            sleeve.state = "closing" if action == "close" else "stopped" if action == "revoke" else "paused"
            if action == "close": sleeve.scheduled = True
            sleeve.revoked = action == "revoke"
            sleeve.initialized = sleeve.initialized or action == "close"
        else: raise ValueError("Unknown strategy control")
        sleeve.save()
        if action in {"pause", "close", "revoke"}:
            try:
                client = broker_client(broker)
                reconcile(client)
                # Net orders can involve several sleeves: cancel and reconcile
                # the entire affected order before any new account plan.
                for order in AccountOrder.objects.exclude(status__in=TERMINAL):
                    if str(sleeve.pk) in order.allocations and order.broker_id: client.cancel(order.broker_id)
            except Exception:
                sleeve.observations = (sleeve.observations + ["State changed locally; cancellation unconfirmed. Review account orders."])[-200:]
                sleeve.save(update_fields=["observations"])
        return {"session": sleeve.pk, "state": sleeve.state}


def adopt(session_id, symbol, qty, broker=None):
    from research.datasets import symbols
    ticker = symbols([symbol])[0]
    if not isinstance(qty, int) or qty <= 0: raise ValueError("Adopt a positive whole-share quantity")
    with locked(), transaction.atomic():
        if pending(): raise ValueError("Reconcile orders before adoption")
        sleeve = PaperSession.objects.get(pk=session_id)
        if sleeve.revoked or ticker not in sleeve.experiment.dataset.snapshot["tickers"]: raise ValueError("Symbol must belong to a current strategy")
        state = broker_client(broker).state()
        position = state["positions"].get(ticker)
        used = sum((D(s.holdings.get(ticker, "0")) for s in PaperSession.objects.all()), D(0))
        if not position or D(qty) > position["qty"]-used: raise ValueError("Not enough unmanaged shares")
        value = D(qty)*position["value"]/position["qty"]
        if not sleeve.initialized: sleeve.cash = sleeve.budget
        if value > sleeve.cash: raise ValueError("Adopted holdings exceed sleeve cash reservation")
        sleeve.cash -= value
        sleeve.holdings[ticker] = str(D(sleeve.holdings.get(ticker, "0")) + qty)
        sleeve.initialized = True
        sleeve.save()
        return {"session": sleeve.pk, "holdings": sleeve.holdings}


def history_for(sleeve, previous_session):
    from marketdata.alpaca_client import fetch_daily_bars, get_client
    from alpaca.data.enums import DataFeed
    run = sleeve.experiment
    frozen = materialize(run.dataset)
    assets = run.dataset.manifest.get("assets", list(frozen))
    import json
    cache = settings.LAB_DATA_DIR / f"history-{run.pk}-{previous_session}.json"
    if cache.exists():
        payload = json.loads(cache.read_text())
        if payload["digest"] != digest(payload["data"]): raise ValueError("Execution history cache integrity failed")
        data = payload["data"]
        return pd.DataFrame(data["prices"], columns=data["tickers"], index=pd.to_datetime(data["dates"]))
    # Re-fetch the full range so adjustment changes cannot splice incompatible
    # series into a frozen research snapshot. Freeze the actual inputs per cycle.
    rows = {}
    client = get_client()
    for ticker in assets:
        bars = fetch_daily_bars(client, ticker, frozen.index[0].date(), previous_session, feed=DataFeed(run.dataset.manifest.get("feed", "iex")))
        rows[ticker] = pd.Series({bar.timestamp.date(): float(bar.close) for bar in bars})
    frame = pd.DataFrame(rows).dropna().sort_index()
    frame.index = pd.to_datetime(frame.index)
    if frame.empty or frame.index[-1].date() != previous_session: raise ValueError("Daily bars must reach the previous exchange session")
    data = {"prices": frame.to_numpy().tolist(), "tickers": list(frame), "dates": [str(d.date()) for d in frame.index]}
    cache.write_text(json.dumps({"data": data, "digest": digest(data)}, allow_nan=False))
    return frame


def cycle(broker=None, histories=None, scheduled_only=False):
    with locked():
        client = broker_client(broker)
        if reconcile(client): return {"status": "waiting", "reason": "Pending, partial, or unknown orders remain"}
        state = client.state()
        if not state["open"] or state["blocked"] or state["open_orders"]: return {"status": "waiting", "reason": "Market closed, account blocked, or external orders present"}
        if state.get("timestamp"):
            now = datetime.fromisoformat(state["timestamp"]).astimezone(ZoneInfo("America/New_York"))
            if (now.hour, now.minute) < (9, 35): return {"status": "waiting", "reason": "Scheduled submission starts at 09:35 New York"}
        sleeves = list(PaperSession.objects.select_related("experiment__dataset", "experiment__strategy").filter(revoked=False))
        enabled = [s for s in sleeves if s.active and (s.scheduled or not scheduled_only)]
        if not enabled: return {"status": "idle"}
        if any(not s.initialized for s in enabled): raise ValueError("Legacy sessions require adoption before resuming")
        for sleeve in enabled:
            if sleeve.state != "closing": check_version(sleeve)
        if all(s.state != "closing" and s.target_month == period(state["date"], s.experiment.config["parameters"].get("rebalance", "monthly")) and s.desired_shares and all(D(s.desired_shares.get(t, "0")) == D(s.holdings.get(t, "0")) for t in set(s.desired_shares) | set(s.holdings)) for s in enabled):
            return {"status": "idle", "reason": "Targets filled; waiting for next rebalance period"}
        limits = policy()
        managed = {}
        for s in sleeves:
            for t, q in s.holdings.items(): managed[t] = managed.get(t, D(0))+D(q)
        if any(q > state["positions"].get(t, {}).get("qty", 0)+UNIT for t, q in managed.items()): raise ValueError("Account holdings disagree with sleeve ledger; resolve external changes")
        plans, raw, histories_saved = {}, {}, {}
        for sleeve in sleeves:
            if sleeve not in enabled:
                plans[str(sleeve.pk)] = dict(sleeve.holdings)
                continue
            params = dict(sleeve.experiment.config["parameters"], method=sleeve.experiment.config["method"])
            if params.get("allow_short") or params.get("cap", .2) > limits.cap: raise ValueError("Strategy violates current execution limits")
            if sleeve.state == "closing":
                plans[str(sleeve.pk)] = {t: "0" for t in sleeve.holdings}
                continue
            frame = histories[sleeve.pk] if histories is not None else history_for(sleeve, state["previous_session"])
            if frame.index[-1].date() != state["previous_session"]: raise ValueError("Refresh history through the previous exchange session")
            tickers = list(frame)
            references = client.raw_closes(tickers, state["previous_session"]) if hasattr(client, "raw_closes") else raw_prices(tickers, state["previous_session"], sleeve.experiment.dataset.manifest.get("feed", "iex"))
            raw.update({t: D(str(p)).quantize(D(".01"), rounding=ROUND_DOWN) for t, p in references.items()})
            if any(raw[t] <= 0 for t in tickers): raise ValueError("Invalid raw reference prices")
            capital = sleeve.cash + sum((D(q)*raw[t] for t, q in sleeve.holdings.items()), D(0))
            allocation_capital = min(capital, sleeve.budget)
            current = {t: float(D(sleeve.holdings.get(t, "0"))*raw[t]/capital) for t in tickers} if capital > 0 else {}
            group = period(state["date"], params.get("rebalance", "monthly"))
            if sleeve.target_month == group: targets = sleeve.targets
            else:
                strategy = sleeve.experiment.strategy
                if strategy and strategy.kind == "python":
                    from workers.isolation import StrategyProcess
                    with StrategyProcess(strategy.source, sleeve.experiment.config["seed"]) as worker:
                        if worker.image_digest != sleeve.experiment.provenance.get("worker_image"): raise ValueError("Worker version changed")
                        targets = worker.weights(frame, current, params)
                else:
                    from strategies.builtin import target_weights
                    targets = target_weights(frame, current, params)
            weights = validate_weights(targets, tickers, params.get("cap", .2))
            # Numerical allocator noise must not turn 4.999999999999999 into 4.
            desired = sleeve.desired_shares if sleeve.target_month == group and sleeve.desired_shares else {t: str(int(D(str(w))*allocation_capital/raw[t]+D("1e-10"))) for t, w in weights.items()}
            if sleeve.target_month != group and any(D(q)*raw[t] > sleeve.budget*D(str(limits.cap))+D(".01") for t, q in desired.items()): raise ValueError("Position cap exceeded")
            plans[str(sleeve.pk)] = desired
            histories_saved[str(sleeve.pk)] = {"dates": [str(d.date()) for d in frame.index], "tickers": tickers, "prices": frame.to_numpy().tolist(), "fingerprint": sleeve.fingerprint, "period": group, "weights": weights.to_dict()}
        all_tickers = sorted({t for desired in plans.values() for t in desired} | set(managed))
        missing = [t for t in all_tickers if t not in raw]
        if missing:
            raw.update({t: D(str(p)).quantize(D(".01"), rounding=ROUND_DOWN) for t, p in (client.raw_closes(missing, state["previous_session"]) if hasattr(client, "raw_closes") else raw_prices(missing, state["previous_session"])).items()})
        inputs = {"histories": histories_saved, "raw_closes": {t: str(p) for t, p in raw.items()}, "holdings": {str(s.pk): s.holdings for s in sleeves}, "cash": {str(s.pk): str(s.cash) for s in sleeves}, "account": {"positions": {t: {k: str(v) for k, v in p.items()} for t, p in state["positions"].items()}, "cash": str(state["cash"])}, "date": str(state["date"])}
        instructions = []
        with transaction.atomic():
            if any(not PaperSession.objects.get(pk=s.pk).active for s in enabled):
                return {"status": "waiting", "reason": "Strategy paused during evaluation"}
            record, created = AccountCycle.objects.get_or_create(digest=digest({"inputs": inputs, "targets": plans}), defaults={"trading_date": state["date"], "inputs": inputs, "targets": plans})
            if not created and record.transfers:
                raise ValueError("Current ledger conflicts with previously recorded internal transfers")
            for sleeve in enabled:
                if str(sleeve.pk) in histories_saved:
                    row = histories_saved[str(sleeve.pk)]
                    sleeve.target_month, sleeve.targets = row["period"], row["weights"]
                    sleeve.desired_shares = plans[str(sleeve.pk)]
                    sleeve.save(update_fields=["target_month", "targets", "desired_shares"])
            for ticker in all_tickers:
                if raw[ticker] <= 0: raise ValueError("Invalid reference price")
                buyers, sellers = [], []
                for sleeve in sleeves:
                    difference = D(plans[str(sleeve.pk)].get(ticker, "0"))-D(sleeve.holdings.get(ticker, "0"))
                    if difference > 0: buyers.append([sleeve, difference])
                    elif difference < 0: sellers.append([sleeve, -difference])
                for buyer in buyers:
                    for seller in sellers:
                        quantity = min(buyer[1], seller[1], max(D(0), buyer[0].cash/raw[ticker]))
                        quantity = quantity.quantize(D(1), rounding=ROUND_DOWN)
                        if quantity <= 0: continue
                        for sleeve, sign in ((buyer[0], 1), (seller[0], -1)):
                            sleeve.holdings[ticker] = str(D(sleeve.holdings.get(ticker, "0"))+sign*quantity)
                            sleeve.cash -= sign*quantity*raw[ticker]
                            sleeve.save(update_fields=["holdings", "cash"])
                        buyer[1] -= quantity; seller[1] -= quantity
                        record.transfers.append({"symbol": ticker, "qty": str(quantity), "price": str(raw[ticker]), "buyer": buyer[0].pk, "seller": seller[0].pk})
                buys, sells = sum((p[1] for p in buyers), D(0)), sum((p[1] for p in sellers), D(0))
                # Whole broker shares; fractional sleeve attribution is tracked.
                if buys >= 1 and sells >= 1: raise ValueError("Internal transfer lacked sleeve cash; reconcile funding")
                side, rows = ("buy", buyers) if buys > sells else ("sell", sellers)
                quantity = int(abs(buys-sells))
                if quantity: instructions.append((ticker, side, quantity, {str(s.pk): str(q) for s, q in rows if q > 0}))
            record.save(update_fields=["transfers"])
            for sleeve in enabled:
                sleeve.last_cycle_at = timezone.now()
                if sleeve.state == "closing" and not any(D(q) for q in sleeve.holdings.values()): sleeve.state, sleeve.active, sleeve.revoked = "stopped", False, True
                sleeve.observations = (sleeve.observations + [{"date": str(state["date"]), "cycle": record.pk, "equity_reference": str(sleeve.cash+sum((D(q)*raw[t] for t, q in sleeve.holdings.items()), D(0)))}])[-200:]
                sleeve.save()
        # Sells precede buys. Idempotence keys are account-wide per session date.
        instructions = [i for i in instructions if i[1] == "sell"] or instructions
        buys = sum((D(q)*raw[t] for t, side, q, _ in instructions if side == "buy"), D(0))
        if buys > state["cash"]: raise ValueError("Account cash insufficient")
        by_id = {str(s.pk): s for s in sleeves}
        for ticker, side, qty, allocations in instructions:
            total = sum(D(v) for v in allocations.values())
            if side == "buy" and any(D(qty)*raw[ticker]*D(q)/total > by_id[sid].cash+D(".01") for sid, q in allocations.items()): raise ValueError("Sleeve cash insufficient")
        submitted = []
        for ticker, side, qty, allocations in instructions:
            if any(not PaperSession.objects.get(pk=sid).active for sid in allocations): break
            key = "pl2-"+hashlib.sha256(f"{state['date']}:{ticker}:{side}".encode()).hexdigest()[:40]
            intent, created = AccountOrder.objects.get_or_create(client_order_id=key, defaults={"cycle": record, "trading_date": state["date"], "symbol": ticker, "side": side, "qty": qty, "limit_price": raw[ticker], "allocations": allocations})
            if not created: continue
            try:
                order = client.submit(intent)
                apply_fill(intent, order)
                submitted.append(key)
            except Exception:
                intent.refresh_from_db()
                intent.status, intent.error = "unknown", "Submission outcome uncertain; reconcile before continuing"
                intent.save(update_fields=["status", "error"])
                break
        return {"status": "evaluated", "cycle": record.pk, "submitted": submitted}


def raw_prices(tickers, day, feed="iex"):
    from alpaca.data.enums import Adjustment, DataFeed
    from marketdata.alpaca_client import fetch_daily_bars, get_client
    client = get_client()
    values = {}
    for ticker in tickers:
        bars = fetch_daily_bars(client, ticker, day, day, adjustment=Adjustment.RAW, feed=DataFeed(feed))
        if not bars: raise ValueError("Unadjusted reference bar missing")
        values[ticker] = D(str(bars[-1].close))
    return values
