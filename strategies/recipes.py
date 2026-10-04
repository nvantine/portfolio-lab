"""Composable forecasts, risk estimates, allocation, and explicit constraints."""
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

SIGNALS = ("none", "historical_mean", "momentum", "mean_reversion", "ridge", "views")
ALLOCATORS = ("min_variance", "mean_variance", "robust", "cvar", "max_sharpe", "tracking_error", "max_diversification", "fixed_weights")


def validate_recipe(recipe):
    if not isinstance(recipe, dict) or set(recipe) - {"signal", "allocator", "overlay", "parameters"}:
        raise ValueError("Recipe fields: signal, allocator, overlay, parameters")
    signal, allocator = recipe.get("signal", "none"), recipe.get("allocator", "min_variance")
    if signal not in SIGNALS or allocator not in ALLOCATORS or recipe.get("overlay", "none") not in {"none", "volatility_target"}:
        raise ValueError("Unknown recipe component")
    consumes = allocator in {"mean_variance", "robust", "max_sharpe"}
    if consumes == (signal == "none"):
        raise ValueError("Return-sensitive allocators need a signal; other allocators require signal=none")
    parameters = recipe.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError("Recipe parameters must be an object")
    if parameters.get("allow_short", False) and (allocator not in {"min_variance", "mean_variance", "robust", "cvar", "tracking_error", "fixed_weights"} or recipe.get("overlay", "none") != "none"):
        raise ValueError("This allocator/overlay does not support signed research")
    if allocator in {"fixed_weights", "tracking_error"} and not parameters.get("fixed_weights" if allocator == "fixed_weights" else "benchmark_weights"):
        raise ValueError("Supply explicit fixed or benchmark weights")


def forecast(prices, returns, signal, parameters):
    if signal == "none": return returns.mean() * 0
    if signal == "historical_mean": return returns.mean()
    if signal == "momentum": return (prices.iloc[-1] / prices.iloc[0]) ** (1 / len(returns)) - 1
    if signal == "mean_reversion":
        return -(prices.iloc[-1] - prices.mean()) / prices.std().replace(0, np.nan) * returns.std()
    if signal == "views":
        views = parameters.get("views", {})
        if set(views) != set(prices): raise ValueError("Explicit signal views must cover every asset")
        return pd.Series(views).reindex(prices.columns)
    result = {}
    for ticker in prices:
        series = returns[ticker].to_numpy()
        x = np.array([series[i-5:i] for i in range(5, len(series))])
        scaler = StandardScaler().fit(x)
        model = Ridge(alpha=parameters.get("ridge_alpha", 1)).fit(scaler.transform(x), series[5:])
        result[ticker] = float(model.predict(scaler.transform(series[-5:].reshape(1, -1)))[0])
    return pd.Series(result)


def target_weights(history, current_weights, parameters):
    from strategies.builtin import covariance
    from optimizer.advanced import allocation
    recipe = parameters["recipe"]
    validate_recipe(dict(recipe, parameters=parameters))
    prices = history.tail(int(parameters.get("lookback", 126)) + 1)
    returns = prices.pct_change(fill_method=None).dropna()
    if len(returns) < 10: raise ValueError("Need ten observed historical returns")
    sigma = covariance(returns, parameters.get("covariance", "ledoit_wolf"), parameters.get("ewma_decay", .94))
    allocator = recipe.get("allocator", "min_variance")
    if allocator == "fixed_weights":
        weights = parameters["fixed_weights"]
    else:
        means = forecast(prices, returns, recipe.get("signal", "none"), parameters)
        weights = allocation(sigma, means, method=allocator, current=current_weights if allocator not in {"max_sharpe", "max_diversification"} else None,
            cap=parameters.get("cap", .2), risk_aversion=parameters.get("risk_aversion", 10), scenarios=returns,
            confidence=parameters.get("confidence", .95), turnover_limit=parameters.get("turnover_limit"),
            cost_bps=parameters.get("turnover_penalty_bps", 0), robust_radius=parameters.get("robust_radius", .001) if allocator == "robust" else 0,
            allow_short=parameters.get("allow_short", False), net_exposure=parameters.get("net_exposure", 1),
            gross_limit=parameters.get("gross_limit", 1.5), short_cap=parameters.get("short_cap", .2), benchmark_weights=parameters.get("benchmark_weights"))["weights"]
    if recipe.get("overlay", "none") == "volatility_target":
        w = pd.Series(weights).reindex(sigma.columns, fill_value=0)
        risk = float(np.sqrt(w @ sigma @ w) * np.sqrt(252))
        scale = min(1, parameters.get("target_volatility", .1) / max(risk, 1e-12))
        weights = {ticker: value * scale for ticker, value in weights.items()}
    return weights
