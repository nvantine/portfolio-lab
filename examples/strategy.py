"""Hermes strategy contract: input is a chronological pandas price frame."""
def target_weights(history, current_weights, parameters):
    tickers = list(history.columns)
    cap = float(parameters.get("cap", .2))
    allocation = min(1 / len(tickers), cap)
    return dict.fromkeys(tickers, allocation)
