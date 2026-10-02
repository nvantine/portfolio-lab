# Portfolio Lab

A small Django research app for historical ETF data and portfolio optimization. Phase 2 adds read-only Alpaca price caching and a pure Python optimization package. The web pages still show placeholders; dashboard charts and saved runs come in Phase 3.

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

The connection check requests recent **daily SPY bars** using `DataFeed.IEX` and `Adjustment.ALL`. IEX is explicitly chosen because it is the stock feed available on Alpaca's free Basic plan; `ALL` adjusts for splits and dividends. IEX covers one exchange, so its bars can differ from consolidated SIP bars. The application only uses Alpaca's historical stock data client.

## Refresh prices

Fetch the editable default universe in `marketdata/universe.py` for the last two years through yesterday:

```bash
uv run --no-project --python .venv/bin/python manage.py refresh_prices
```

Or fetch named ETFs over an inclusive date range:

```bash
uv run --no-project --python .venv/bin/python manage.py refresh_prices SPY QQQ AGG --start 2025-01-01 --end 2025-12-31
```

Each ticker is requested separately so the command identifies a failing or empty ticker. A repeat refresh updates existing `(asset, date)` rows instead of adding duplicates. API failures are reported without displaying credentials or response bodies. No bar is invented for a missing date or an ETF that started later. The cached-price loader uses only dates shared by all requested ETFs and requires at least three common price dates.

## Optimization methods

`optimizer/` accepts pandas inputs and has no Django imports. Supply a DataFrame of aligned **daily returns** to a covariance estimator; missing or non-finite values cause a clear error. The sample estimator uses pandas sample covariance. The Ledoit–Wolf estimator uses scikit-learn shrinkage and returns the same ticker labels.

Both optimizers return a ticker-to-weight dictionary with nonnegative weights summing to one. Minimum variance minimizes `wᵀΣw`. Mean-variance maximizes `μᵀw − λwᵀΣw`, where `μ` and `Σ` use daily units and `λ` is a nonnegative risk-aversion input. `max_sharpe` and the risk metrics remain placeholders for later phases.

## Code map

- `portfolio_lab/`: Django settings, environment loading, and URL routing.
- `marketdata/`: ETF and daily adjusted price models, editable default ticker list, historical bars fetch, SQLite cache, and shared-date alignment.
- `portfolio/`: saved optimization run model, placeholder views, and templates.
- `optimizer/`: Django-independent covariance estimators and CVXPY optimizers, plus later-phase risk metric placeholders.
- `tests/`: mocked fetch/cache checks, date alignment, optimizer validation, SciPy comparison, and page rendering.

`OptimizationRun` includes `parameters`, `input_snapshot`, and `results` JSON fields so future runs can store their exact inputs and outputs. SQLite is for local research; `db.sqlite3` and `.env` are ignored by Git.

## Next phase

Build the results page with a weights chart, efficient frontier, risk metrics, and a simple equal-weight comparison. Save each run's parameters, input snapshot, and outputs in `OptimizationRun`.

## API references

- [Django 6.1 models and migrations](https://docs.djangoproject.com/en/6.1/intro/overview/)
- [Alpaca historical stock client](https://alpaca.markets/sdks/python/api_reference/data/stock/historical.html)
- [Alpaca stock bars request](https://alpaca.markets/sdks/python/api_reference/data/stock/requests.html)
- [Alpaca feed and adjustment enums](https://alpaca.markets/sdks/python/api_reference/data/enums.html)
- [Alpaca Basic market data coverage](https://docs.alpaca.markets/us/docs/about-market-data-api)
- [CVXPY quadratic programming example](https://www.cvxpy.org/examples/basic/quadratic_program.html)
- [scikit-learn LedoitWolf](https://scikit-learn.org/stable/modules/generated/sklearn.covariance.LedoitWolf.html)
- [SciPy SLSQP](https://docs.scipy.org/doc/scipy/reference/optimize.minimize-slsqp.html)
