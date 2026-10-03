import numpy as np
import pandas as pd
import pytest
from backtest.engine import evaluate, validate_weights
from optimizer.risk import max_drawdown, cvar, metrics


def test_no_future_inputs_delay_and_costs():
    frame = pd.DataFrame({"SPY": 100 * 1.01 ** np.arange(70)}, index=pd.bdate_range("2020-01-01", periods=70))
    seen = []
    def strategy(history, current, params):
        seen.append(history.index[-1])
        return {"SPY": 1}
    result = evaluate(frame, strategy, {"lookback": 10, "cap": 1, "cost_bps": 0, "rebalance": "daily"}, 20, 40)
    assert seen[0] == frame.index[19]
    assert seen[1] == frame.index[20]
    assert result["returns"][0] == 0
    assert result["returns"][1] == pytest.approx(.01)
    charged = evaluate(frame, strategy, {"lookback": 10, "cap": 1, "cost_bps": 10}, 20, 40)
    assert charged["wealth"][-1] < result["wealth"][-1]
    altered = frame.copy()
    altered.iloc[40:] *= 100
    assert evaluate(altered, strategy, {"lookback": 10, "cap": 1, "cost_bps": 0}, 20, 40)["returns"] == result["returns"]


def test_cash_and_weight_contract():
    assert validate_weights({}, ["A", "B"]).sum() == 0
    for invalid in [{"X": .1}, {"A": -1}, {"A": float("nan")}, {"A": .8, "B": .8}]:
        with pytest.raises(ValueError):
            validate_weights(invalid, ["A", "B"])


def test_risk_metrics_known_values():
    assert max_drawdown([-.2, 0, .1]) == pytest.approx(.2)
    assert cvar([-.1, -.2, .1, .1], confidence_level=.5) == pytest.approx(.15)
    assert metrics([0, 0])["sharpe"] is None
