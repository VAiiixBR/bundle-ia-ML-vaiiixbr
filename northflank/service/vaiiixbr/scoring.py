from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from vaiiixbr.config import Settings


class EntryScorer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _score_long(self, row: pd.Series) -> Tuple[int, Dict[str, int]]:
        score = 0
        reasons: Dict[str, int] = {}
        if bool(row.get("trend_up", False)):
            score += 25
            reasons["tendencia_alta"] = 25
        if bool(row.get("pullback_long", False)):
            score += 15
            reasons["pullback"] = 15

        rsi_value = row.get("rsi", np.nan)
        if pd.notna(rsi_value) and 52 <= rsi_value <= 68:
            score += 15
            reasons["rsi_favoravel"] = 15
        elif pd.notna(rsi_value) and rsi_value > 75:
            score -= 10
            reasons["rsi_esticado"] = -10

        volume_ratio = row.get("volume_ratio", np.nan)
        if pd.notna(volume_ratio) and volume_ratio >= 1.2:
            score += 15
            reasons["volume_forte"] = 15
        elif pd.notna(volume_ratio) and volume_ratio < 0.8:
            score -= 5
            reasons["volume_fraco"] = -5

        body_strength = row.get("body_strength", np.nan)
        if pd.notna(body_strength) and body_strength >= 0.6:
            score += 10
            reasons["candle_confirmacao"] = 10

        close_ = row.get("close", np.nan)
        ema_fast = row.get("ema_fast", np.nan)
        atr_value = row.get("atr", np.nan)
        if pd.notna(close_) and pd.notna(ema_fast) and pd.notna(atr_value) and atr_value > 0:
            distance = abs(close_ - ema_fast) / atr_value
            if distance <= 1.0:
                score += 10
                reasons["entrada_nao_esticada"] = 10
            elif distance > 2.0:
                score -= 10
                reasons["entrada_esticada"] = -10

        if bool(row.get("break_recent_high", False)):
            score += 10
            reasons["rompimento_confirmado"] = 10

        return max(score, 0), reasons

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        scores = []
        reasons_text = []
        for _, row in data.iterrows():
            score, reasons = self._score_long(row)
            scores.append(score)
            reasons_text.append(", ".join(f"{k}:{v}" for k, v in reasons.items()))
        data["long_score"] = scores
        data["long_reasons"] = reasons_text
        data["entry_quality"] = np.where(data["long_score"] >= self.settings.high_confidence_score, "alta", "normal")
        return data
