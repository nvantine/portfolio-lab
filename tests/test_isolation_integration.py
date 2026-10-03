"""Explicit opt-in integration tests; never fall back to host execution."""
import os
import nbformat
import pandas as pd
import pytest

pytestmark = pytest.mark.skipif(os.getenv("LAB_TEST_CONTAINERS") != "1", reason="Requires an explicitly enabled rootless runtime and built worker image")


def test_strategy_executes_with_limits_and_no_credentials():
    from workers.isolation import StrategyProcess
    source = '''
import os
from pathlib import Path
def target_weights(history, current_weights, parameters):
    assert not any("ALPACA" in key for key in os.environ)
    assert not Path("/app/.env").exists()
    assert Path("/sys/fs/cgroup/memory.max").read_text().strip() == "4294967296"
    quota, period = map(int, Path("/sys/fs/cgroup/cpu.max").read_text().split())
    assert quota / period == 2
    assert Path("/sys/fs/cgroup/pids.max").read_text().strip() == "128"
    import socket
    assert socket.socket().connect_ex(("1.1.1.1", 80)) != 0
    return {ticker: 1/len(history.columns) for ticker in history.columns}
'''
    frame = pd.DataFrame({"SPY": [100., 101.], "AGG": [100., 99.]}, index=pd.to_datetime(["2024-01-02", "2024-01-03"]))
    with StrategyProcess(source) as worker:
        assert worker.weights(frame, {}, {}) == {"SPY": .5, "AGG": .5}
        assert worker.image_digest.startswith("sha256:")


def test_notebook_executes_and_removes_rich_outputs():
    from workers.isolation import StrategyProcess
    book = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell('import pandas as pd\nfrom IPython.display import display, HTML\nprices = pd.read_csv("prices.csv")\nprint(len(prices))\ndisplay(HTML("<script>bad()</script>"))')])
    with StrategyProcess() as worker:
        result = worker.request({"action": "notebook", "notebook": book, "dates": ["2024-01-02", "2024-01-03"], "tickers": ["SPY"], "prices": [[100], [101]]})
    outputs = " ".join(result["cells"][0]["outputs"])
    assert "2" in outputs
    assert "<script>" not in outputs
