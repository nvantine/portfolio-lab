from datetime import date
from types import SimpleNamespace
import json
import numpy as np
import pandas as pd
import pytest
from scipy.optimize import minimize
from backtest.engine import evaluate, validate_weights
from optimizer.advanced import allocation
from research.models import Experiment, Job, StrategyVersion
from research.services import freeze_frame, materialize, register_recipe, queue_experiment
from research.datasets import queue_fetch, accept_preview, fetch_preview
from research.commands import dispatch
from research.jobs import work


@pytest.mark.django_db
def test_saved_recipe_runs_and_is_frozen(prices, settings, tmp_path):
    settings.LAB_DATA_DIR = tmp_path
    strategy = register_recipe("Momentum optimized", {"signal": "momentum", "allocator": "mean_variance", "parameters": {"lookback": 30, "cap": .25, "cost_bps": 0, "covariance": "sample"}})
    response = queue_experiment({"dataset": freeze_frame(prices).pk, "strategy": strategy.digest, "parameters": {"rebalance": "weekly"}})
    job = work(once=True)
    assert job["status"] == "succeeded", job
    run = Experiment.objects.get(pk=response["run_id"])
    assert run.config["method"] == "recipe" and run.config["parameters"]["recipe"]["signal"] == "momentum"
    assert max(max(row.values()) for row, traded in zip(run.results["weights"], run.results["turnover"]) if traded > 0) <= .250001


def test_recipe_incompatible_components():
    from strategies.recipes import validate_recipe
    with pytest.raises(ValueError, match="signal"):
        validate_recipe({"signal": "momentum", "allocator": "min_variance"})
    with pytest.raises(ValueError, match="signed"):
        validate_recipe({"signal": "historical_mean", "allocator": "max_sharpe", "parameters": {"allow_short": True}})


def test_signed_optimizer_matches_scipy():
    sigma = pd.DataFrame(np.diag([.0001, .0004, .0002]), index=list("ABC"), columns=list("ABC"))
    means = pd.Series([.001, -.001, .0002], index=list("ABC"))
    result = allocation(sigma, means, method="mean_variance", cap=.8, allow_short=True, short_cap=.25, gross_limit=1.5, risk_aversion=2)
    w = np.array(list(result["weights"].values()))
    solved = minimize(lambda x: 2*x@sigma.to_numpy()@x-means.to_numpy()@x, np.ones(3)/3, method="SLSQP", bounds=[(-.25,.8)]*3,
                      constraints=[{"type": "eq", "fun": lambda x: x.sum()-1}, {"type": "ineq", "fun": lambda x: 1.5-np.abs(x).sum()}], options={"ftol": 1e-12, "maxiter": 500})
    assert solved.success
    np.testing.assert_allclose(w, solved.x, atol=2e-5)
    assert w.min() < 0 and abs(w.sum()-1) < 1e-6 and np.abs(w).sum() <= 1.500001


def test_signed_borrow_and_bankruptcy():
    prices = pd.DataFrame(100., index=pd.bdate_range("2024-01-01", periods=50), columns=["A", "B"])
    strategy = lambda history, current, params: {"A": 1.25, "B": -.25}
    params = {"allow_short": True, "cap": 1.3, "lookback": 10, "cost_bps": 0, "short_cap": .25, "gross_limit": 1.5, "rebalance": "weekly", "borrow_rate": .03}
    result = evaluate(prices, strategy, params, 12, 40)
    assert result["wealth"][-1] < 1
    params["borrow_rate"] = 0
    assert evaluate(prices, strategy, params, 12, 40)["wealth"][-1] == 1
    prices.iloc[14:, 1] = 10000
    with pytest.raises(ValueError, match="nonpositive"): evaluate(prices, strategy, params, 12, 40)


@pytest.mark.django_db
def test_dataset_preview_accept_and_independent_benchmark(monkeypatch, prices):
    job = queue_fetch(["AAPL", "MISSING"], "2020-01-01", "2022-01-01", "Stocks", benchmark="SPY")
    row = Job.objects.get(pk=job["job_id"])
    snapshot = {"dates": [str(d.date()) for d in prices.index], "tickers": ["AAPL", "SPY"], "prices": prices.iloc[:, :2].to_numpy().tolist()}
    row.result = {"snapshot": snapshot, "failures": {"MISSING": "No bars"}, "coverage": {}, "lost_dates": 0}
    row.status = "succeeded"; row.save()
    with pytest.raises(ValueError, match="explicitly"): accept_preview(row.pk)
    result = accept_preview(row.pk, accept_reduced=True)
    assert result["manifest"]["assets"] == ["AAPL"]
    assert result["manifest"]["benchmark"] == "SPY"
    response = queue_experiment({"dataset": result["dataset"], "method": "fixed_weights", "parameters": {"fixed_weights": {"AAPL": 1}, "cap": 1, "lookback": 30}})
    from research.services import run_experiment
    values = run_experiment(Experiment.objects.get(pk=response["run_id"]))
    assert list(values["weights"][0]) == ["AAPL"] and "SPY" in values["benchmarks"]


@pytest.mark.django_db
def test_fetch_feed_error_is_sanitized(monkeypatch):
    from alpaca.data.enums import DataFeed
    monkeypatch.setattr("marketdata.alpaca_client.get_client", lambda: object())
    seen = []
    def fetch(client, ticker, start, end, **kwargs):
        seen.append(kwargs["feed"])
        if ticker == "BAD": raise RuntimeError("SECRET must not escape")
        return [SimpleNamespace(timestamp=pd.Timestamp("2024-01-01"), close=100.)]
    monkeypatch.setattr("marketdata.alpaca_client.fetch_daily_bars", fetch)
    result = fetch_preview({"tickers": ["AAPL", "BAD"], "benchmark": "", "start": "2023-01-01", "end": "2024-01-02", "feed": "sip"})
    assert seen == [DataFeed.SIP]*2
    assert "SECRET" not in json.dumps(result)


@pytest.mark.django_db
def test_workspace_pages_and_escape(client, django_user_model):
    client.force_login(django_user_model.objects.create_user(username="reviewer", is_staff=True))
    for path in ("/datasets/", "/strategies/", "/paper/"):
        assert client.get(path).status_code == 200
    from portfolio.templatetags.presentation import pretty
    assert "<script>" not in pretty({"<script>": "<script>"})
