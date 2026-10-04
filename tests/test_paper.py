from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from paper.broker import PaperBroker
from paper.models import PaperSession, AccountOrder as PaperOrder, AccountCycle as PaperDecision
from paper.services import approve, fingerprint, stop, tick
from research.models import Experiment
from research.services import freeze_frame, provenance


class FakeBroker:
    def __init__(self):
        self.orders = {}
        self.submitted = []
        self.positions = {}
        self.fail = False
        self.partial = False
        self.day = date(2024, 6, 4)

    def state(self):
        return {"open": True, "blocked": False, "date": self.day, "previous_session": date(2024, 6, 3),
                "cash": Decimal("100000"), "positions": self.positions, "open_orders": []}

    def raw_closes(self, tickers, day):
        return dict.fromkeys(tickers, Decimal("100"))

    def lookup(self, client_id):
        return self.orders.get(client_id)

    def submit(self, intent):
        self.submitted.append(intent.client_order_id)
        if self.fail:
            raise TimeoutError("outcome unknown")
        fill = 1 if self.partial else intent.qty
        order = SimpleNamespace(id=intent.client_order_id, status="partially_filled" if self.partial else "filled", filled_qty=fill, filled_avg_price=100)
        self.orders[intent.client_order_id] = order
        qty = self.positions.get(intent.symbol, {}).get("qty", 0)
        qty += fill if intent.side == "buy" else -fill
        self.positions[intent.symbol] = {"qty": Decimal(qty), "value": Decimal(qty) * 100}
        return order

    def cancel(self, order_id):
        self.orders[order_id].status = "canceled"


@pytest.fixture
def setup_paper(settings, tmp_path, django_user_model, monkeypatch):
    settings.LAB_DATA_DIR = tmp_path
    tickers = ["SPY", "QQQ", "AGG", "GLD", "TLT", "EFA"]
    frame = pd.DataFrame(100.0, index=pd.bdate_range(end="2024-06-03", periods=400), columns=tickers)
    dataset = freeze_frame(frame)
    run = Experiment.objects.create(dataset=dataset, status="succeeded", config={"dataset": dataset.pk, "method": "equal_weight", "window": "validation", "seed": 42, "parameters": {"cap": .2, "lookback": 30}}, provenance=provenance(), results={"metrics": {}})
    user = django_user_model.objects.create_user(username="operator", is_staff=True)
    monkeypatch.setattr("paper.account.broker_client", lambda broker=None: broker if broker is not None else FakeBroker())
    return run, user, frame


def test_adapter_hardcodes_paper(monkeypatch, settings, tmp_path):
    settings.BASE_DIR = tmp_path
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "placeholder")
    monkeypatch.setenv("ALPACA_PAPER_SECRET_KEY", "placeholder")
    calls = []
    from alpaca.common.enums import BaseURL
    def factory(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(_base_url=BaseURL.TRADING_PAPER)
    monkeypatch.setattr("paper.broker.TradingClient", factory)
    PaperBroker()
    assert calls[0]["paper"] is True
    assert "url_override" not in calls[0]


@pytest.mark.django_db(transaction=True)
def test_approval_idempotence_and_revocation(setup_paper):
    run, user, frame = setup_paper
    session = approve(run.pk, user)
    broker = FakeBroker()
    first = tick(session.pk, broker, frame)
    assert len(first["submitted"]) == 6
    tick(session.pk, broker, frame)
    assert len(broker.submitted) == 6
    assert all(order.qty == 16 for order in PaperOrder.objects.all())
    assert PaperDecision.objects.count() == 1
    assert len(PaperDecision.objects.first().inputs["histories"][str(session.pk)]["prices"]) == 400
    assert all(order.cycle_id for order in PaperOrder.objects.all())
    stop(session.pk, broker=broker)
    with pytest.raises(ValueError, match="paused or revoked"):
        tick(session.pk, broker, frame)


@pytest.mark.django_db(transaction=True)
def test_unknown_outcome_never_retried(setup_paper):
    run, user, frame = setup_paper
    session = approve(run.pk, user)
    broker = FakeBroker()
    broker.fail = True
    tick(session.pk, broker, frame)
    assert len(broker.submitted) == 1
    assert tick(session.pk, broker, frame)["status"] == "waiting"
    assert len(broker.submitted) == 1


@pytest.mark.django_db(transaction=True)
def test_stale_data_approval_mutation_and_limits(setup_paper):
    run, user, frame = setup_paper
    with pytest.raises(ValueError, match="budget"):
        approve(run.pk, user, budget=20000)
    session = approve(run.pk, user)
    with pytest.raises(ValueError, match="previous"):
        tick(session.pk, FakeBroker(), frame.iloc[:-1])
    run.config["parameters"]["cap"] = .3
    run.save()
    with pytest.raises(ValueError, match="Activation"):
        tick(session.pk, FakeBroker(), frame)


@pytest.mark.django_db(transaction=True)
def test_partial_fills_block_new_intents(setup_paper):
    run, user, frame = setup_paper
    session = approve(run.pk, user)
    broker = FakeBroker()
    broker.partial = True
    tick(session.pk, broker, frame)
    broker.day = date(2024, 6, 5)
    result = tick(session.pk, broker, frame)
    assert result["status"] == "waiting"
    assert len(broker.submitted) == 6


@pytest.mark.django_db
def test_web_approval_requires_authentication_and_post(client):
    assert client.post("/paper/approve/1/").status_code == 302
    assert PaperSession.objects.count() == 0
