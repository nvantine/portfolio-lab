"""Portfolio risk metric contracts."""

import pandas as pd


def volatility(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Return annualized standard deviation of daily portfolio returns."""
    raise NotImplementedError("Volatility is planned for Phase 3")


def sharpe(
    returns: pd.Series, daily_risk_free_rate: float = 0.0, periods_per_year: int = 252
) -> float:
    """Return annualized Sharpe ratio using a daily risk-free rate."""
    raise NotImplementedError("Sharpe ratio is planned for Phase 3")


def max_drawdown(returns: pd.Series) -> float:
    """Return the largest peak-to-trough loss as a positive fraction."""
    raise NotImplementedError("Maximum drawdown is planned for Phase 3")


def cvar(returns: pd.Series, confidence_level: float = 0.95) -> float:
    """Return positive expected daily loss in the worst return tail."""
    raise NotImplementedError("CVaR is planned for Phase 3")
