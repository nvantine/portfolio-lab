"""Compatibility entry points and reconciliation for historical order records.

All new submissions route through the account netting engine. Historical models
remain readable; their unresolved intents block new execution.
"""
from decimal import Decimal
import hashlib
from paper.models import PaperSession, PaperOrder
from research.services import digest

TERMINAL = {"filled", "canceled", "expired", "rejected", "replaced"}


def fingerprint(run):
    strategy = None
    if run.strategy:
        strategy = digest({"recipe": run.strategy.recipe}) if run.strategy.kind == "recipe" else hashlib.sha256(run.strategy.source.encode()).hexdigest()
        if strategy != run.strategy.digest: raise ValueError("Strategy integrity check failed")
    return digest({"config": run.config, "dataset": run.dataset.digest, "strategy": strategy,
                   "provenance": run.provenance, "results": run.results})


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



def approve(run_id, user, budget=10000):
    from paper.account import activate
    value = activate(run_id, budget, user=user)
    return PaperSession.objects.get(pk=value["session"])


def status():
    from paper.account import status as account_status
    return account_status()


def stop(session_id, revoke=False, broker=None):
    from paper.account import control
    return control(session_id, "revoke" if revoke else "pause", broker=broker)


def tick(session_id, broker=None, prices=None):
    from paper.account import cycle
    session = PaperSession.objects.get(pk=session_id)
    if not session.active or session.revoked:
        raise ValueError("Strategy is paused or revoked")
    return cycle(broker=broker, histories={session_id: prices} if prices is not None else None)
