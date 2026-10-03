"""Risk statistics for simple daily returns; undefined ratios are None."""
import numpy as np
import pandas as pd


def _returns(returns):
    values = np.asarray(returns, dtype=float)
    if values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all() or (values <= -1).any():
        raise ValueError("Supply at least two finite simple returns greater than -1")
    return values


def volatility(returns: pd.Series, periods_per_year: int = 252) -> float:
    return float(np.std(_returns(returns), ddof=1) * np.sqrt(periods_per_year))


def sharpe(returns: pd.Series, daily_risk_free_rate=0.0, periods_per_year=252):
    excess = _returns(returns) - daily_risk_free_rate
    std = np.std(excess, ddof=1)
    return float(excess.mean() / std * np.sqrt(periods_per_year)) if std > 1e-12 else None


def max_drawdown(returns: pd.Series) -> float:
    wealth = np.r_[1.0, np.cumprod(1 + _returns(returns))]
    return float(np.max(1 - wealth / np.maximum.accumulate(wealth)))


def cvar(returns: pd.Series, confidence_level=0.95) -> float:
    if not 0 < confidence_level < 1:
        raise ValueError("Confidence level must lie between zero and one")
    losses = np.sort(-_returns(returns))[::-1]
    tail = len(losses) * (1 - confidence_level)
    whole = int(np.floor(tail))
    weighted = losses[:whole].sum() + (tail - whole) * losses[min(whole, len(losses) - 1)]
    return float(max(0, weighted / tail))


def metrics(returns, benchmark=None, annual_risk_free_rate=0.0):
    values = _returns(returns)
    rf = (1 + annual_risk_free_rate) ** (1 / 252) - 1
    excess = values - rf
    downside = np.sqrt(np.mean(np.minimum(excess, 0) ** 2))
    output = {
        "total_return": float(np.prod(1 + values) - 1),
        "cagr": float(np.prod(1 + values) ** (252 / len(values)) - 1),
        "volatility": volatility(values), "sharpe": sharpe(values, rf),
        "sortino": float(excess.mean() / downside * np.sqrt(252)) if downside > 1e-12 else None,
        "max_drawdown": max_drawdown(values),
        "var_95": float(max(0, np.quantile(-values, .95))), "cvar_95": cvar(values),
    }
    if benchmark is not None:
        active = values - np.asarray(benchmark)
        te = np.std(active, ddof=1) * np.sqrt(252)
        output.update(tracking_error=float(te), information_ratio=float(active.mean()*252/te) if te > 1e-12 else None)
    return output


def bootstrap_sharpe_interval(returns, seed=42, samples=200, block_length=10):
    """Moving-block bootstrap; dependence within a block is retained."""
    values = _returns(returns)
    size = min(block_length, len(values))
    rng = np.random.default_rng(seed)
    estimates = []
    for _ in range(samples):
        starts = rng.integers(0, len(values)-size+1, size=int(np.ceil(len(values)/size)))
        draw = np.concatenate([values[i:i+size] for i in starts])[:len(values)]
        statistic = sharpe(draw)
        if statistic is not None:
            estimates.append(statistic)
    return np.quantile(estimates, [.025, .975]).tolist() if estimates else [None, None]
