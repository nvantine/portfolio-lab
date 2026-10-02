from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.common.exceptions import APIError
from django.core.management import call_command, CommandError

from marketdata.models import Asset, PricePoint
from marketdata.prices import load_aligned_close_prices
from marketdata.universe import DEFAULT_ETFS


def test_default_universe_has_spy():
    assert "SPY" in DEFAULT_ETFS


@pytest.mark.django_db
def test_refresh_prices_caches_adjusted_bars_without_duplicates():
    bar = SimpleNamespace(timestamp=datetime(2024, 1, 3, tzinfo=timezone.utc), close=450.25)
    client = SimpleNamespace(get_stock_bars=lambda request: SimpleNamespace(data={"SPY": [bar]}))

    with patch("marketdata.management.commands.refresh_prices.get_client", return_value=client):
        call_command("refresh_prices", "SPY", start="2024-01-02", end="2024-01-04")
        bar.close = 451.50
        call_command("refresh_prices", "SPY", start="2024-01-02", end="2024-01-04")

    assert PricePoint.objects.count() == 1
    assert PricePoint.objects.get().adjusted_close == Decimal("451.50")


@pytest.mark.django_db
def test_fetch_requests_iex_daily_all_adjustments():
    requests = []

    def get_stock_bars(request):
        requests.append(request)
        return SimpleNamespace(data={"SPY": []})

    client = SimpleNamespace(get_stock_bars=get_stock_bars)
    with patch("marketdata.management.commands.refresh_prices.get_client", return_value=client):
        call_command("refresh_prices", "SPY", start="2024-01-02", end="2024-01-04")

    assert requests[0].feed == DataFeed.IEX
    assert requests[0].adjustment == Adjustment.ALL
    assert str(requests[0].timeframe) == "1Day"
    assert requests[0].end.date() == date(2024, 1, 5)
    assert not Asset.objects.exists()


@pytest.mark.django_db
def test_aligned_prices_use_only_shared_dates():
    spy = Asset.objects.create(ticker="SPY")
    agg = Asset.objects.create(ticker="AGG")
    for day in (1, 2, 3, 4):
        PricePoint.objects.create(asset=spy, date=date(2024, 1, day), adjusted_close=100 + day)
    for day in (2, 3, 4, 5):
        PricePoint.objects.create(asset=agg, date=date(2024, 1, day), adjusted_close=90 + day)

    prices = load_aligned_close_prices(["SPY", "AGG"], date(2024, 1, 1), date(2024, 1, 5))
    assert list(prices.columns) == ["SPY", "AGG"]
    assert list(prices.index) == [date(2024, 1, day) for day in (2, 3, 4)]


@pytest.mark.django_db
def test_aligned_prices_report_missing_ticker():
    spy = Asset.objects.create(ticker="SPY")
    PricePoint.objects.create(asset=spy, date=date(2024, 1, 2), adjusted_close=100)
    with pytest.raises(ValueError, match="No cached prices for: AGG"):
        load_aligned_close_prices(["SPY", "AGG"], date(2024, 1, 1), date(2024, 1, 5))


@pytest.mark.django_db
def test_refresh_reports_api_error_and_keeps_other_tickers(capsys):
    def get_stock_bars(request):
        if request.symbol_or_symbols == "QQQ":
            http_error = SimpleNamespace(response=SimpleNamespace(status_code=429))
            raise APIError('{"code": 429, "message": "rate limit"}', http_error)
        bar = SimpleNamespace(timestamp=datetime(2024, 1, 3, tzinfo=timezone.utc), close=450.25)
        return SimpleNamespace(data={"SPY": [bar]})

    client = SimpleNamespace(get_stock_bars=get_stock_bars)
    with patch("marketdata.management.commands.refresh_prices.get_client", return_value=client):
        with pytest.raises(CommandError, match="Refresh incomplete for QQQ"):
            call_command("refresh_prices", "SPY", "QQQ", start="2024-01-02", end="2024-01-04")

    assert PricePoint.objects.filter(asset__ticker="SPY").count() == 1
    assert "rate limit reached" in capsys.readouterr().err
