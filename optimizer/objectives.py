"""Long-only portfolio optimization using daily returns and covariance."""

import cvxpy as cp
import numpy as np
import pandas as pd


def _validate_covariance(covariance: pd.DataFrame) -> tuple[list[str], np.ndarray]:
    if not isinstance(covariance, pd.DataFrame) or covariance.empty:
        raise ValueError("Covariance must be a nonempty labeled DataFrame")
    if not covariance.index.is_unique or not covariance.columns.is_unique:
        raise ValueError("Covariance ticker labels must be unique")
    if list(covariance.index) != list(covariance.columns):
        raise ValueError("Covariance rows and columns must have the same ticker order")
    values = covariance.to_numpy(dtype=float)
    if not np.isfinite(values).all() or not np.allclose(values, values.T, atol=1e-10):
        raise ValueError("Covariance must be finite and symmetric")

    eigenvalues, eigenvectors = np.linalg.eigh((values + values.T) / 2)
    if eigenvalues.min() < -1e-10:
        raise ValueError("Covariance must be positive semidefinite")
    # Remove only tiny negative eigenvalues caused by floating-point rounding.
    positive_values = eigenvectors @ np.diag(np.maximum(eigenvalues, 0)) @ eigenvectors.T
    return list(covariance.index), positive_values


def _solve(covariance: pd.DataFrame, expected_returns: pd.Series | None, risk_aversion: float) -> dict[str, float]:
    tickers, matrix = _validate_covariance(covariance)
    weights = cp.Variable(len(tickers), nonneg=True)
    variance = cp.quad_form(weights, matrix)
    if expected_returns is None:
        objective = cp.Minimize(variance)
    else:
        if not isinstance(expected_returns, pd.Series) or not expected_returns.index.is_unique:
            raise ValueError("Expected returns must be a Series with unique ticker labels")
        if set(expected_returns.index) != set(tickers):
            raise ValueError("Expected returns and covariance must have the same tickers")
        means = expected_returns.reindex(tickers).to_numpy(dtype=float)
        if not np.isfinite(means).all():
            raise ValueError("Expected returns must be finite")
        if not np.isfinite(risk_aversion) or risk_aversion < 0:
            raise ValueError("Risk aversion must be a finite nonnegative number")
        objective = cp.Maximize(means @ weights - risk_aversion * variance)

    problem = cp.Problem(objective, [cp.sum(weights) == 1])
    problem.solve()
    if problem.status != cp.OPTIMAL or weights.value is None:
        raise ValueError(f"Portfolio optimization failed: {problem.status}")

    solved = np.asarray(weights.value, dtype=float)
    if solved.min() < -1e-6 or abs(solved.sum() - 1) > 1e-6:
        raise ValueError("Solver returned weights outside the budget or long-only constraints")
    solved = np.maximum(solved, 0)
    solved /= solved.sum()
    return dict(zip(tickers, solved.tolist(), strict=True))


def min_variance(covariance: pd.DataFrame) -> dict[str, float]:
    """Return long-only weights minimizing variance from a daily covariance matrix."""
    return _solve(covariance, None, 0.0)


def mean_variance(
    expected_returns: pd.Series, covariance: pd.DataFrame, risk_aversion: float
) -> dict[str, float]:
    """Maximize daily expected return minus risk_aversion times daily variance."""
    return _solve(covariance, expected_returns, risk_aversion)


def max_sharpe(
    expected_returns: pd.Series, covariance: pd.DataFrame, risk_free_rate: float = 0.0
) -> dict[str, float]:
    """Return long-only weights maximizing daily excess return per unit risk."""
    raise NotImplementedError("Maximum Sharpe optimization is planned for a later phase")
