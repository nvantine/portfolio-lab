# Portfolio Lab

A single-user Django laboratory for daily ETF allocation, reproducible quant experiments, mathematical explanations, isolated agent research and human-approved **Alpaca paper** execution.

## Start

Requires uv and Python 3.13. All Python environment and execution commands use uv.

```bash
uv sync --locked
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver 127.0.0.1:8000
```

Log in at http://127.0.0.1:8000/. Use an SSH tunnel for remote access; keep the development server on loopback. Set a private random `DJANGO_SECRET_KEY` in `.env`; never use the example placeholder. No operator password is pre-created.

In a second terminal, process the durable job queue:

```bash
uv run portfolio-lab jobs work
```

## First experiment without API keys

```bash
uv run portfolio-lab datasets demo
# Set examples/min-variance.json dataset to the returned ID if it is not 1.
uv run portfolio-lab experiments run examples/min-variance.json
uv run portfolio-lab jobs work --once
uv run portfolio-lab runs list
```

The synthetic dataset is labeled and cannot be approved for paper execution. The dashboard queues the same jobs as the CLI. Review allocations, cash, drift, growth/drawdown, equal-weight/SPY comparisons, rolling volatility, covariance, frontier, duals, metrics, bootstrap intervals and physical simulations. Formula cards render using local KaTeX; Plotly also loads locally.

## Historical Alpaca data

1. Copy `.env.example` to `.env` only if `.env` does not already exist; keep existing credentials.
2. Edit locally and set `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`. Never paste keys in chat or commit `.env`.
3. Set `DJANGO_SECRET_KEY` to a locally generated random secret and run `chmod 600 .env`.
4. Check loading without printing values:

   ```bash
   uv run python manage.py shell -c 'from django.conf import settings; print("Key loaded:", bool(settings.ALPACA_API_KEY), "Secret loaded:", bool(settings.ALPACA_SECRET_KEY))'
   ```

5. Verify historical bars:

   ```bash
   uv run python manage.py refresh_prices --check-connection
   ```

6. Refresh and freeze:

   ```bash
   uv run portfolio-lab data refresh
   uv run portfolio-lab datasets freeze SPY QQQ IWM EFA EEM AGG TLT LQD HYG GLD VNQ XLE XLK XLV XLF DBC
   ```

The editable universe is in `marketdata/universe.py`. Daily bars explicitly use IEX and adjustment ALL (splits/dividends); only common observed dates enter a snapshot, with no forward fill. IEX venue coverage differs from SIP. Paper sizing separately requests RAW historical bars, never uses adjusted prices for order limits.

## CLI

```bash
uv run portfolio-lab methods list
uv run portfolio-lab experiments sweep examples/sweep.json
uv run portfolio-lab jobs status JOB_ID
uv run portfolio-lab runs show RUN_ID
uv run portfolio-lab runs compare RUN_ID OTHER_RUN_ID
uv run portfolio-lab reports export RUN_ID --output report.md
uv run portfolio-lab strategies register examples/strategy.py --name equal-weight-example
uv run portfolio-lab notebooks run examples/covariance.ipynb --dataset DATASET_ID
uv run portfolio-lab paper status
```

Experiment configs are JSON with schema, dataset ID, method, optional strategy hash, seed, hypothesis, window and parameters. `window` defaults to validation; only an operator may request final holdout. A registered strategy defines `target_weights(history, current_weights, parameters)` and executes only in the isolated worker. All trials—including failures—remain in SQLite.

## Isolated generated code

Install rootless Docker using its official documented setup. Require rootless mode, systemd/cgroup v2 and actual CPU/memory/swap/PID limits. There is no rootful fallback.

```bash
docker info --format '{{.SecurityOptions}} {{.CgroupVersion}} {{.CgroupDriver}}'
docker build -f workers/Dockerfile -t portfolio-lab-worker:0.2 .
```

If registry/package downloads are slow and `uv sync --locked` has already populated the local cache, use `uv run python -m workers.build_image --cached`. It creates a fresh dependency-only build context using `uv pip sync --offline` and the same Docker recipe. Runtime restrictions are identical; the resulting image ID is recorded per job.

Build context explicitly excludes `.env`, database and books. Runtime containers have no network, credentials or host mounts. They run as an unprivileged user with a read-only filesystem, resource/time bounds and training/prefix data via stdin. Notebooks are executed then reviewed as escaped plain text; they are not interactive notebooks. See [Hermes setup and prompt](docs/hermes.md). Configure separate OS users on the server before scheduling an autonomous agent; no Hermes cron task is enabled here.

## Paper operator approval

See [paper credential and approval steps](docs/paper.md). Separate `.env.paper` credentials, authenticated review, immutable approval fingerprint, allowlist, no leverage, $10,000 maximum budget and 20% position cap are required. Open/partial orders and uncertain submissions block new work. Pause/revoke requests cancellation and retains positions. The endpoint is permanently paper; no live mode exists. No execution approval or trading credentials are created automatically.

## Verification

```bash
uv run pytest -q
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
```

Rootless integration tests are opt-in after building the image:

```bash
LAB_TEST_CONTAINERS=1 uv run pytest tests/test_isolation_integration.py -q
```

## Dependencies and reading guide

`pyproject.toml` is the direct dependency source; `uv.lock` is canonical. `requirements.txt` is the fully pinned portable export. After intentional dependency changes:

```bash
uv lock
uv sync --locked
uv export --no-emit-project --no-hashes --format requirements-txt --output-file requirements.txt
```

- [Architecture and file walkthrough](docs/architecture.md)
- [Project instructions for coding agents](AGENTS.md)
- [Mathematics, timing, assumptions and limitations](docs/methodology.md)
- [Hermes boundary and bounded research workflow](docs/hermes.md)
- [Paper lifecycle and stop controls](docs/paper.md)
- Local original book notes: `~/Library/math/markdown/portfolio-lab-index.md` (Boyd, Shreve I/II, ISLP, Casella–Berger; selected passages, source hashes, examples and code/test links).

`optimizer/`, `strategies/` and `backtest/` import no Django. `research/` is the shared experiment application layer; `marketdata/` caches prices; `portfolio/` renders operator pages; `workers/` isolates source; `paper/` handles approved paper orders. The original `portfolio.OptimizationRun` model is retained for migration compatibility; the expanded experiment ledger is `research.Experiment`, with related immutable snapshots and source versions. SQLite, artifacts and secrets remain local and ignored.
