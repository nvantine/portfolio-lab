import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def prices():
    rng = np.random.default_rng(7)
    return pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(.001, .01, (420, 6)), axis=0)), index=pd.bdate_range("2020-01-01", periods=420), columns=["SPY", "QQQ", "AGG", "GLD", "TLT", "EFA"])
