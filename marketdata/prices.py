"""Cache adjusted closes and align stored prices for future research views."""

from datetime import date
from decimal import Decimal
from math import isfinite

import pandas as pd
from django.db import transaction

from marketdata.models import Asset, PricePoint


def save_daily_bars(ticker: str, bars: list) -> int:
    """Upsert valid adjusted daily closes; return the number of saved dates."""
    closes = {}
    for bar in bars:
        close = float(bar.close)
        if not isfinite(close) or close <= 0:
            raise ValueError(f"{ticker}: received an invalid adjusted close")
        closes[bar.timestamp.date()] = Decimal(str(close))

    if not closes:
        return 0

    with transaction.atomic():
        asset, _ = Asset.objects.get_or_create(ticker=ticker)
        for bar_date, close in closes.items():
            PricePoint.objects.update_or_create(
                asset=asset,
                date=bar_date,
                defaults={"adjusted_close": close},
            )
    return len(closes)


def load_aligned_close_prices(tickers: list[str], start: date, end: date) -> pd.DataFrame:
    """Return closes on dates shared by every ticker, with no forward filling."""
    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        raise ValueError("Select at least one ticker")

    rows = list(
        PricePoint.objects.filter(asset__ticker__in=tickers, date__range=(start, end))
        .values_list("date", "asset__ticker", "adjusted_close")
    )
    if not rows:
        raise ValueError("No cached prices exist for the selected dates")

    prices = pd.DataFrame(rows, columns=["date", "ticker", "close"])
    observed = set(prices["ticker"])
    missing = [ticker for ticker in tickers if ticker not in observed]
    if missing:
        raise ValueError(f"No cached prices for: {', '.join(missing)}")

    wide = prices.pivot(index="date", columns="ticker", values="close")
    wide = wide.reindex(columns=tickers).sort_index().dropna()
    if len(wide) < 3:
        raise ValueError("Fewer than three shared price dates; choose a wider date range")
    return wide.astype(float)
