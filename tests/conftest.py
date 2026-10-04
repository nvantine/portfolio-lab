import numpy as np
import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def no_external_http(monkeypatch):
    """SDK tests must supply fakes; never contact Alpaca or other HTTP services."""
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must use a fake HTTP/broker client")
    monkeypatch.setattr("requests.sessions.Session.request", blocked)


@pytest.fixture
def prices():
    rng = np.random.default_rng(7)
    return pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(.001, .01, (420, 6)), axis=0)), index=pd.bdate_range("2020-01-01", periods=420), columns=["SPY", "QQQ", "AGG", "GLD", "TLT", "EFA"])
