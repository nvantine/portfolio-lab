"""The visible method catalog: every strategy has a formula and assumptions."""
METHODS = {
    "custom": (r"w=f(\text{available history},w_{current},\theta)", "Registered Python defines the strategy; inspect its source and assumptions."),
    "recipe": (r"\text{signal}\to\text{risk model}\to\text{allocator}\to\text{overlay}", "Compatible, explicitly recorded components; no automatic claim of optimality."),
    "fixed_weights": (r"w=w_{user}", "User-specified allocations; unallocated wealth remains in cash."),
    "tracking_error": (r"\min_w(w-b)^T\Sigma(w-b)", "Tracking error relative to explicit asset benchmark weights."),
    "max_diversification": (r"\max_w\frac{\sigma^Tw}{\sqrt{w^T\Sigma w}}", "Diversification ratio uses estimated marginal volatilities; long-only."),
    "equal_weight": (r"w_i=1/n", "Uniform allocation; a baseline, not a forecast."),
    "inverse_volatility": (r"w_i\propto 1/\hat\sigma_i", "Marginal volatility sizing ignores correlations."),
    "min_variance": (r"\min_w w^T\hat\Sigma w", "Historical covariance need not persist."),
    "mean_variance": (r"\max_w \hat\mu^Tw-\lambda w^T\hat\Sigma w", "Daily means are noisy estimates."),
    "max_sharpe": (r"\max_w (\hat\mu-r_f)^Tw/\sqrt{w^T\hat\Sigma w}", "Requires feasible positive expected excess return."),
    "cvar": (r"\min_{w,a}\;a+\frac{1}{(1-\alpha)T}\sum_t(-r_t^Tw-a)_+", "Empirical tail scenarios may miss future extremes."),
    "robust": (r"\max_w \hat\mu^Tw-\lambda w^T\hat\Sigma w-\rho\|w\|_2", "Spherical mean uncertainty; radius uses daily return units."),
    "risk_parity": (r"w_i(\Sigma w)_i=b_iw^T\Sigma w", "Equal risk budgets; applying a position cap changes parity."),
    "hrp": (r"d_{ij}=\sqrt{(1-\rho_{ij})/2}", "Single-linkage clustering and recursive variance allocation."),
    "black_litterman": (r"\mu=\pi+\tau\Sigma P^T(P\tau\Sigma P^T+\Omega)^{-1}(Q-P\pi)", "Explicit equal-weight prior by default; ETF fund size is not a market-cap prior."),
    "momentum": (r"s_i=P_{i,t}/P_{i,t-L}-1", "Allocate to positive trailing returns; remainder can stay in cash."),
    "mean_reversion": (r"s_i=-\frac{P_{i,t}-\bar P_i}{s(P_i)}", "A price deviation signal is not evidence of stationarity."),
    "ridge": (r"\min_\beta\|y-X\beta\|_2^2+\eta\|\beta\|_2^2", "One-step forecasts from lagged returns; fitted only to available history."),
    "volatility_target": (r"w=\min(1,\sigma_*/\hat\sigma_p)w_{base}", "Scales an equal-weight portfolio down; does not borrow."),
}
COVARIANCES = ("sample", "ledoit_wolf", "ewma", "pca")


def catalog():
    return [{"name": name, "latex": equation, "assumptions": assumptions} for name,(equation,assumptions) in METHODS.items()]
