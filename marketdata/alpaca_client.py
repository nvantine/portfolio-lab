"""Only historical stock bars are requested from Alpaca."""

from datetime import datetime, timedelta, timezone

from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def check_connection() -> bool:
    """Request recent SPY daily bars; return whether at least one bar arrived."""
    if not settings.ALPACA_API_KEY or not settings.ALPACA_SECRET_KEY:
        raise ImproperlyConfigured(
            "Alpaca credentials are missing. Set ALPACA_API_KEY and "
            "ALPACA_SECRET_KEY in the project .env file."
        )

    client = StockHistoricalDataClient(
        api_key=settings.ALPACA_API_KEY,
        secret_key=settings.ALPACA_SECRET_KEY,
    )
    end = datetime.now(timezone.utc) - timedelta(days=1)
    request = StockBarsRequest(
        symbol_or_symbols="SPY",
        timeframe=TimeFrame(1, TimeFrameUnit.Day),
        start=end - timedelta(days=30),
        end=end,
        adjustment=Adjustment.ALL,
        feed=DataFeed.IEX,
    )
    bars = client.get_stock_bars(request)
    return bool(bars.data.get("SPY"))
