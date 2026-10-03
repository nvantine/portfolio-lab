"""Seeded physical-measure demonstrations, not derivative prices or forecasts."""
import numpy as np
from sklearn.mixture import GaussianMixture


def simulate(prices, seed=42, paths=200, days=252):
    returns = prices.pct_change(fill_method=None).dropna()
    log_returns = np.log1p(returns.to_numpy())
    rng = np.random.default_rng(seed)
    draws = rng.multivariate_normal(log_returns.mean(axis=0), np.atleast_2d(np.cov(log_returns, rowvar=False)), size=(paths,days))
    wealth = np.exp(draws.cumsum(axis=1))
    portfolio = wealth.mean(axis=2)
    terminal = portfolio[:,-1]
    regimes = GaussianMixture(n_components=2, random_state=seed, reg_covar=1e-6).fit(returns.to_numpy())
    return {"measure": "physical empirical log-return model", "assumption": "IID Gaussian log returns; regime mixture is descriptive, not a prediction",
            "days": days, "paths": paths, "seed": seed, "terminal_quantiles": np.quantile(terminal,[.05,.5,.95]).tolist(),
            "fan": dict(zip(["5%", "50%", "95%"], np.quantile(portfolio,[.05,.5,.95],axis=0).tolist())),
            "regime_probabilities": regimes.predict_proba(returns.to_numpy()).tolist()}
