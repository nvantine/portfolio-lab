"""Optimization function contracts; implementations begin in Phase 2."""

import pandas as pd


def min_variance(covariance: pd.DataFrame) -> dict[str, float]:
    """Return long-only weights minimizing variance from a daily covariance matrix."""
    raise NotImplementedError("Minimum variance optimization is planned for Phase 2")


def mean_variance(
    expected_returns: pd.Series, covariance: pd.DataFrame, risk_aversion: float
) -> dict[str, float]:
    """Return long-only weights balancing daily mean return and variance."""
    raise NotImplementedError("Mean-variance optimization is planned for Phase 2")


def max_sharpe(
    expected_returns: pd.Series, covariance: pd.DataFrame, risk_free_rate: float = 0.0
) -> dict[str, float]:
    """Return long-only weights maximizing daily excess return per unit risk."""
    raise NotImplementedError("Maximum Sharpe optimization is planned for a later phase")
