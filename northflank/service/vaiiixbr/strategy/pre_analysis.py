from __future__ import annotations

from typing import Any

import pandas as pd

from vaiiixbr.config import Settings


def analyze_previous_day_context(prepared: pd.DataFrame) -> dict[str, Any]:
    if len(prepared) < 2 or not isinstance(prepared.index, pd.DatetimeIndex):
        return {"previous_day_label": "indefinido", "previous_day_change_pct": 0.0, "previous_day_range_pct": 0.0}

    daily = prepared[["open", "high", "low", "close", "volume"]].copy()
    idx = daily.index
    if idx.tz is not None:
        daily.index = idx.tz_localize(None)
    daily = daily.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    if len(daily) < 2:
        return {"previous_day_label": "indefinido", "previous_day_change_pct": 0.0, "previous_day_range_pct": 0.0}

    prev_day = daily.iloc[-2]
    open_ = float(prev_day["open"])
    high = float(prev_day["high"])
    low = float(prev_day["low"])
    close = float(prev_day["close"])
    range_pct = ((high - low) / open_ * 100) if open_ else 0.0
    change_pct = ((close - open_) / open_ * 100) if open_ else 0.0
    body_ratio = (abs(close - open_) / (high - low)) if (high - low) > 0 else 0.0

    label = "lateral"
    if change_pct > 0.6 and body_ratio >= 0.5:
        label = "alta_forte"
    elif change_pct < -0.6 and body_ratio >= 0.5:
        label = "baixa_forte"
    elif change_pct < 0 and abs(change_pct) < 0.6:
        label = "correcao_controlada"

    return {
        "previous_day_label": label,
        "previous_day_change_pct": change_pct,
        "previous_day_range_pct": range_pct,
    }


def build_pre_analysis(
    prepared: pd.DataFrame,
    signal_metrics: dict[str, Any],
    trade_metrics: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    context = analyze_previous_day_context(prepared)
    recent_win_rate = float(trade_metrics.get("win_rate", 0.0) or 0.0)
    high_conf_rate = float(trade_metrics.get("high_confidence_trade_rate", 0.0) or 0.0)
    yesterday_label = str(context.get("previous_day_label", "indefinido"))

    operation_mode = "normal"
    if recent_win_rate >= 60.0 and high_conf_rate >= 50.0 and yesterday_label in {"alta_forte", "correcao_controlada"}:
        operation_mode = "agressivo"
    elif recent_win_rate < 50.0 or yesterday_label in {"lateral", "baixa_forte"}:
        operation_mode = "defensivo"

    if operation_mode == "defensivo":
        recommended_min_score = max(settings.high_confidence_score, 85)
    elif operation_mode == "agressivo":
        recommended_min_score = settings.high_confidence_score
    else:
        recommended_min_score = max(settings.high_confidence_score, 82)

    return {
        **context,
        "recent_win_rate": recent_win_rate,
        "avg_score_wins": float(trade_metrics.get("avg_score_wins", 0.0) or 0.0),
        "avg_score_losses": float(trade_metrics.get("avg_score_losses", 0.0) or 0.0),
        "high_confidence_trade_rate": high_conf_rate,
        "saved_signal_count": int(signal_metrics.get("total_signals", 0) or 0),
        "operation_mode": operation_mode,
        "recommended_min_score": recommended_min_score,
    }
