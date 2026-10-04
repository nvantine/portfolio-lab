# Methodology and limitations

## Data and reproducibility

Adjusted daily stock/ETF closes use an explicitly selected IEX or SIP feed and `adjustment=ALL`. IEX remains the default; SIP requires entitlement. IEX is compatible with ordinary free data entitlements but covers a single venue, not consolidated SIP volume/liquidity. Price rows are cached; each experiment uses a copied snapshot and manifest, not mutable cache rows. Common observed dates are retained, no forward fill is used, and missing symbols fail with a useful message. Alignment can discard substantial history for newer funds; the manifest records discarded rows. The universe consists of currently selected securities and therefore has survivorship/selection bias. Fetch previews display coverage and losses before snapshot acceptance; a benchmark can be stored independently of allocated assets.

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
- EWMA defaults to configurable decay 0.94; PCA retains up to three components plus residual diagonal variance. Neither specification is automatically optimal.

Frontier and dual values are **retrospective fits at evaluation end** for inspection. They do not drive earlier allocations and are not a guarantee of attainable future returns. The shadow-price panel uses an allocation without a turnover penalty; duals retain objective units and can be unstable under degeneracy.

## Backtest and risk

A signal formed after close `t` is applied at close `t+1` and earns price returns ending `t+2`. The account begins as cash; cash earns zero. Weights drift between rebalances. One-way modeled cost defaults to 10 bps on each buy and sell; turnover is gross traded notional divided by wealth. Cost is separately realized even when optimization also penalizes turnover. No commissions/spread/impact model is estimated from IEX daily bars. The closing execution assumption is a coarse simulation, not an executable quote.

Volatility, Sharpe (zero risk-free rate), Sortino (downside RMS), CAGR, maximum drawdown, empirical VaR/CVaR, tracking error versus equal weight, information ratio and annual turnover are reported. The VaR/CVaR display floors loss at zero; empirical CVaR integrates a fractional tail observation. Zero-denominator ratios are `null`. Sharpe intervals use a seeded 200-draw moving-block bootstrap with 10-session blocks. These approximate intervals neither correct multiple strategy selection nor establish out-of-sample profitability.

Every trial, including failed jobs, counts in selection history. Inspecting validation repeatedly changes its role. Holdout is available in both interfaces, but repeated inspection also consumes it. No claimed deflated Sharpe or formal multiple-testing correction is provided without a justified dependence/trial model.

## Stochastic demonstrations

Seeded correlated Gaussian log increments estimate a **physical** daily distribution on training data; fan plots show equal-weight buy-and-hold wealth. They exclude parameter uncertainty and heavy tails. A two-component Gaussian mixture describes historical regimes; it is not a transition model or trading forecast. No risk-neutral drift is substituted into return prediction.

## Composable and signed research

Recipes separate forecasts from risk estimation, allocation, and optional volatility scaling. Mean-sensitive allocators require a signal; minimum variance, CVaR, tracking error, diversification, and fixed weights require signal=none. The experiment records recipe defaults resolved with explicit overrides. Tracking error minimizes `(w-b)' Sigma (w-b)` for explicit benchmark weights. Maximum diversification maximizes `sigma' w / sqrt(w' Sigma w)` using the long-only homogeneous transformation. Fixed weights may leave cash.

Turnover penalties affect the allocator's solution before optional volatility scaling. An overlay cannot be combined with a hard turnover limit because scaling could violate the bound. Fixed weights and the homogeneous Sharpe/diversification allocators reject turnover limits and penalties.

Signed research constrains net exposure `sum(w)` (default 1), gross exposure `sum(abs(w))` (default maximum 1.5), positive cap, and short-position bound (default .2). Default short borrow rate is an editable 3% annually on short notional, accrued actual calendar days / 360. Negative cash is charged the configured financing rate (default zero) using actual days / 365; positive cash and short proceeds earn zero. These are explicit simplified assumptions, not a model of actual margin eligibility, locates, recalls, or variable borrowing rates. Nonpositive equity stops the simulation. Unsupported allocators/overlays reject signed configurations. Signed frontiers are omitted rather than mislabeled as long-only diagnostics.

