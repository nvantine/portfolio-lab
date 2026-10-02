"""Covariance estimators for aligned daily return observations."""

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf


def _validate_returns(returns: pd.DataFrame) -> np.ndarray:
    if not isinstance(returns, pd.DataFrame) or returns.empty or len(returns) < 2:
        raise ValueError("Returns must contain at least two days and one ETF")
    if not returns.columns.is_unique:
        raise ValueError("ETF ticker columns must be unique")
    values = returns.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Returns contain missing or non-finite values; align price dates first")
    return values


def sample_covariance(returns: pd.DataFrame) -> pd.DataFrame:
    """Estimate sample covariance from daily returns, retaining ticker labels."""
    _validate_returns(returns)
    return returns.cov()


def ledoit_wolf_covariance(returns: pd.DataFrame) -> pd.DataFrame:
    """Estimate shrunk daily covariance from returns, retaining ticker labels."""
    values = _validate_returns(returns)
    estimate = LedoitWolf().fit(values).covariance_
    return pd.DataFrame(estimate, index=returns.columns, columns=returns.columns)
