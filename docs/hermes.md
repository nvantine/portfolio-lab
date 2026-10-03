# Hermes research agent interface

## Keep the OS boundary real

Run the trusted Django/socket/queue services as a lab operator service user. Run Hermes as a **different OS user** with no ability to read the lab user's home, `.env`, `.env.paper`, SQLite database or Docker socket. Install a read-only copy of the CLI code/dependencies for Hermes; set `LAB_SOCKET` in its environment. The socket directory must be traversable by a shared research group; the socket is mode 0660. The service runs under that shared group so its socket inherits the right group. Do not give Hermes membership in `docker`, sudo permission, the operator's login cookie, or permission to edit trusted source.

The current workstation exercises the interface as the owner for development. That does **not** provide the separate-user boundary described here. Configure it on the server before enabling an autonomous agent. An agent with the same OS account can bypass application restrictions by reading files or invoking the trusted CLI locally.

## Start trusted processes

```bash
uv sync --locked
uv run portfolio-lab serve --socket /private-shared-runtime/portfolio-lab.sock
# separate operator terminal/service:
uv run portfolio-lab jobs work
```

For an owner-only local demonstration use `artifacts/research.sock`. For a real shared-user service use a runtime directory that the operator owns and the research group can traverse, with no write access for Hermes. Restart a service only after checking that no owner is alive; an existing socket deliberately prevents startup. No application binds a public agent endpoint.

Hermes environment:

```bash
export LAB_SOCKET=/private-shared-runtime/portfolio-lab.sock
uv run portfolio-lab methods list
uv run portfolio-lab datasets list
uv run portfolio-lab experiments run proposal.json
uv run portfolio-lab jobs status JOB_ID
uv run portfolio-lab runs show RUN_ID
uv run portfolio-lab reports export RUN_ID --output report.md
```

CLI JSON stays on stdout; errors are JSON on stderr and return a nonzero exit status. Run/sweep/notebook commands queue work and return job IDs immediately. `methods list`, strategy registration, validation experiments, notebook execution, result comparison and report export are available remotely. Market refresh, dataset creation, worker startup, final holdout access, paper execution and approvals are unavailable to the agent. `paper status` is read-only.

## Generated Python contract

```python
def target_weights(history, current_weights, parameters):
    # history: adjusted price DataFrame, ascending dates, past/current prefix only
    # current_weights: ticker-to-weight dict after market drift
    # parameters: recorded JSON, including cap and lookback
    return {ticker: min(1 / len(history.columns), parameters.get("cap", .2))
            for ticker in history.columns}
```

Register exact source with `strategies register strategy.py --name descriptive-name`. Use the returned digest as `strategy` in an experiment config. The strategy name is a label; its source hash defines the immutable version. The `method` config labels the comparison family for generated code and does not override its Python implementation. Source is parsed without execution during registration. Weight validation rejects unknown assets, nonfinite/negative weights, borrowing and cap violations.

Notebooks are submitted using `notebooks run file.ipynb --dataset ID`. Read `prices.csv` in the isolated working directory. Only training prices are supplied; earlier notebook outputs are erased. The reviewer receives escaped source and plain text outputs; rich HTML/JavaScript is discarded. Notebook runs do not register a portfolio strategy or approve execution.

The parent serial worker supplies chronological data through stdin. Rootless Docker must use cgroup v2/systemd with CPU, memory/swap and PID enforcement. Image ID is resolved before each launch. Containers have no network or mounted files, a read-only filesystem, dropped capabilities, unprivileged user, 2 CPUs, 4 GB RAM/swap bound, 128 processes, 256 MB tmpfs and a 15-minute wall-clock limit. A host lock permits one consumer. Containers are not a defense against an unpatched kernel; keep the runtime maintained.

## Bounded passive research prompt

Use this as the body of a scheduled Hermes task after server permissions are configured:

> Use Portfolio Lab through LAB_SOCKET only. Read methods, available datasets and recent trials. Select one hypothesis about daily ETF allocation. Propose no more than three configurations with fixed seed, cost assumption and validation window. You may write a Python strategy or a notebook, then register/submit it through the CLI. Do not request holdout data, credentials, broker access or operator approval. Queue the trials; poll job state on later invocations rather than launching duplicate trials. Compare completed runs to equal weight using the same dataset/window. Export a plain Markdown report with method formula, assumptions, results, failures, and selection limitations. Record IDs so the next invocation continues the same research. Stop when the daily budget is reached. Never approve or execute paper trades.

Server limits: at most 12 configurations per sweep, 24 outstanding jobs, 24 experiments per local calendar day and four notebook jobs per day. Operator trials count toward that research budget. Failed trials consume budget too. The operator handles fresh price caching and dataset freezing; Hermes cannot quietly change the evaluation data.

Scheduling itself is left to your server's Hermes installation; no cron entry or background agent has been enabled by this project. Start with one manually reviewed invocation before scheduling repeated tasks.
