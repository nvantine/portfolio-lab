# Active strategies and account execution

## Credentials

Historical keys remain in ignored `.env` as `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`. Account execution uses separate credentials:

1. Copy `.env.paper.example` to `.env.paper` in your local editor.
2. Set `ALPACA_PAPER_API_KEY` and `ALPACA_PAPER_SECRET_KEY` from Alpaca's Paper Trading dashboard. Never paste them into chat.
3. Run `chmod 600 .env.paper`.
4. Confirm presence without revealing values:

   ```bash
   uv run python -c 'from dotenv import dotenv_values; v=dotenv_values(".env.paper"); print("Key present:", bool(v.get("ALPACA_PAPER_API_KEY")), "Secret present:", bool(v.get("ALPACA_PAPER_SECRET_KEY")))'
   ```

Create a staff login interactively with `uv run python manage.py createsuperuser`. CLI activation uses `LAB_OPERATOR_USERNAME` if configured, otherwise the first active staff user. Both interfaces have equal authority.

## Activate and monitor

Run a successful validation experiment on real Alpaca stock/ETF data, review it, then choose its budget in Active Strategies or use `strategies activate RUN_ID --budget 1000`. Scheduling is enabled by default; use `--manual` for manual cycles. Account settings default to a $10,000 total reserved budget and 20% position cap; increase them explicitly if appropriate for your experiments. Available account equity/cash also constrains activation. Signed strategies cannot execute in this release.

The scheduler reconciles each minute, checks the exchange calendar, and begins new submissions after 09:35 New York. Historical inputs refresh after close plus 20 minutes; a cycle must use the previous completed exchange session. Live input history is copied into each decision rather than replacing the frozen research dataset. Targets are formed from adjusted bars; raw prior-session closes size whole-share DAY limit orders. A backtest's next-close execution timing is a different assumption.

The page shows each sleeve's budget, cash, shares, marked equity/return, latest cycle, observations, and account orders. These are local strategy attribution records, not separate Alpaca accounts. Daily, weekly, and monthly targets remain fixed as share quantities during their period while staged sells/buys complete. Weights and actual market values can drift between rebalances.

## Several strategies on one account

Each sleeve owns virtual cash and whole shares. Opposing sleeve requirements transfer shares internally at the recorded reference price before the app submits account-level residual orders. No broker order or trading fee is assigned to an internal transfer. External fills use proportional allocation with deterministic largest-remainder rounding to whole shares; subsequent partial fills allocate against remaining requests. Price revisions adjust attributed cash once, without double-applying shares.

Unmanaged account positions are displayed separately and retained. `strategies adopt SESSION_ID SYMBOL QTY` or the dashboard adoption form explicitly assigns existing shares at current marked value and reduces the sleeve cash reservation. No unrelated holdings are silently sold. External sales/splits that make broker shares smaller than the ledger block execution for review. Dividend/corporate-action attribution is not implemented; resolve those events before continuing.

## Controls and recovery

- **Pause:** immediately disables new intents, waits for the account cycle, requests cancellation of affected net orders, and retains holdings.
- **Resume:** verifies the strategy/evaluator version before continuing its configured schedule.
- **Close and stop:** requests unwinding that sleeve on eligible cycles, retaining other sleeves' allocations. Completion depends on fills; market closure or unresolved orders leaves it visibly closing.
- **Stop empty strategy:** revokes the empty sleeve and releases its reservation. Holdings require pause or close first.

Open/partial/unknown orders block new plans. Durable intents precede API submission; deterministic account-wide date/symbol/side IDs prevent duplicate submission. A timeout or crash never causes blind resending. A broker lookup can recover the outcome. If it cannot, inspect Alpaca and resolve only after proving what happened; never delete an intent to unblock trading.

Existing sessions migrate to paused with scheduling disabled. Their old order/decision records remain. Adopt retained shares explicitly or stop an empty old sleeve and activate a freshly evaluated version. Reevaluate after numerical/application/dependency updates: activation binds dataset, source, configuration, results, and runtime provenance.

The adapter always uses `paper=True` and checks `https://paper-api.alpaca.markets`; there is no live URL switch. Simulation omits actual queue position, impact, dividends, and some fill conditions. Account orders are never submitted by migrations or implementation tests.
