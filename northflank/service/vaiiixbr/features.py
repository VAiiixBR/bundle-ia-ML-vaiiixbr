from __future__ import annotations

import numpy as np
import pandas as pd

from vaiiixbr.config import Settings
from vaiiixbr.indicators import atr, ema, rsi


class FeatureEngineer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Dados ausentes: {missing}")
        minimum = max(self.settings.trend_ma, self.settings.volume_window, self.settings.swing_lookback) + 5
        if len(df) < minimum:
            raise ValueError(f"Dados insuficientes para análise. Necessário ao menos {minimum} candles")

        data = df.copy()
        data["ema_fast"] = ema(data["close"], self.settings.fast_ma)
        data["ema_slow"] = ema(data["close"], self.settings.slow_ma)
        data["ema_trend"] = ema(data["close"], self.settings.trend_ma)
        data["rsi"] = rsi(data["close"], self.settings.rsi_period)
        data["atr"] = atr(data, self.settings.atr_period)
        data["vol_mean"] = data["volume"].rolling(self.settings.volume_window).mean()
        data["volume_ratio"] = np.where(data["vol_mean"] > 0, data["volume"] / data["vol_mean"], np.nan)
        data["body"] = (data["close"] - data["open"]).abs()
        data["range"] = data["high"] - data["low"]
        data["body_strength"] = np.where(data["range"] > 0, data["body"] / data["range"], 0.0)
        data["recent_high"] = data["high"].rolling(self.settings.swing_lookback).max()
        data["recent_low"] = data["low"].rolling(self.settings.swing_lookback).min()
        data["trend_up"] = (data["ema_fast"] > data["ema_slow"]) & (data["ema_slow"] > data["ema_trend"])
        data["pullback_long"] = (data["close"] > data["ema_trend"]) & (data["low"] <= data["ema_fast"])
        data["break_recent_high"] = data["close"] > data["recent_high"].shift(1)
        return data
