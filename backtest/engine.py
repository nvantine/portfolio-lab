"""Signals computed after a close execute at the following close.

Daily adjusted closes approximate total returns. Costs are proportional to traded
notional (buys plus sells). Cash earns zero; there is no leverage or shorting.
"""
import numpy as np
import pandas as pd

from optimizer.risk import metrics, bootstrap_sharpe_interval


def validate_weights(weights, tickers, cap=1.0):
    if not isinstance(weights, dict) or set(weights) - set(tickers):
        raise ValueError("Strategy returned unknown assets or invalid weights")
    values = pd.Series(weights, dtype=float).reindex(tickers, fill_value=0.0)
    if not np.isfinite(values).all() or (values < -1e-8).any():
        raise ValueError("Weights must be finite and nonnegative")
    if values.sum() > 1 + 1e-7 or (values > cap + 1e-7).any():
        raise ValueError("Weights exceed the cash or position limit")
    return values.clip(lower=0)


def evaluate(prices, strategy, parameters, start, end, seed=42):
    if prices.empty or not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError("Prices must be positive, finite, and aligned")
    if not prices.index.is_monotonic_increasing or prices.index.has_duplicates:
        raise ValueError("Dates must be unique and ordered")
    lookback = int(parameters.get("lookback", 126))
    if not lookback + 1 <= start < end <= len(prices):
        raise ValueError("Evaluation window needs sufficient training history")
    costs = float(parameters.get("cost_bps", 10)) / 10000
    if not 0 <= costs <= .1:
        raise ValueError("Trading costs must be between 0 and 1000 bps")
    cap = float(parameters.get("cap", .2))
    rebalance = parameters.get("rebalance", "monthly")
    if rebalance not in ("daily", "monthly"):
        raise ValueError("Rebalance must be daily or monthly")
    weights = pd.Series(0.0, index=prices.columns)
    pending = None
    previous_month = None
    daily, dates, turnover, allocations = [], [], [], []
    # Start with cash. An initial signal is formed before the evaluation window.
    pending = validate_weights(strategy(prices.iloc[:start].copy(), weights.to_dict(), parameters), prices.columns, cap)
    for i in range(start, end):
        asset_return = prices.iloc[i] / prices.iloc[i - 1] - 1
        gross = float(weights @ asset_return)
        weights = weights * (1 + asset_return) / (1 + gross)
        traded = 0.0
        if pending is not None:
            traded = float((pending - weights).abs().sum())
            fee = traded * costs
            # Targets are fractions of post-cost wealth; solve the cost equation.
            # At daily ETF costs this fixed-point converges rapidly.
            for _ in range(20):
                fee = float(((1 - fee) * pending - weights).abs().sum()) * costs
            traded = float(((1 - fee) * pending - weights).abs().sum())
            gross = (1 + gross) * (1 - fee) - 1
            weights = pending.copy()
            pending = None
        day = prices.index[i]
        daily.append(gross)
        dates.append(str(day.date()))
        turnover.append(traded)
        allocations.append(weights.to_dict())
        month = (day.year, day.month)
        if rebalance == "daily" or month != previous_month:
            pending = validate_weights(strategy(prices.iloc[:i + 1].copy(), weights.to_dict(), parameters), prices.columns, cap)
        previous_month = month
    returns = np.asarray(daily)
    wealth = np.concatenate(([1.0], np.cumprod(1 + returns)))
    drawdown = wealth / np.maximum.accumulate(wealth) - 1
    summary = metrics(returns)
    summary["annual_turnover"] = float(np.mean(turnover) * 252)
    summary["sharpe_interval"] = bootstrap_sharpe_interval(returns, seed=seed)
    return {"dates": dates, "returns": daily, "wealth": wealth[1:].tolist(),
            "drawdown": drawdown[1:].tolist(), "turnover": turnover,
            "weights": allocations, "metrics": summary,
            "timing": "Close signal executes next close; earns returns from subsequent close."}
