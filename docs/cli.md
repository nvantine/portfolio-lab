# Dashboard and CLI: the same application

The CLI grants the same application capabilities as the logged-in dashboard. There is no agent role, separate agent environment, holdout restriction, or agent-specific trial budget. Use it yourself or through any agent you authorize. Submitted Python still executes in the isolated worker.

On the same server you can run commands directly in the project, or use the owner-only Unix socket. Socket mode is 0600; access is equivalent to dashboard authority, including execution activation and account controls. Broker keys stay in the application files/environment and are never command arguments.

```bash
cd ~/Projects/portfolio-lab
uv run portfolio-lab methods list
uv run portfolio-lab datasets list
uv run portfolio-lab datasets create AAPL MSFT AMZN NVDA GOOGL --start 2020-01-01 --end 2026-10-01 --name 'US stocks' --benchmark SPY --feed iex --wait
# Read the returned job result and review coverage, then use its ID:
uv run portfolio-lab datasets accept JOB_ID --accept-reduced
uv run portfolio-lab strategies register strategy.py --name 'My allocation'
uv run portfolio-lab strategies recipe recipe.json --name 'Momentum allocation'
uv run portfolio-lab experiments run experiment.json --wait
uv run portfolio-lab jobs status JOB_ID
uv run portfolio-lab runs show RUN_ID
uv run portfolio-lab runs compare RUN_ID OTHER_RUN_ID
uv run portfolio-lab runs trash RUN_ID
uv run portfolio-lab runs list --trash
uv run portfolio-lab runs restore RUN_ID
uv run portfolio-lab reports export RUN_ID --output report.md
```

Replace identifiers with returned values. `--wait` polls the supervised worker; it does not start a worker inside the request. Normal commands produce JSON stdout and JSON error diagnostics on stderr with a nonzero exit status. Queue commands without `--wait` immediately return IDs. Process-management commands run locally even when `LAB_SOCKET` is set.

An experiment config looks like this:

```json
{
  "dataset": 1,
  "strategy": "REPLACE_WITH_REGISTERED_DIGEST",
  "seed": 42,
  "window": "validation",
  "hypothesis": "A momentum forecast improves this allocator versus equal weight",
  "parameters": {"lookback": 126, "cap": 0.2, "rebalance": "weekly", "cost_bps": 10}
}
```

For a built-in method, omit `strategy` and provide `method`. For recipes, supplied experiment parameters override saved recipe defaults and the resolved configuration is recorded. Registered Python runs are labeled `custom`, with source available for review.

A recipe file:

```json
{
  "signal": "momentum",
  "allocator": "mean_variance",
  "overlay": "volatility_target",
  "parameters": {
    "covariance": "ledoit_wolf", "lookback": 126, "risk_aversion": 10,
    "target_volatility": 0.1, "cap": 0.2, "turnover_penalty_bps": 2
  }
}
```

Custom Python contract:

```python
def target_weights(history, current_weights, parameters):
    # history is a chronologically available adjusted-price DataFrame.
    # This example leaves cash if the cap prevents full equal allocation.
    weight = min(1 / len(history.columns), parameters.get("cap", .2))
    return {symbol: weight for symbol in history.columns}
```

Registration parses code without executing it. Source, recipe, dataset, configuration, and runtime versions remain identifiable. Notebooks use `notebooks run file.ipynb --dataset ID --wait`, receive training-only `prices.csv`, and return escaped text for dashboard review. Reports and rich notebook content do not execute in the browser.

## Connected account commands

```bash
uv run portfolio-lab strategies status
uv run portfolio-lab strategies limits --budget 10000 --cap .2
uv run portfolio-lab strategies activate RUN_ID --budget 1000
uv run portfolio-lab strategies cycle
uv run portfolio-lab strategies pause SESSION_ID
uv run portfolio-lab strategies resume SESSION_ID
uv run portfolio-lab strategies close SESSION_ID
uv run portfolio-lab strategies revoke SESSION_ID
uv run portfolio-lab strategies adopt SESSION_ID AAPL 5
```

Activation enables scheduling by default; `--manual` disables it. `cycle` can submit account orders. Pause retains holdings; close requests unwinding and stops the sleeve after fills; revoke stops an empty sleeve. `paper status` and `paper tick --session ID` remain aliases: tick now runs the shared account cycle so sleeves cannot trade independently against each other. See [execution details](paper.md).

An agent can propose a hypothesis, register code, create a dataset, run configurations, compare results, and export a report. Execution activation is also available if you instruct it to activate a strategy. Keep its research process aware that repeated validation/holdout inspection introduces selection bias.
