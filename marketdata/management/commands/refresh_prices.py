"""Price refresh entry point; caching implementation is planned for Phase 2."""

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from marketdata.alpaca_client import check_connection
from marketdata.universe import DEFAULT_ETFS


class Command(BaseCommand):
    help = "Check Alpaca historical bars access; price caching arrives in Phase 2."

    def add_arguments(self, parser) -> None:
        parser.add_argument("tickers", nargs="*", help="ETF tickers to refresh in Phase 2")
        parser.add_argument(
            "--check-connection",
            action="store_true",
            help="Request one recent SPY daily bar without writing to the database",
        )

    def handle(self, *args, **options) -> None:
        if not options["check_connection"]:
            raise CommandError(
                "Price refresh is planned for Phase 2. For now, use --check-connection. "
                f"The default universe has {len(DEFAULT_ETFS)} ETFs."
            )

        try:
            has_bars = check_connection()
        except ImproperlyConfigured as exc:
            raise CommandError(str(exc)) from None
        except Exception:
            raise CommandError(
                "Alpaca historical bars request failed. Check your credentials, "
                "network access, and IEX market data entitlement."
            ) from None

        if not has_bars:
            raise CommandError("Alpaca responded, but no recent SPY IEX daily bars were returned.")
        self.stdout.write(self.style.SUCCESS("Alpaca historical bars connection succeeded (IEX, adjusted)."))
