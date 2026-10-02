"""Fetch and cache adjusted daily ETF closes from Alpaca historical bars."""

import re
from datetime import date, timedelta

from alpaca.common.exceptions import APIError
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from marketdata.alpaca_client import check_connection, fetch_daily_bars, get_client
from marketdata.prices import save_daily_bars
from marketdata.universe import DEFAULT_ETFS


def api_error_message(status_code: int | None) -> str:
    """Explain common Alpaca failures without displaying response bodies or secrets."""
    return {
        401: "Alpaca rejected the credentials (HTTP 401)",
        403: "IEX data access was denied (HTTP 403)",
        429: "Alpaca rate limit reached (HTTP 429); retry later",
    }.get(status_code, f"Alpaca request failed (HTTP {status_code or 'unknown'})")


class Command(BaseCommand):
    help = "Refresh IEX daily adjusted closes, or check historical bars access."

    def add_arguments(self, parser) -> None:
        parser.add_argument("tickers", nargs="*", help="ETFs to refresh (default: editable universe)")
        parser.add_argument("--start", help="First date, YYYY-MM-DD (default: two years ago)")
        parser.add_argument("--end", help="Last date, YYYY-MM-DD (default: yesterday)")
        parser.add_argument(
            "--check-connection",
            action="store_true",
            help="Check SPY bars without saving prices",
        )

    def handle(self, *args, **options) -> None:
        if options["check_connection"]:
            try:
                has_bars = check_connection()
            except ImproperlyConfigured as exc:
                raise CommandError(str(exc)) from None
            except APIError as exc:
                raise CommandError(api_error_message(exc.status_code)) from None
            except Exception:
                raise CommandError(
                    "Alpaca historical bars request failed. Check credentials, "
                    "network access, and IEX market data entitlement."
                ) from None
            if not has_bars:
                raise CommandError("Alpaca responded, but no recent SPY IEX daily bars were returned.")
            self.stdout.write(self.style.SUCCESS("Alpaca historical bars connection succeeded (IEX, adjusted)."))
            return

        end = self.parse_date(options["end"], "end") if options["end"] else date.today() - timedelta(days=1)
        start = self.parse_date(options["start"], "start") if options["start"] else end - timedelta(days=730)
        if start > end:
            raise CommandError("Start date must be on or before end date")
        if end >= date.today():
            raise CommandError("End date must be before today to avoid an incomplete daily bar")

        tickers = list(dict.fromkeys(ticker.upper() for ticker in (options["tickers"] or DEFAULT_ETFS)))
        invalid = [ticker for ticker in tickers if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,11}", ticker)]
        if invalid:
            raise CommandError(f"Invalid ticker(s): {', '.join(invalid)}")

        try:
            client = get_client()
        except ImproperlyConfigured as exc:
            raise CommandError(str(exc)) from None

        failed = []
        for ticker in tickers:
            try:
                bars = fetch_daily_bars(client, ticker, start, end)
            except APIError as exc:
                failed.append(ticker)
                self.stderr.write(f"{ticker}: {api_error_message(exc.status_code)}")
                continue
            except Exception:
                failed.append(ticker)
                self.stderr.write(f"{ticker}: historical bars request failed; check network access")
                continue
            try:
                count = save_daily_bars(ticker, bars)
            except ValueError as exc:
                failed.append(ticker)
                self.stderr.write(str(exc))
                continue
            except Exception:
                failed.append(ticker)
                self.stderr.write(f"{ticker}: could not save adjusted closes to SQLite")
                continue
            if count == 0:
                self.stdout.write(f"{ticker}: no IEX bars in this range; nothing saved")
            else:
                self.stdout.write(f"{ticker}: saved {count} adjusted daily closes")

        if failed:
            raise CommandError(f"Refresh incomplete for {', '.join(failed)}; see messages above")

    @staticmethod
    def parse_date(value: str, name: str) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise CommandError(f"{name} must be a valid YYYY-MM-DD date") from None
