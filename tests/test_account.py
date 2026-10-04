from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace
import pandas as pd
import pytest
from paper import account
from paper.models import AccountOrder, AccountCycle, PaperSession
from research.models import Experiment
from research.services import freeze_frame, provenance


class Broker:
    def __init__(self):
        self.positions, self.orders, self.submitted = {}, {}, []
        self.day = date(2024, 6, 4)
        self.fail = False
        self.partial = False

    def state(self):
        return {"open": True, "blocked": False, "date": self.day, "previous_session": date(2024, 6, 3), "cash": D(100000), "equity": D(100000), "positions": self.positions, "open_orders": []}

    def raw_closes(self, tickers, day): return dict.fromkeys(tickers, D(100))
    def lookup(self, client_id): return self.orders.get(client_id)
    def cancel(self, order_id): self.orders[order_id].status = "canceled"

    def submit(self, intent):
        self.submitted.append(intent)
        if self.fail: raise TimeoutError()
        qty = 1 if self.partial else intent.qty
        row = SimpleNamespace(id=intent.client_order_id, status="partially_filled" if self.partial else "filled", filled_qty=qty, filled_avg_price=100)
        self.orders[intent.client_order_id] = row
        previous = self.positions.get(intent.symbol, {}).get("qty", D(0))
        shares = previous + (qty if intent.side == "buy" else -qty)
        self.positions[intent.symbol] = {"qty": D(shares), "value": D(shares)*100}
        return row


@pytest.fixture
def ready(settings, tmp_path, django_user_model):
    settings.LAB_DATA_DIR = tmp_path
    frame = pd.DataFrame(100., index=pd.bdate_range(end="2024-06-03", periods=400), columns=["AAPL", "MSFT", "SPY", "QQQ", "GLD", "AGG"])
    dataset = freeze_frame(frame)
    run = Experiment.objects.create(dataset=dataset, status="succeeded", config={"dataset": dataset.pk, "method": "equal_weight", "window": "validation", "seed": 42, "parameters": {"cap": .2, "lookback": 30}}, provenance=provenance(), results={})
    user = django_user_model.objects.create_user(username="operator", is_staff=True)
    return run, user, frame, Broker()


@pytest.mark.django_db(transaction=True)
def test_multi_sleeves_net_orders_and_repeat(ready):
    run, user, frame, broker = ready
    first = account.activate(run.pk, 3000, user=user, broker=broker)["session"]
    second = account.activate(run.pk, 3000, user=user, broker=broker)["session"]
    result = account.cycle(broker, {first: frame, second: frame})
    assert len(result["submitted"]) == 6
    assert all(intent.qty == 10 for intent in broker.submitted)
    assert all(len(intent.allocations) == 2 for intent in broker.submitted)
    assert D(PaperSession.objects.get(pk=first).holdings["AAPL"]) == 5
    account.cycle(broker, {first: frame, second: frame})
    assert len(broker.submitted) == 6


@pytest.mark.django_db(transaction=True)
def test_unknown_and_partial_are_not_resubmitted(ready):
    run, user, frame, broker = ready
    sleeve = account.activate(run.pk, 3000, user=user, broker=broker)["session"]
    broker.fail = True
    account.cycle(broker, {sleeve: frame})
    assert account.cycle(broker, {sleeve: frame})["status"] == "waiting"
    assert len(broker.submitted) == 1


@pytest.mark.django_db(transaction=True)
def test_partial_fill_applied_once(ready):
    run, user, frame, broker = ready
    sleeve = account.activate(run.pk, 3000, user=user, broker=broker)["session"]
    broker.partial = True
    account.cycle(broker, {sleeve: frame})
    before = PaperSession.objects.get(pk=sleeve).cash
    account.cycle(broker, {sleeve: frame})
    assert PaperSession.objects.get(pk=sleeve).cash == before
    assert all(order.applied_qty == 1 for order in AccountOrder.objects.all())


@pytest.mark.django_db(transaction=True)
def test_pause_and_internal_cross_preserve_other_sleeve(ready):
    run, user, frame, broker = ready
    first = account.activate(run.pk, 3000, user=user, broker=broker)["session"]
    account.cycle(broker, {first: frame})
    account.control(first, "pause", broker)
    second = account.activate(run.pk, 3000, user=user, broker=broker)["session"]
    account.control(first, "close", broker)
    broker.day = date(2024, 6, 5)
    account.cycle(broker, {second: frame})
    assert len(broker.submitted) == 6  # transfer six existing holdings internally
    assert len(AccountCycle.objects.last().transfers) == 6
    old, new = PaperSession.objects.get(pk=first), PaperSession.objects.get(pk=second)
    assert old.state == "stopped" and old.revoked
    assert D(new.holdings["AAPL"]) == 5


@pytest.mark.django_db(transaction=True)
def test_unmanaged_and_limits(ready):
    run, user, frame, broker = ready
    broker.positions["UNRELATED"] = {"qty": D(3), "value": D(300)}
    sleeve = account.activate(run.pk, 3000, user=user, broker=broker)["session"]
    account.cycle(broker, {sleeve: frame})
    assert broker.positions["UNRELATED"]["qty"] == 3
    with pytest.raises(ValueError, match="budget"):
        account.activate(run.pk, 8000, user=user, broker=broker)
    with pytest.raises(ValueError, match="cover"):
        account.set_limits(1000, .2)


@pytest.mark.django_db(transaction=True)
def test_signed_cannot_activate_and_changed_version(ready):
    run, user, frame, broker = ready
    run.config["parameters"]["allow_short"] = True
    run.save()
    with pytest.raises(ValueError, match="Signed"):
        account.activate(run.pk, 3000, user=user, broker=broker)
