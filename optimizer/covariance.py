"""Daily return covariance estimator contracts."""

import pandas as pd


def sample_covariance(returns: pd.DataFrame) -> pd.DataFrame:
    """Estimate sample covariance from daily returns, retaining ticker labels."""
    raise NotImplementedError("Sample covariance is planned for Phase 2")


def ledoit_wolf_covariance(returns: pd.DataFrame) -> pd.DataFrame:
    """Estimate shrunk daily covariance from returns, retaining ticker labels."""
    raise NotImplementedError("Ledoit-Wolf covariance is planned for Phase 2")
