"""Inspectable constrained allocations, frontier, and Bayesian views."""
import cvxpy as cp
import numpy as np
import pandas as pd

from optimizer.objectives import _validate_covariance


def allocation(covariance, means=None, *, method="min_variance", cap=1.0, risk_aversion=10.0,
               current=None, turnover_limit=None, cost_bps=0.0, robust_radius=0.0,
               scenarios=None, confidence=.95, target_return=None):
    tickers, sigma = _validate_covariance(covariance)
    n = len(tickers)
    if not np.isfinite(cap) or cap <= 0 or cap > 1 or n*cap < 1-1e-9:
        raise ValueError("Position cap is infeasible for this universe")
    for value in (risk_aversion, cost_bps, robust_radius):
        if not np.isfinite(value) or value < 0:
            raise ValueError("Risk, cost, and uncertainty parameters must be finite and nonnegative")
    mu = np.zeros(n) if means is None else means.reindex(tickers).to_numpy(dtype=float)
    if not np.isfinite(mu).all():
        raise ValueError("Expected returns must match covariance ticker labels")
    w = cp.Variable(n)
    constraints = {"budget": cp.sum(w) == 1, "long_only": w >= 0, "position_cap": w <= cap}
    variance = cp.quad_form(w, cp.psd_wrap(sigma))
    if method == "min_variance":
        loss = variance
    elif method in ("mean_variance", "robust", "black_litterman"):
        loss = risk_aversion*variance - mu@w + robust_radius*cp.norm(w, 2)
    elif method == "cvar":
        if scenarios is None or not 0 < confidence < 1:
            raise ValueError("CVaR needs return scenarios and a confidence level in (0, 1)")
        values = scenarios.reindex(columns=tickers).to_numpy(dtype=float)
        if not np.isfinite(values).all() or len(values) < 2:
            raise ValueError("Invalid CVaR scenarios")
        threshold = cp.Variable()
        loss = threshold + cp.sum(cp.pos(-values@w-threshold))/((1-confidence)*len(values))
    elif method == "max_sharpe":
        if mu.max() <= 0 or current is not None or turnover_limit is not None:
            raise ValueError("Maximum Sharpe requires positive excess returns and no turnover penalty")
        y, scale = cp.Variable(n), cp.Variable(nonneg=True)
        transformed = cp.Problem(cp.Minimize(cp.quad_form(y, cp.psd_wrap(sigma))),
                                 [mu@y == 1, cp.sum(y) == scale, y >= 0, y <= cap*scale])
        transformed.solve(solver="CLARABEL", tol_gap_abs=1e-10, tol_feas=1e-10, tol_gap_rel=1e-10)
        if transformed.status != cp.OPTIMAL or scale.value is None or scale.value <= 0:
            raise ValueError("Maximum Sharpe problem did not solve")
        return {"weights": dict(zip(tickers, (y.value/scale.value).tolist())), "duals": {}, "status": transformed.status}
    else:
        raise ValueError("Unknown allocation objective")
    if current is not None:
        previous = np.array([current.get(ticker, 0) for ticker in tickers])
        turnover = cp.norm1(w-previous)
        loss += cost_bps/10000*turnover
        if turnover_limit is not None:
            if not 0 <= turnover_limit <= 2:
                raise ValueError("Turnover limit must be between zero and two")
            constraints["turnover"] = turnover <= turnover_limit
    if target_return is not None:
        constraints["target_return"] = mu@w >= target_return
    problem = cp.Problem(cp.Minimize(loss), list(constraints.values()))
    problem.solve(solver="CLARABEL", tol_gap_abs=1e-10, tol_feas=1e-10, tol_gap_rel=1e-10)
    if problem.status != cp.OPTIMAL or w.value is None:
        raise ValueError(f"Allocation infeasible or solver failed: {problem.status}")
    values = np.asarray(w.value)
    if values.min() < -1e-6 or values.max() > cap+1e-6 or abs(values.sum()-1) > 1e-6:
        raise ValueError("Solver constraint violation")
    values = np.maximum(values, 0); values /= values.sum()
    return {"weights": dict(zip(tickers, values.tolist())),
            "duals": {name: np.asarray(c.dual_value).tolist() for name,c in constraints.items()},
            "status": problem.status}


def efficient_frontier(covariance, means, cap=1.0, points=15):
    base = allocation(covariance, cap=cap)["weights"]
    low = float(means@pd.Series(base))
    order = means.sort_values(ascending=False)
    remaining, high = 1.0, 0.0
    for value in order:
        amount = min(cap, remaining); high += amount*value; remaining -= amount
    result = []
    for target in np.linspace(low, high, points):
        solved = allocation(covariance, means, cap=cap, target_return=float(target))
        w = pd.Series(solved["weights"]).reindex(means.index)
        result.append({"return": float(means@w)*252, "volatility": float(np.sqrt(w@covariance@w)*np.sqrt(252)), "weights": solved["weights"]})
    return result


def black_litterman(covariance, prior_weights, views, uncertainty, tau=.05, risk_aversion=2.5):
    """Absolute views Q with diagonal uncertainty; prior weights are explicitly supplied."""
    tickers, sigma = _validate_covariance(covariance)
    if tau <= 0 or uncertainty <= 0 or not views:
        raise ValueError("Supply positive uncertainty/tau and at least one absolute view")
    prior = np.asarray([prior_weights[t] for t in tickers])
    pick = np.array([[float(t == name) for t in tickers] for name in views])
    if (pick.sum(axis=1) != 1).any():
        raise ValueError("View tickers must belong to the universe")
    base = risk_aversion*sigma@prior
    scaled = tau*sigma
    innovation = np.linalg.solve(pick@scaled@pick.T + uncertainty*np.eye(len(views)), np.array(list(views.values()))-pick@base)
    return pd.Series(base+scaled@pick.T@innovation, index=tickers)
