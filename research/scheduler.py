"""Supervised scheduler: reconcile each minute; submit only eligible schedules."""
import fcntl
import time
from django.conf import settings
from research.jobs import heartbeat
from paper.models import PaperSession


def work(once=False):
    settings.LAB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with (settings.LAB_DATA_DIR / "scheduler.lock").open("w") as handle:
        try: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError("A scheduler is already running") from None
        while True:
            result = {"status": "idle"}
            from paper.account import pending
            active = list(PaperSession.objects.select_related("experiment__dataset").filter(active=True, scheduled=True, revoked=False))
            if active or pending():
                try:
                    from paper.account import cycle, broker_client, history_for
                    client = broker_client()
                    state = client.state()
                    if not state["open"] and state.get("completed_session"):
                        for sleeve in active:
                            if sleeve.state != "closing": history_for(sleeve, state["completed_session"])
                    result = cycle(broker=client, scheduled_only=True)
                except Exception as exc:
                    result = {"status": "blocked", "reason": str(exc) if isinstance(exc, ValueError) else "Cycle unavailable: check versions, market data, funding, and broker state"}
            heartbeat("scheduler", **result)
            if once: return result
            time.sleep(60)
