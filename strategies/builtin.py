"""Readable ETF allocation and signal methods; no Django dependencies."""
import cvxpy as cp
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, leaves_list
from scipy.spatial.distance import squareform
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from optimizer import sample_covariance, ledoit_wolf_covariance
from optimizer.advanced import allocation, black_litterman
from strategies.catalog import METHODS


def covariance(returns, name="ledoit_wolf"):
    if name == "sample": return sample_covariance(returns)
    if name == "ledoit_wolf": return ledoit_wolf_covariance(returns)
    x = returns.to_numpy(dtype=float)
    if name == "ewma":
        weights = .94**np.arange(len(x)-1, -1, -1)
        matrix = np.cov(x, rowvar=False, aweights=weights, ddof=0)
    elif name == "pca":
        model = PCA(n_components=min(3, len(returns.columns), len(returns)-1)).fit(x)
        reconstructed = model.components_.T@np.diag(model.explained_variance_)@model.components_
        residual = x-model.inverse_transform(model.transform(x))
        matrix = reconstructed+np.diag(np.var(residual, axis=0, ddof=1))
    else: raise ValueError("Unknown covariance estimator")
    return pd.DataFrame(np.atleast_2d(matrix), index=returns.columns, columns=returns.columns)


def capped_weights(values, cap):
    """Euclidean projection onto a capped, fully invested simplex."""
    raw = np.asarray(values, dtype=float)
    if len(raw)*cap < 1-1e-9: raise ValueError("Infeasible position cap")
    if raw.sum() <= 0: raw = np.ones(len(raw))
    raw = raw/raw.sum()
    low, high = raw.min()-1, raw.max()
    for _ in range(80):
        middle = (low+high)/2
        if np.clip(raw-middle, 0, cap).sum() > 1: low = middle
        else: high = middle
    return np.clip(raw-high, 0, cap)


def hierarchical_weights(sigma, returns):
    if len(returns.columns) == 1: return np.ones(1)
    corr = returns.corr().fillna(0).to_numpy(copy=True)
    np.fill_diagonal(corr, 1)
    distance = np.sqrt(np.clip((1-corr)/2, 0, 1))
    tree = linkage(squareform(distance, checks=False), method="single")
    order = leaves_list(tree).tolist()
    weights = np.ones(len(order))
    clusters = [order]
    def cluster_variance(indices):
        cov = sigma[np.ix_(indices, indices)]
        inverse = 1/np.maximum(np.diag(cov), 1e-12); inverse /= inverse.sum()
        return float(inverse@cov@inverse)
    while clusters:
        next_clusters = []
        for cluster in clusters:
            if len(cluster) < 2: continue
            midpoint = len(cluster)//2
            left, right = cluster[:midpoint], cluster[midpoint:]
            lv, rv = cluster_variance(left), cluster_variance(right)
            fraction = rv/max(lv+rv, 1e-12)
            weights[left] *= fraction; weights[right] *= 1-fraction
            next_clusters.extend([left,right])
        clusters = next_clusters
    return weights


def target_weights(history, current_weights, parameters):
    method = parameters.get("method", "min_variance")
    if method not in METHODS: raise ValueError("Unknown strategy method")
    cap = parameters.get("cap", .2)
    prices = history.tail(parameters.get("lookback", 126)+1)
    returns = prices.pct_change(fill_method=None).dropna()
    if len(returns) < 10: raise ValueError("Strategy needs at least ten historical returns")
    cov = covariance(returns, parameters.get("covariance", "ledoit_wolf"))
    n = len(prices.columns)
    means = returns.mean()
    if method == "black_litterman":
        means = black_litterman(cov, dict.fromkeys(prices.columns, 1/n), parameters.get("views", {}), parameters.get("view_uncertainty", .0001), tau=parameters.get("tau", .05))
    if method in ("min_variance", "mean_variance", "max_sharpe", "cvar", "robust", "black_litterman"):
        rf = (1+parameters.get("annual_risk_free_rate", 0))**(1/252)-1
        return allocation(cov, means-rf if method == "max_sharpe" else means, method=method, cap=cap,
                          risk_aversion=parameters.get("risk_aversion", 10),
                          robust_radius=parameters.get("robust_radius", .001) if method == "robust" else 0,
                          current=current_weights if method != "max_sharpe" else None,
                          turnover_limit=parameters.get("turnover_limit"), cost_bps=parameters.get("cost_bps", 0),
                          scenarios=returns, confidence=parameters.get("confidence", .95))["weights"]
    if method in ("momentum", "mean_reversion", "ridge"):
        if method == "momentum": scores = prices.iloc[-1]/prices.iloc[0]-1
        elif method == "mean_reversion": scores = -(prices.iloc[-1]-prices.mean())/prices.std().replace(0, np.nan)
        else:
            scores = pd.Series(index=prices.columns, dtype=float)
            for ticker in prices.columns:
                series = returns[ticker].to_numpy()
                x = np.array([series[i-5:i] for i in range(5, len(series))])
                scaler = StandardScaler().fit(x)
                model = Ridge(alpha=parameters.get("ridge_alpha", 1)).fit(scaler.transform(x), series[5:])
                scores[ticker] = model.predict(scaler.transform(series[-5:].reshape(1,-1)))[0]
        positive = scores.fillna(0).clip(lower=0).to_numpy()
        weights = np.minimum(positive/positive.sum(), cap) if positive.sum() else np.zeros(n)
    elif method == "inverse_volatility": weights = capped_weights(1/np.maximum(returns.std().to_numpy(), 1e-12), cap)
    elif method == "hrp": weights = capped_weights(hierarchical_weights(cov.to_numpy(), returns), cap)
    elif method == "risk_parity":
        raw = cp.Variable(n, pos=True)
        problem = cp.Problem(cp.Minimize(.5*cp.quad_form(raw, cp.psd_wrap(cov.to_numpy()+np.eye(n)*1e-12))-cp.sum(cp.log(raw))/n))
        problem.solve()
        if problem.status != cp.OPTIMAL: raise ValueError("Risk-budget problem failed")
        weights = capped_weights(raw.value, cap)
    else:
        weights = capped_weights(np.ones(n), cap)
        if method == "volatility_target":
            risk = np.sqrt(weights@cov.to_numpy()@weights)*np.sqrt(252)
            weights *= min(1, parameters.get("target_volatility", .1)/max(risk, 1e-12))
    return dict(zip(prices.columns, weights.tolist()))
