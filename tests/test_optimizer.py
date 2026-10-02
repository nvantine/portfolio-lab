import numpy as np
import pandas as pd
import pytest
from scipy.optimize import minimize

from optimizer import (
    ledoit_wolf_covariance,
    mean_variance,
    min_variance,
    sample_covariance,
    volatility,
)


def test_optimizer_exports_are_importable():
    assert callable(min_variance)
    assert callable(sample_covariance)
    assert callable(volatility)


def test_covariance_estimators_keep_labels_and_reject_missing_returns():
    returns = pd.DataFrame(
        {"SPY": [0.01, -0.02, 0.015, 0.005], "AGG": [0.002, 0.001, -0.001, 0.003]}
    )
    sample = sample_covariance(returns)
    shrunk = ledoit_wolf_covariance(returns)
    assert list(sample.columns) == ["SPY", "AGG"]
    assert list(shrunk.index) == ["SPY", "AGG"]
    np.testing.assert_allclose(sample, returns.cov())
    assert np.linalg.eigvalsh(shrunk.to_numpy()).min() >= -1e-12
    with pytest.raises(ValueError, match="missing or non-finite"):
        sample_covariance(returns.assign(AGG=np.nan))


@pytest.fixture
def portfolio_inputs():
    tickers = ["SPY", "AGG", "GLD"]
    covariance = pd.DataFrame(
        [[0.03, 0.005, 0.002], [0.005, 0.012, 0.001], [0.002, 0.001, 0.025]],
        index=tickers,
        columns=tickers,
    )
    expected_returns = pd.Series([0.06, 0.04, 0.05], index=tickers)
    return covariance, expected_returns


@pytest.mark.parametrize("objective", ["minimum_variance", "mean_variance"])
def test_cvxpy_weights_match_scipy_slsqp(portfolio_inputs, objective):
    covariance, means = portfolio_inputs
    matrix = covariance.to_numpy()
    if objective == "minimum_variance":
        weights = min_variance(covariance)
        loss = lambda w: w @ matrix @ w
    else:
        weights = mean_variance(means, covariance, risk_aversion=2.0)
        loss = lambda w: 2.0 * (w @ matrix @ w) - means.to_numpy() @ w

    scipy_result = minimize(
        loss,
        x0=np.full(3, 1 / 3),
        method="SLSQP",
        bounds=[(0, 1)] * 3,
        constraints={"type": "eq", "fun": lambda w: w.sum() - 1},
        options={"ftol": 1e-12},
    )
    assert scipy_result.success
    actual = np.array(list(weights.values()))
    assert list(weights) == list(covariance.index)
    assert np.isclose(actual.sum(), 1, atol=1e-8)
    assert np.all(actual >= 0)
    np.testing.assert_allclose(actual, scipy_result.x, atol=1e-5)


def test_optimizer_rejects_bad_inputs(portfolio_inputs):
    covariance, means = portfolio_inputs
    with pytest.raises(ValueError, match="Risk aversion"):
        mean_variance(means, covariance, risk_aversion=-1)
    with pytest.raises(ValueError, match="same tickers"):
        mean_variance(means.drop("GLD"), covariance, risk_aversion=2)
    with pytest.raises(ValueError, match="positive semidefinite"):
        min_variance(pd.DataFrame([[1.0, 2.0], [2.0, 1.0]], index=["A", "B"], columns=["A", "B"]))
