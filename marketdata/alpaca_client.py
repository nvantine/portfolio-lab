"""Read-only access to Alpaca's historical daily stock bars."""

from datetime import date, datetime, timedelta, timezone

from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def get_client() -> StockHistoricalDataClient:
    """Build a market data client after checking locally loaded credentials."""
    if not settings.ALPACA_API_KEY or not settings.ALPACA_SECRET_KEY:
        raise ImproperlyConfigured(
            "Alpaca credentials are missing. Set ALPACA_API_KEY and "
            "ALPACA_SECRET_KEY in the project .env file."
        )

    return StockHistoricalDataClient(
        api_key=settings.ALPACA_API_KEY,
        secret_key=settings.ALPACA_SECRET_KEY,
    )


def fetch_daily_bars(
    client: StockHistoricalDataClient, ticker: str, start: date, end: date
) -> list:
    """Return split/dividend-adjusted IEX daily bars for an inclusive date range."""
    request = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame(1, TimeFrameUnit.Day),
        start=datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc),
        end=datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc),
        adjustment=Adjustment.ALL,
        feed=DataFeed.IEX,
    )
    return client.get_stock_bars(request).data.get(ticker, [])


def check_connection() -> bool:
    """Request recent SPY daily bars without writing to the database."""
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    return bool(fetch_daily_bars(get_client(), "SPY", end - timedelta(days=30), end))
