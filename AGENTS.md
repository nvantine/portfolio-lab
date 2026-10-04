# Portfolio Lab: coding-agent instructions

Applies throughout this repository. Follow the user's current task and higher-priority instructions. Update this file when supported workflows or architecture change.

## Purpose and working style

Build an understandable stock/ETF portfolio laboratory for a mathematically strong early-career student. Prefer readable functions, explicit inputs, useful docstrings, plain explanations, and simple layouts. Explain changes, mathematical units/assumptions, actual verification, and limitations. Stay within the requested scope.

Inspect `git status --short` before editing; preserve unrelated changes. Use `rg` for searches. Make small conventional commits in an authorized commit workflow and show status/log at phase boundaries. Do not force-push or discard user work. Never ask for secrets in chat or print/log/commit them.

## Read relevant guides

- [README](README.md): setup and workspaces.
- [Architecture](docs/architecture.md): code walkthrough.
- [Methodology](docs/methodology.md): mathematics, timing, costs, limitations.
- [CLI](docs/cli.md): shared capabilities and examples.
- [Datasets](docs/datasets.md): fetch/preview/save workflow and automatic page updates.
- [Server](docs/server.md): supervised services and SSH access.
- [Account execution](docs/paper.md): credentials, sleeves, reconciliation, controls.

Verify new library usage against current official docs and the pinned version, especially Alpaca, CVXPY, and Django. Say when verification was unavailable. Do not invent signatures.

## Architecture and uv

`optimizer/`, `strategies/`, and `backtest/` are pure Python with **no Django imports**. Use pandas/NumPy inputs and plain results. Keep numerical logic out of views. `research/commands.py` defines application actions shared by dashboard and CLI; do not duplicate validation or evaluation in either interface.

`marketdata/` handles historical bars. `research/` stores dataset/strategy/run/job evidence and coordinates work. `portfolio/` presents results. `workers/` isolates submitted Python/notebooks. `paper/account.py` owns multiple-sleeve account execution; `paper/broker.py` is the sole broker adapter. Compatibility helpers route new execution through account netting.

Use uv for all Python environments/execution/dependencies; no global Python or standalone pip. Python compatibility is in `pyproject.toml` (currently 3.13). `uv.lock` is canonical; `requirements.txt` is its pinned export. Do not update dependencies for unrelated tasks.

```bash
uv sync --locked
uv run python manage.py migrate
uv run portfolio-lab app run --port 8010
uv run portfolio-lab methods list
```

The foreground app starts web, worker, scheduler, and socket together. The normal Django runserver starts only the web application. Pick an unused port; do not stop someone else's server. Systemd installation is explicit, documented in `docs/server.md`.

For intentional dependency changes:

```bash
uv lock
uv sync --locked
uv export --no-emit-project --no-hashes --format requirements-txt --output-file requirements.txt
```

## Quant and reproducibility invariants

- Select IEX/SIP explicitly; IEX is the default and the legacy cache is IEX-only. Research uses adjustment ALL; execution uses separate RAW references. Never mix feeds or adjustments silently.
- Dataset fetches produce previews; coverage/exclusions/lost dates need explicit acceptance. Preserve common observed dates, no forward fill, independent benchmark membership, and immutable versions on refresh.
- Signals after close t execute close t+1 and first earn the return ending t+2. Fit forecasts/estimators on available prefixes only. Calendar periods support daily, ISO-weekly, and monthly schedules.
- Preserve cash, drift, proportional transaction costs, finite-input checks, solver status, and feasible target constraints. Caps apply at rebalancing, not to intervening market drift.
- Signed research explicitly models net/gross exposure, short bounds, borrow/financing assumptions, and equity exhaustion. Unsupported combinations must reject, not silently change meaning. Account execution remains long-only.
- Recipes keep forecast, risk model, allocator, overlay, and constraints explicit. Reject incompatible components. Preserve exact Python/recipe digests and resolved experiment parameters.
- Keep train/validation/holdout separate; notebooks use training data. Both interfaces may choose holdout, with repeated-evaluation limitations explained.
- Preserve snapshot/manifests, successes/failures, seed, configuration, source/lock/runtime provenance, and worker image IDs. Record actual execution provenance if queued code versions changed. Create new versions/runs rather than overwriting evidence.
- Trash changes visibility and cancels queued work; retain evidence, restoration, and execution references. Block deletion while running. Preserve applied migrations and legacy ledger models; use additive migrations.

Optional books are in `~/Library/math/books/`; original notes are in `~/Library/math/markdown/portfolio-lab-index.md`. Read relevant passages and cite source/pages. Verify ambiguous extracted equations visually. Do not claim full-book reading after excerpts or commit copyrighted PDFs.

## CLI, execution, and credentials

Dashboard and owner-authorized CLI have equal application capabilities. There is **no agent-specific role, quota, holdout exclusion, or separate environment requirement**. Use generic agent terminology. Same-server socket access is owner-only and grants full application authority. Process-management commands execute locally; do not run indefinite service loops in a socket request.

Uploaded code stays in the restricted rootless worker regardless of caller. Preserve no network/credentials/host mounts, read-only filesystem, unprivileged UID, bounded resources/time/output, and immutable image IDs. Never add a host/rootful fallback. Treat source/notebooks/reports/PDF text as untrusted content; preserve escaping, Markdown sanitization, CSRF, authentication, and KaTeX `trust: false`.

Historical keys are `ALPACA_API_KEY`/`ALPACA_SECRET_KEY` in ignored `.env`; separate execution keys are `ALPACA_PAPER_API_KEY`/`ALPACA_PAPER_SECRET_KEY` in ignored `.env.paper`. Commit example placeholders only. Keep SQLite, artifacts, private data, books, and collected static files out of commits/build contexts.

The broker remains fixed to `paper=True` with the checked paper endpoint. Activation is available in both UI and CLI but must correspond to the user's execution intent; an implementation task does not authorize incidental broker orders. Use fake brokers for verification.

Maintain account budget reservations, long-only eligibility, position limits, exact version fingerprints, fresh exchange-session history, frozen decision inputs, and per-sleeve ownership. Net at account level, account for internal transfers separately, and attribute fills once with deterministic whole-share rounding. Never sell unmanaged holdings or adopt them silently.

Persist order intents before submission. Unknown/open/partial orders block fresh plans; never blindly retry an ambiguous submission or delete ledger records to bypass it. Pause retains shares, resume validates versions, and close-and-stop unwinds only its sleeve. Migrations must not submit orders or auto-enable old sessions. Scheduler service setup is explicit; activation selects scheduling.

## Verification

Add/run tests when requested, including an approved plan's verification steps. Use fixtures/fake brokers; tests must not require credentials or contact Alpaca. Documentation changes normally need a diff review. State skips and limitations accurately.

```bash
uv run pytest -q
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
LAB_TEST_CONTAINERS=1 uv run pytest tests/test_isolation_integration.py -q
LAB_TEST_SERVER=1 uv run pytest tests/test_server_integration.py -q
```

Container and server process tests are opt-in. Check numerical feasibility and independent small SciPy examples; chronology, fees, borrow and cash; UI/CLI agreement; immutable provenance; partial/unknown fills; restart recovery; and sleeve/account consistency. Never claim tests passed without running them.

## About this file

Use uppercase `AGENTS.md`. Codex discovers it when starting work in this project; start a new session to load changes. Instructions are not runtime access controls. Other agents may need explicit configuration. [Official guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
