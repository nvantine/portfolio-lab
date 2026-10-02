# Portfolio Lab

A small Django research app for historical ETF data and portfolio optimization. Phase 1 contains the project scaffold, schema, placeholder pages, and a read-only Alpaca connection check. Price caching, optimization, and charts are planned for later phases.

## Start locally

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13. Django 6.1 supports Python 3.12 through 3.14; this project uses 3.13 for its pinned dependency set. From this directory:

```bash
uv venv --python 3.13 .venv
uv pip sync requirements.txt --python .venv/bin/python
uv run --no-project --python .venv/bin/python manage.py migrate
uv run --no-project --python .venv/bin/python manage.py runserver
```

Open <http://127.0.0.1:8000/>. The home and results pages work without Alpaca credentials. Stop the server with Ctrl+C.

Run the tests with:

```bash
uv run --no-project --python .venv/bin/python -m pytest
```

`requirements.in` lists the direct dependencies. `requirements.txt` pins the full resolved dependency tree. After changing `requirements.in`, regenerate and install it with:

```bash
uv pip compile requirements.in -o requirements.txt --python-version 3.13
uv pip sync requirements.txt --python .venv/bin/python
```

## Alpaca credentials

1. Copy the template in the project root: `cp .env.example .env`.
2. Open the new `portfolio-lab/.env` file in your local editor.
3. Replace `your_alpaca_api_key_here` after `ALPACA_API_KEY=` with your key.
4. Replace `your_alpaca_secret_key_here` after `ALPACA_SECRET_KEY=` with your secret.
5. Save the file. Never paste either value into a chat or commit `.env`.
6. Confirm both variables loaded without showing either value:

   ```bash
   uv run --no-project --python .venv/bin/python manage.py shell -c 'from django.conf import settings; print("Key loaded:", bool(settings.ALPACA_API_KEY), "Secret loaded:", bool(settings.ALPACA_SECRET_KEY))'
   ```

7. Check the historical bars connection without saving prices:

   ```bash
   uv run --no-project --python .venv/bin/python manage.py refresh_prices --check-connection
   ```

The connection check requests recent **daily SPY bars** using `DataFeed.IEX` and `Adjustment.ALL`. IEX is explicitly chosen because it is the stock feed available on Alpaca's free Basic plan; `ALL` adjusts for splits and dividends. IEX covers one exchange, so its bars can differ from consolidated SIP bars. The application only uses Alpaca's historical stock data client. The refresh command's ticker argument and database caching are placeholders until Phase 2.

## Code map

- `portfolio_lab/`: Django settings, environment loading, and URL routing.
- `marketdata/`: ETF and daily adjusted price models, editable default ticker list, and historical bars connection check.
- `portfolio/`: saved optimization run model, placeholder views, and templates.
- `optimizer/`: Django-independent function contracts for optimization, covariance estimation, and risk metrics. They raise `NotImplementedError` until their planned phases.
- `tests/`: small smoke tests for imports, universe configuration, and page rendering.

`OptimizationRun` includes `parameters`, `input_snapshot`, and `results` JSON fields so future runs can store their exact inputs and outputs. SQLite is for local research; `db.sqlite3` and `.env` are ignored by Git.

## Next phase

Implement historical bar refresh and caching, then sample and Ledoit-Wolf covariance plus minimum variance and mean-variance optimization. Test weight sums and constraints, and compare a CVXPY solution against SciPy SLSQP on a small fixed example.

## API references

- [Django 6.1 models and migrations](https://docs.djangoproject.com/en/6.1/intro/overview/)
- [Alpaca historical stock client](https://alpaca.markets/sdks/python/api_reference/data/stock/historical.html)
- [Alpaca stock bars request](https://alpaca.markets/sdks/python/api_reference/data/stock/requests.html)
- [Alpaca feed and adjustment enums](https://alpaca.markets/sdks/python/api_reference/data/enums.html)
- [Alpaca Basic market data coverage](https://docs.alpaca.markets/us/docs/about-market-data-api)
