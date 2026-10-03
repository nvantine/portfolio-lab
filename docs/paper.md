# Paper execution operator guide

Historical research credentials remain in `.env` as `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`. Trading requires **separate paper credentials**:

1. In your local editor copy `.env.paper.example` to `.env.paper` in the project root.
2. Set `ALPACA_PAPER_API_KEY` and `ALPACA_PAPER_SECRET_KEY` using keys from Alpaca's **Paper Trading** dashboard. Do not paste them into chat.
3. Run `chmod 600 .env.paper`. Git ignores this file. Keep it readable only by the trusted operator/broker service account.
4. Confirm presence without printing values:

   ```bash
   uv run python -c 'from dotenv import dotenv_values; values=dotenv_values(".env.paper"); print("Paper key present:", bool(values.get("ALPACA_PAPER_API_KEY")), "Paper secret present:", bool(values.get("ALPACA_PAPER_SECRET_KEY")))'
   ```

5. Create your operator login interactively: `uv run python manage.py createsuperuser`.
6. Refresh the ETF universe and freeze a current real Alpaca dataset. Queue and inspect a validation experiment with position cap at most 0.2 and budget at most $10,000. Synthetic datasets cannot be approved.
7. Log in to `/paper/`, open the candidate's results/configuration/hash, and click **Approve this version for paper execution**. The application verifies that the evaluator and lock file match the reviewed run. Changed strategy source, parameters, dataset or results invalidate approval.
8. Use a dedicated Alpaca paper account with no unrelated/short/fractional positions. The app treats matching whole-share positions as belonging to the approved session; it does not isolate a subaccount inside Alpaca.
9. Click **Run one paper cycle**, or have a trusted operator process run `uv run portfolio-lab paper tick --session ID` during regular exchange hours. This command can create **paper** orders after approval. Hermes cannot call it through the socket. No unattended paper scheduler is installed.
10. Inspect order status and filled quantities after each cycle. Sell orders precede buys; later cycles reconcile them. Daily IDs prevent a second order for the same session/date/symbol/side. DAY orders are not chased or repriced automatically.

Monthly mode reuses the first month's approved strategy targets during the month, allowing staged sells/buys to complete; daily mode recomputes targets each session. Whole-share rounding leaves cash. Prices are prior-session unadjusted IEX closes and are only limit references; fills are not assured. Markets must be open and every cached ETF must reach the prior exchange session. Missing daily bars block execution.

## Stop and investigate

- **Pause** disables new intents immediately, waits for an in-flight cycle, reconciles and requests cancellation of known session orders. It does not sell holdings. A paused session requires revocation/new approval to resume.
- **Revoke** also invalidates the approval. Pending or uncertain earlier orders block approval of another session.
- If submission times out, the persisted intent becomes `unknown`. A later lookup by client ID may recover it, but the app never resends an ambiguous submission. If lookup stays missing, inspect the Alpaca paper dashboard and resolve the ledger only after proving the outcome. Do not blindly delete intents.
- If cancellation cannot be confirmed, the UI records that fact. Check and cancel remaining orders in Alpaca's paper dashboard. Local stop state alone cannot retract an order already accepted by the broker.
- New approval requires all earlier orders to be terminal. Positions remain in the dedicated account and are adopted by the next approved session. Review that state before proceeding.

The API URL is hardcoded and checked: `https://paper-api.alpaca.markets`. The UI, CLI and environment provide no live URL option. Fake-broker tests cover approval, endpoint enforcement, stale data, repeat cycles, unknown submissions, partial fills and revocation. No real paper orders were submitted during implementation.
