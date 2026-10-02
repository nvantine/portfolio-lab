from marketdata.universe import DEFAULT_ETFS


def test_default_universe_has_spy():
    assert "SPY" in DEFAULT_ETFS
