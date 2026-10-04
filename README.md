# Portfolio Lab

A single-owner Django workspace for stock/ETF portfolio research, reproducible experiments, mathematical explanations, and multiple strategies on an Alpaca paper account. The dashboard and CLI share the same capabilities; any authorized agent can use the CLI.

## Start locally

```bash
uv sync --locked
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run portfolio-lab app run --port 8010
```

Before starting, create `.env` from `.env.example` in your editor and set a private `DJANGO_SECRET_KEY`. Historical Alpaca keys are optional for synthetic demonstrations; account execution uses separate `.env.paper` credentials. Never paste keys into chat. The foreground command starts the dashboard, queue worker, scheduler, and owner-only socket together. Open http://127.0.0.1:8010. Use Ctrl+C to stop the stack. For supervised server operation and SSH access, follow [server setup](docs/server.md).

The usual Django `runserver` starts only the website; automatic processing needs the worker service. No account execution is enabled until you explicitly activate a strategy.

## Workspaces

- **Research:** configure a method or saved strategy, daily/weekly/monthly rebalancing, risk/cost assumptions, validation or holdout, and a hypothesis. Experiments process asynchronously. Delete moves a run to trash; restore keeps its history.
- **Datasets:** choose stock/ETF symbols, dates, explicit IEX/SIP feed, and an independent benchmark. Review coverage, missing symbols, and lost dates before accepting a frozen snapshot. Refresh creates a new version. An ETF preset and synthetic demonstration are available.
- **Strategies:** save compatible recipes or upload Python implementing `target_weights(history, current_weights, parameters)`. Review source/versions and submit training-data notebooks.
- **Results:** metrics, allocations, wealth, drawdowns, turnover, covariance, frontier, risk contributions, shadow prices, descriptive simulation, and provenance. Charts expand to full width or an overlay. Download JSON or Markdown reports.
- **Compare:** select experiments, sort metric columns, and zoom synchronized charts. Differences in dataset/window/cost/seed are flagged.
- **Active Strategies:** activate exact reviewed versions, allocate budgets, inspect attributed holdings/performance and net account orders, pause/resume, or close-and-stop. The connected account remains paper; no live mode exists.

## Strategy choices

Existing methods include equal weight, inverse volatility, minimum variance, mean variance, maximum Sharpe, CVaR, robust allocation, risk parity, HRP, Black–Litterman, momentum, mean reversion, ridge, and volatility targeting. Added choices include fixed user weights, tracking-error minimization, maximum diversification, and recipe/custom strategies.

Recipes combine a return signal, covariance estimator, allocator, optional volatility overlay, and compatible constraints. Risk models include sample, Ledoit–Wolf, configurable EWMA, and PCA approximation. Minimum variance does not consume a forecast; the builder rejects incompatible components instead of ignoring them. See [CLI examples](docs/cli.md) and [methodology](docs/methodology.md).

Signed research supports net/gross exposure constraints, short bounds, borrow costs, financing assumptions, and an equity-exhaustion failure condition. It is **backtest-only** in this release. Options and ETF constituent importing are not included.

## CLI

```bash
uv run portfolio-lab methods list
uv run portfolio-lab datasets list
uv run portfolio-lab experiments run examples/min-variance.json --wait
uv run portfolio-lab runs list
uv run portfolio-lab jobs health
```

Use returned dataset/run/job identifiers rather than assuming the examples match your database. Queue commands return IDs immediately unless `--wait` is selected. JSON results go to stdout; JSON diagnostics go to stderr. Full dashboard/CLI parity includes dataset creation, strategy registration, trash/restore, notebooks, reports, activation, and account controls. There are no agent-specific quotas or holdout exclusions.

For socket operation on the server, set `LAB_SOCKET` to the owner-only service socket described in [server setup](docs/server.md). Direct local commands remain available. Process-management commands start locally rather than through the request socket.

## Submitted code

Built-in recipes use pure Python numerical packages. Uploaded Python and notebooks execute only in a rootless container with no network, credentials, or host mounts; bounded CPU/memory/PIDs/time/output; and a read-only filesystem. Registration only parses source. Build the worker after changing numerical source or dependencies:

```bash
uv run python -m workers.build_image --cached
```

The cached builder needs uv's populated dependency cache and a functioning rootless Docker installation with cgroup v2/systemd resource enforcement. The normal builder without `--cached` downloads dependencies. Rich notebook output is discarded; reviewed source/output is escaped. Container isolation is independent of whether the caller is human or an agent.

## Execution

Multiple sleeves track their own cash and whole shares. Desired holdings are netted at account level; internal transfers use recorded raw reference prices, and external fills are attributed proportionally with deterministic whole-share rounding. Unmanaged holdings are displayed and retained unless explicitly adopted. Pausing retains holdings. Closing requests unwinding; the sleeve stops after fills.

Scheduled cycles check the exchange calendar each minute and begin submitting at 09:35 New York. Completed historical inputs are refreshed after the exchange close plus a 20-minute publication allowance. Daily/weekly/monthly targets retain share counts while orders complete. Execution uses prior unadjusted closes as DAY limit references; fills are not guaranteed and this differs from historical next-close modeling.

Default account allocation limit is $10,000 and position cap 20%; both are editable. Budgets reserve available funding. Source/dependency changes require reevaluation before activation/resume. Unknown/open/partial orders block new plans; an uncertain submission is never blindly resent. See [execution and credentials](docs/paper.md).

## Verification and dependencies

```bash
uv run pytest -q
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
LAB_TEST_CONTAINERS=1 uv run pytest tests/test_isolation_integration.py -q
```

Container checks are opt-in. Broker tests use fakes and submit no account orders. Server process checks are separately opt-in with `LAB_TEST_SERVER=1 uv run pytest tests/test_server_integration.py -q`.

Python 3.13 is specified by `pyproject.toml`; uv manages `.venv`. Direct dependencies live in that file, `uv.lock` is canonical, and `requirements.txt` is the pinned export. For intentional updates:

```bash
uv lock
uv sync --locked
uv export --no-emit-project --no-hashes --format requirements-txt --output-file requirements.txt
```

## Reading guide

- [Architecture and code walkthrough](docs/architecture.md)
- [Mathematics and limitations](docs/methodology.md)
- [Dashboard/CLI workflows](docs/cli.md)
- [Server installation](docs/server.md)
- [Active strategies and credentials](docs/paper.md)
- [Coding-agent instructions](AGENTS.md)
- Optional original book notes: `~/Library/math/markdown/portfolio-lab-index.md`.

`optimizer/`, `strategies/`, and `backtest/` have no Django imports. `research/` connects both interfaces to shared services; `marketdata/` handles bars; `portfolio/` presents results; `workers/` isolates submitted code; `paper/` manages account execution. Existing models/migrations and experiment evidence remain compatible. Databases, secrets, artifacts, and copyrighted PDFs stay outside Git.