Daily/weekly/monthly signals use observed calendar periods, including holiday-shortened weeks and ISO-year boundaries. Backtest signals remain delayed to the next observed close. Constraints govern targets: weights can drift beyond a cap between rebalances.

## Account execution

The trading client remains fixed to the paper endpoint. The dashboard and owner-authorized CLI can activate exact successful validation versions with editable account funding/position limits. Multiple sleeves keep separate cash and shares; desired holdings are netted, internal transfers use recorded raw reference prices, and external fills are attributed proportionally with deterministic whole-share rounding. Unmanaged holdings remain untouched unless adopted explicitly.

Scheduled submission starts at 09:35 New York on eligible exchange sessions, with completed historical inputs refreshed after close plus 20 minutes. Inputs must reach the previous exchange session. Daily/weekly/monthly target share counts stay fixed while staged orders complete. This differs from next-close backtest execution. Adjusted histories inform allocation; prior unadjusted closes size DAY limit orders. Fills can be scarce.

Sell orders precede buys. Open/partial/unknown orders block fresh work. Account-wide date/symbol/side IDs prevent duplicates, and durable intents precede submission. Uncertain submissions are never blindly retried. Pause retains holdings and requests cancellation; close-and-stop unwinds only the selected sleeve's allocation. Historical sessions migrate paused. Dividend/split attribution and real microstructure are not modeled; account discrepancies block further execution. Market movement can make a held position exceed its original target cap.

## Primary references verified during implementation

- [Django authentication](https://docs.djangoproject.com/en/6.1/topics/auth/default/)
- [Alpaca orders and requests](https://alpaca.markets/sdks/python/api_reference/trading/orders.html), [request models](https://alpaca.markets/sdks/python/api_reference/trading/requests.html), [historical stock data](https://alpaca.markets/sdks/python/api_reference/data/stock/historical.html), [paper limitations](https://docs.alpaca.markets/docs/paper-trading)
- [CVXPY solver features](https://www.cvxpy.org/tutorial/solvers/index.html), [Clarabel settings](https://clarabel.org/stable/api_settings/)
- [scikit-learn GaussianMixture](https://scikit-learn.org/stable/modules/generated/sklearn.mixture.GaussianMixture.html), [Ridge](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html)
- [Docker rootless](https://docs.docker.com/engine/security/rootless/), [resource-limit requirements](https://docs.docker.com/engine/security/rootless/tips/), [container options](https://docs.docker.com/reference/cli/docker/container/run/)
- [nbclient](https://nbclient.readthedocs.io/en/latest/client.html), [nbformat](https://nbformat.readthedocs.io/en/latest/api.html), [Bleach cleaning](https://bleach.readthedocs.io/en/latest/clean.html)
- [KaTeX API](https://katex.org/docs/api), [Plotly embedding](https://plotly.com/python/interactive-html-export/)

Installed Alpaca SDK signatures and constructor source were also inspected before writing the adapter. Local original book notes are indexed in `~/Library/math/markdown/portfolio-lab-index.md`; only selected passages were reviewed. PDFs are not copied into the repository.

Upgrade references: [Alpaca historical bars and feed/adjustment options](https://docs.alpaca.markets/us/reference/stockbars), [Alpaca asset eligibility](https://alpaca.markets/sdks/python/api_reference/trading/assets.html), [CVXPY Problem API](https://www.cvxpy.org/api_reference/cvxpy.problems.html), [Django model fields](https://docs.djangoproject.com/en/6.1/ref/models/fields/), [Plotly responsive layouts](https://plotly.com/javascript/responsive-fluid-layout/), [WhiteNoise Django setup](https://whitenoise.readthedocs.io/en/stable/django.html). Gunicorn web documentation could not be fetched during this upgrade; installed command-line help was checked for the configured options.
