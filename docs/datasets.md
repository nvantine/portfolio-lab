# Fetching and saving datasets

The Tickers field accepts actual stock/ETF symbols separated by spaces, commas,
or newlines, for example `AAPL, MSFT, NVDA`. It accepts 100-symbol lists;
descriptions such as “top 100 Nasdaq by market cap” do not select a universe.
Supply the ticker list yourself. A current list used for historical research
also introduces survivorship bias; it is not historical index membership.

1. Enter a name, symbols, start/end dates, feed, and optional benchmark.
2. Click **Fetch and preview**. A named job appears immediately, with worker
   availability and per-symbol progress. This has not saved a dataset yet.
3. The preview appears automatically after fetching. Review coverage and
   exclusions. Saving requires at least 250 common positive daily closes.
4. Click **Save dataset snapshot**, explicitly accepting any excluded symbols
   or lost dates. The saved dataset becomes available in Research, including
   in an already-open Research page.

Selecting today excludes the incomplete current day and requests history
through yesterday. Weekends/holidays contribute no bars. The job records both
the requested and effective end dates. Future or reversed date ranges show
a prominent validation error and create no job. IEX is explicit by default;
SIP requires an appropriate Alpaca entitlement.

The dataset, research, and strategy lists poll a small authenticated revision
endpoint every two seconds. A changed revision fetches updated HTML with GET
and replaces only lists and relevant selection options. Draft forms, checked
comparison selections, and expanded coverage details are retained. Updates
defer while a list control is focused, pause in hidden tabs, and retry after
temporary network errors. Result/notebook pages update when their jobs finish.

Successful submissions redirect to GET pages to avoid duplicate POSTs on
refresh. Rejected dataset submissions return HTTP 400 with a visible error.
The preview remains explicitly reviewable rather than automatically accepting
missing histories or constituents.

Run the full foreground stack (`uv run portfolio-lab app run --port 8010`),
or start the queue worker separately (`uv run portfolio-lab jobs work`).
`manage.py runserver` runs only the website. Restart a running worker after
updating code; development runserver reloads code automatically. A Gunicorn
server needs a restart and `collectstatic` to serve updated scripts.

Verification includes the complete web queue/preview/save flow for 1 and 100
symbols using fake historical bars, invalid inputs, short/reduced previews,
credential failures, stable lightweight revisions, and JavaScript polling and
input preservation using DOM/network doubles. The live diagnostic on
2026-10-03 fetched SPY from 2024-01-01 through 2026-10-01 using Alpaca IEX:
690 sessions, saved as the local **SPY one-ticker diagnostic** snapshot.

The form/redirect behavior follows the [Django form guide](https://docs.djangoproject.com/en/6.1/topics/forms/);
bar parameters follow [Alpaca's StockBarsRequest reference](https://alpaca.markets/sdks/python/api_reference/data/stock/requests.html).
