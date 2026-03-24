from __future__ import annotations

import pandas as pd

from vaiiixbr.config import Settings
from vaiiixbr.execution.paper_trader import PaperTrader


def _prepared_frame(close_values: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2026-03-20 10:00", periods=len(close_values), freq="5min", tz="America/Sao_Paulo")
    rows = []
    for close in close_values:
        rows.append({
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1000,
            "atr": 1.0,
        })
    return pd.DataFrame(rows, index=idx)


def test_paper_trader_tracks_open_position_returns() -> None:
    trader = PaperTrader(Settings())
    prepared = _prepared_frame([10.0])
    state, closed_trade = trader.step(prepared, {"decision": "compra", "long_score": 85})
    assert closed_trade is None
    assert state["paper_in_position"] is True

    prepared2 = _prepared_frame([10.8])
    state2, closed_trade2 = trader.step(prepared2, {"decision": "compra", "long_score": 80})
    assert closed_trade2 is None
    assert state2["paper_position"]["market_value"] > state2["paper_position"]["invested_entry"]
    assert "return_pct_asset" in state2["paper_position"]


def test_paper_trader_closes_on_signal_loss() -> None:
    trader = PaperTrader(Settings())
    prepared = _prepared_frame([10.0])
    trader.step(prepared, {"decision": "compra", "long_score": 85})

    prepared2 = _prepared_frame([10.2])
    state, closed_trade = trader.step(prepared2, {"decision": "neutro", "long_score": 40})
    assert state["paper_in_position"] is False
    assert closed_trade is not None
    assert closed_trade["outcome"] == "signal_loss"
    assert "return_pct_on_initial_cash" in closed_trade
