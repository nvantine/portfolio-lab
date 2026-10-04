"""The only trading adapter. Endpoint is unconditionally Alpaca PAPER."""
import os
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from alpaca.common.enums import BaseURL
from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetCalendarRequest, GetOrdersRequest, LimitOrderRequest
from django.conf import settings
from dotenv import load_dotenv


class PaperBroker:
    def __init__(self):
        load_dotenv(settings.BASE_DIR / ".env.paper", override=False)
        key, secret = os.getenv("ALPACA_PAPER_API_KEY"), os.getenv("ALPACA_PAPER_SECRET_KEY")
        if not key or not secret:
            raise ValueError("Set separate ALPACA_PAPER_API_KEY and ALPACA_PAPER_SECRET_KEY in .env.paper")
        self.client = TradingClient(api_key=key, secret_key=secret, paper=True)
        if self.client._base_url != BaseURL.TRADING_PAPER:
            raise RuntimeError("Paper endpoint enforcement failed")

    def state(self):
        clock = self.client.get_clock()
        today = clock.timestamp.astimezone(ZoneInfo("America/New_York")).date()
        calendar = self.client.get_calendar(GetCalendarRequest(start=today - timedelta(days=14), end=today - timedelta(days=1)))
        account = self.client.get_account()
        positions = self.client.get_all_positions()
        orders = self.client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500))
        return {"open": clock.is_open, "date": today, "previous_session": max(day.date for day in calendar),
                "equity": Decimal(account.equity), "timestamp": clock.timestamp.isoformat(),
                "cash": Decimal(account.cash), "blocked": bool(account.trading_blocked or account.account_blocked),
                "positions": {p.symbol: {"qty": Decimal(p.qty), "value": Decimal(p.market_value)} for p in positions},
                "open_orders": [str(order.id) for order in orders]}

    def lookup(self, client_id):
        try:
            return self.client.get_order_by_client_id(client_id)
        except APIError as exc:
            if exc.status_code == 404:
                return None
            raise

    def submit(self, intent):
        return self.client.submit_order(LimitOrderRequest(symbol=intent.symbol, qty=intent.qty,
                    side=OrderSide.BUY if intent.side == "buy" else OrderSide.SELL,
                    time_in_force=TimeInForce.DAY, limit_price=float(intent.limit_price),
                    client_order_id=intent.client_order_id, extended_hours=False))

    def cancel(self, order_id):
        self.client.cancel_order_by_id(order_id)
