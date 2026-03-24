from __future__ import annotations

import pandas as pd

from vaiiixbr.config import Settings
from vaiiixbr.strategy.pre_analysis import analyze_previous_day_context, build_pre_analysis


def test_previous_day_context_returns_keys() -> None:
    idx = pd.date_range("2026-03-20 10:00", periods=20, freq="5min", tz="America/Sao_Paulo")
    df = pd.DataFrame({
        "open": [10 + i * 0.1 for i in range(20)],
        "high": [10.2 + i * 0.1 for i in range(20)],
        "low": [9.9 + i * 0.1 for i in range(20)],
        "close": [10.1 + i * 0.1 for i in range(20)],
        "volume": [1000] * 20,
    }, index=idx)
    result = analyze_previous_day_context(df)
    assert "previous_day_label" in result


def test_build_pre_analysis_contains_operation_mode() -> None:
    idx = pd.date_range("2026-03-20 10:00", periods=20, freq="5min", tz="America/Sao_Paulo")
    df = pd.DataFrame({
        "open": [10 + i * 0.1 for i in range(20)],
        "high": [10.2 + i * 0.1 for i in range(20)],
        "low": [9.9 + i * 0.1 for i in range(20)],
        "close": [10.1 + i * 0.1 for i in range(20)],
        "volume": [1000] * 20,
    }, index=idx)
    result = build_pre_analysis(df, {"total_signals": 0}, {"win_rate": 0.0}, Settings())
    assert result["operation_mode"] in {"agressivo", "normal", "defensivo"}
