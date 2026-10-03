import numpy as np
import pandas as pd
import pytest
from strategies.builtin import target_weights, covariance
from strategies.catalog import METHODS, COVARIANCES
from optimizer.advanced import allocation, black_litterman
from backtest.engine import validate_weights


@pytest.fixture
def history():
    rng = np.random.default_rng(42)
    return pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(.003, .01, (150, 6)), axis=0)), columns=["SPY", "QQQ", "AGG", "GLD", "TLT", "EFA"])


@pytest.mark.parametrize("method", list(METHODS))
def test_all_registered_methods(history, method):
    params = {"method": method, "cap": .25, "lookback": 100, "views": {"SPY": .001}}
    weights = target_weights(history, dict.fromkeys(history.columns, 1/6), params)
    assert validate_weights(weights, history.columns, .25).sum() <= 1 + 1e-7


@pytest.mark.parametrize("name", COVARIANCES)
def test_covariance_psd(history, name):
    value = covariance(history.pct_change().dropna(), name)
    assert np.linalg.eigvalsh(value).min() >= -1e-10


def test_duals_and_analytic_solution():
    sigma = pd.DataFrame(np.diag([1., 4.]), index=["A", "B"], columns=["A", "B"])
    fit = allocation(sigma)
    assert fit["weights"]["A"] == pytest.approx(.8, abs=1e-5)
    assert "budget" in fit["duals"]
    capped = allocation(sigma, cap=.6)
    assert capped["weights"]["A"] == pytest.approx(.6, abs=1e-5)
    assert capped["duals"]["position_cap"][0] > 0
    with pytest.raises(ValueError):
        allocation(sigma, cap=.4)


def test_black_litterman_view_moves_posterior():
    sigma = pd.DataFrame(np.eye(2) * .001, index=["A", "B"], columns=["A", "B"])
    posterior = black_litterman(sigma, {"A": .5, "B": .5}, {"A": .01}, .00001)
    assert .00125 < posterior["A"] < .01
    assert posterior["B"] == pytest.approx(.00125)
