# Methodology and limitations

## Data and reproducibility

Adjusted daily IEX ETF closes are fetched explicitly with `feed=IEX` and `adjustment=ALL`. IEX is compatible with ordinary free data entitlements but covers a single venue, not consolidated SIP volume/liquidity. Price rows are cached; each experiment uses a copied snapshot and manifest, not mutable cache rows. Common observed dates are retained, no forward fill is used, and missing symbols fail with a useful message. Alignment can discard substantial history for newer funds; the manifest records discarded rows. The universe consists of currently selected liquid funds and therefore has survivorship/selection bias.

Dataset splits: first 60% training, next 20% reusable validation, last 20% final holdout. Choose lookbacks shorter than training history. Worker notebooks get training rows only. Builtins refit on available history, including prior observations in the evaluation interval, as a walk-forward procedure. This is expanding available information with a rolling estimation window, not one permanently frozen fit.

Git revision, dirty flag, evaluator source digest, `uv.lock` digest, seed, strategy digest, dataset digest, configuration and worker image ID are recorded. Seeds do not guarantee bitwise reproducibility across operating systems or solver/library changes; use the locked environment. Final results remain auditable after prices are refreshed.

## Optimization

Daily means and daily covariance share units. Annualized displayed returns use 252 times daily mean; risk uses square root of 252 times daily standard deviation. Means are sample estimates, not verified forecasts.

- Minimum variance / mean variance / robust mean uncertainty / empirical CVaR are convex constrained programs.
- Maximum Sharpe uses a homogeneous change of variables and requires a feasible positive excess return. It intentionally rejects turnover penalties in the transformed objective.
- Position caps must satisfy `number_of_assets * cap >= 1` for fully invested methods.
- Risk parity first solves unconstrained equal-risk budgeting; projecting onto caps changes exact risk parity. HRP likewise applies a final capped-simplex projection.
- Black–Litterman uses a supplied equal-weight prior and absolute daily views with diagonal uncertainty. This prior is not ETF market capitalization.
- Momentum, price-z-score mean reversion and ridge allocate only positive scores, cap individual weights, and leave residual capital as cash. Price deviations do not establish stationarity or mean reversion.
- Volatility targeting scales equal weight down and keeps cash; it never borrows.
- EWMA uses decay 0.94; PCA retains up to three components plus residual diagonal variance. Neither specification is automatically optimal.

Frontier and dual values are **retrospective fits at evaluation end** for inspection. They do not drive earlier allocations and are not a guarantee of attainable future returns. The shadow-price panel uses an allocation without a turnover penalty; duals retain objective units and can be unstable under degeneracy.

## Backtest and risk

A signal formed after close `t` is applied at close `t+1` and earns price returns ending `t+2`. The account begins as cash; cash earns zero. Weights drift between rebalances. One-way modeled cost defaults to 10 bps on each buy and sell; turnover is gross traded notional divided by wealth. Cost is separately realized even when optimization also penalizes turnover. No commissions/spread/impact model is estimated from IEX daily bars. The closing execution assumption is a coarse simulation, not an executable quote.

Volatility, Sharpe (zero risk-free rate), Sortino (downside RMS), CAGR, maximum drawdown, empirical VaR/CVaR, tracking error versus equal weight, information ratio and annual turnover are reported. The VaR/CVaR display floors loss at zero; empirical CVaR integrates a fractional tail observation. Zero-denominator ratios are `null`. Sharpe intervals use a seeded 200-draw moving-block bootstrap with 10-session blocks. These approximate intervals neither correct multiple strategy selection nor establish out-of-sample profitability.

Every trial, including failed jobs, counts in selection history. Inspecting validation repeatedly changes its role. Holdout is available to the operator, but repeated operator inspection also consumes it. No claimed deflated Sharpe or formal multiple-testing correction is provided without a justified dependence/trial model.

## Stochastic demonstrations

Seeded correlated Gaussian log increments estimate a **physical** daily distribution on training data; fan plots show equal-weight buy-and-hold wealth. They exclude parameter uncertainty and heavy tails. A two-component Gaussian mixture describes historical regimes; it is not a transition model or trading forecast. No risk-neutral drift is substituted into return prediction.

## Paper execution

The trading client is always constructed with `paper=True` and checked against the paper base URL. Separate `.env.paper` credentials are required. An authenticated staff operator approves the exact reviewed experiment. The default $10,000 allocation budget and 20% position cap are enforced before whole-share DAY limit orders. Unadjusted daily bars are used for order price/sizing, while adjusted data is used for research. Cached data must reach the previous exchange-calendar session. Limit prices are prior closes, so fills can be scarce and the implementation is not designed for intraday execution.

Sell orders are staged first; a later cycle verifies fills and available cash before buys. Open/partial orders block fresh intents. Client IDs are deterministic per session/day/symbol/side. A durable intent precedes API submission; an uncertain response or interrupted intent is **not automatically retried**. Pause/revoke disables new intents then requests cancellation; broker confirmation must still be checked, and positions remain. Use a dedicated paper account with only allowlisted whole-share long positions. An experiment budget is a target notional cap; market movement can temporarily exceed it until a rebalance.

Alpaca paper simulation omits dividends, actual queue position, market impact and some real fill conditions. Do not equate its returns with the adjusted-close backtest.

## Primary references verified during implementation

- [Django authentication](https://docs.djangoproject.com/en/6.1/topics/auth/default/)
- [Alpaca orders and requests](https://alpaca.markets/sdks/python/api_reference/trading/orders.html), [request models](https://alpaca.markets/sdks/python/api_reference/trading/requests.html), [historical stock data](https://alpaca.markets/sdks/python/api_reference/data/stock/historical.html), [paper limitations](https://docs.alpaca.markets/docs/paper-trading)
- [CVXPY solver features](https://www.cvxpy.org/tutorial/solvers/index.html), [Clarabel settings](https://clarabel.org/stable/api_settings/)
- [scikit-learn GaussianMixture](https://scikit-learn.org/stable/modules/generated/sklearn.mixture.GaussianMixture.html), [Ridge](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html)
- [Docker rootless](https://docs.docker.com/engine/security/rootless/), [resource-limit requirements](https://docs.docker.com/engine/security/rootless/tips/), [container options](https://docs.docker.com/reference/cli/docker/container/run/)
- [nbclient](https://nbclient.readthedocs.io/en/latest/client.html), [nbformat](https://nbformat.readthedocs.io/en/latest/api.html), [Bleach cleaning](https://bleach.readthedocs.io/en/latest/clean.html)
- [KaTeX API](https://katex.org/docs/api), [Plotly embedding](https://plotly.com/python/interactive-html-export/)

Installed Alpaca SDK signatures and constructor source were also inspected before writing the adapter. Local original book notes are indexed in `~/Library/math/markdown/portfolio-lab-index.md`; only selected passages were reviewed. PDFs are not copied into the repository.
