from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import logging
import math

import numpy as np
import pandas as pd


# =========================================================
# LOGGING
# =========================================================
LOGGER_NAME = "VAIIIxBR"
logger = logging.getLogger(LOGGER_NAME)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


# =========================================================
# ENUMS / MODELS
# =========================================================
class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class MarketRegime(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    BREAKOUT = "BREAKOUT"
    MEAN_REVERSION = "MEAN_REVERSION"
    LOW_VOLUME = "LOW_VOLUME"
    NEUTRAL = "NEUTRAL"


@dataclass
class StrategyOutput:
    name: str
    signal: Signal
    score: float
    confidence: float
    reasons: List[str] = field(default_factory=list)


@dataclass
class EnsembleDecision:
    symbol: str
    regime: MarketRegime
    signal: Signal
    confidence: float
    final_score: float
    dynamic_weights: Dict[str, float]
    strategy_outputs: Dict[str, StrategyOutput]
    reasons: List[str]


@dataclass
class RiskConfig:
    stop_loss_pct: float = 0.008
    take_profit_pct: float = 0.012
    trailing_stop_pct: float = 0.004
    guaranteed_entry_confidence: float = 0.78
    max_bars_in_trade: int = 25
    daily_loss_limit_pct: float = 0.04
    cooldown_bars_after_exit: int = 2
    max_position_pct: float = 0.95
    min_cash_buffer: float = 1.0


@dataclass
class HybridConfig:
    symbol: str = "ITUB4"
    initial_cash: float = 50.0
    min_rows: int = 120

    # pesos base
    weight_holly_like: float = 0.35
    weight_quant_like: float = 0.40
    weight_ea_like: float = 0.25

    buy_threshold: float = 0.22
    sell_threshold: float = -0.22
    min_confidence: float = 0.58

    use_volume_filter: bool = True
    min_relative_volume: float = 1.03
    min_price: float = 1.0

    risk: RiskConfig = field(default_factory=RiskConfig)

    logs_dir: str = "logs_vaiiixbr"
    trades_file: str = "paper_trades_itub4.jsonl"
    metrics_file: str = "paper_metrics_itub4.json"

    # validação/execução
    allow_short: bool = False
    slippage_pct: float = 0.0005
    brokerage_per_order: float = 0.0


@dataclass
class Position:
    symbol: str
    side: str
    entry_price: float
    quantity: int
    stop_price: float
    take_price: float
    trailing_stop_price: float
    entry_index: Any = None
    entry_bar: int = 0
    highest_price: float = 0.0


# =========================================================
# VALIDATION / HELPERS
# =========================================================
REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def safe_last(series: pd.Series, default: float = 0.0) -> float:
    clean = series.replace([np.inf, -np.inf], np.nan).dropna()
    return default if clean.empty else float(clean.iloc[-1])


def validate_input(df: pd.DataFrame, config: HybridConfig) -> None:
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes: {sorted(missing)}")

    if len(df) < config.min_rows:
        raise ValueError(f"Dados insuficientes: mínimo {config.min_rows}, recebido {len(df)}")

    numeric_df = df[list(REQUIRED_COLUMNS)].copy()
    for col in REQUIRED_COLUMNS:
        numeric_df[col] = pd.to_numeric(numeric_df[col], errors="coerce")
    if numeric_df.isna().any().any():
        bad_cols = [c for c in REQUIRED_COLUMNS if numeric_df[c].isna().any()]
        raise ValueError(f"Dados inválidos ou não numéricos em: {bad_cols}")

    if (numeric_df["close"] <= 0).any() or (numeric_df["volume"] < 0).any():
        raise ValueError("Preço de fechamento deve ser > 0 e volume deve ser >= 0")

    if "symbol" in df.columns:
        unique_symbols = set(df["symbol"].dropna().astype(str).str.upper().unique())
        if unique_symbols and unique_symbols != {config.symbol}:
            raise ValueError(f"Este projeto é fixado em {config.symbol}. Recebido: {sorted(unique_symbols)}")

    if not pd.Index(df.index).is_monotonic_increasing:
        raise ValueError("O índice do DataFrame deve estar em ordem crescente")


# =========================================================
# INDICATORS
# =========================================================
def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    return rsi_series.fillna(50.0)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean().bfill()


def rolling_vwap(df: pd.DataFrame, window: int = 20) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical * df["volume"]
    return pv.rolling(window).sum() / df["volume"].rolling(window).sum().replace(0, np.nan)


# =========================================================
# FEATURE ENGINE
# =========================================================
class FeatureEngine:
    @staticmethod
    def build(df: pd.DataFrame) -> pd.DataFrame:
        x = df.copy()
        x["open"] = pd.to_numeric(x["open"], errors="coerce")
        x["high"] = pd.to_numeric(x["high"], errors="coerce")
        x["low"] = pd.to_numeric(x["low"], errors="coerce")
        x["close"] = pd.to_numeric(x["close"], errors="coerce")
        x["volume"] = pd.to_numeric(x["volume"], errors="coerce")

        x["ema_9"] = ema(x["close"], 9)
        x["ema_21"] = ema(x["close"], 21)
        x["ema_50"] = ema(x["close"], 50)
        x["rsi_14"] = rsi(x["close"], 14)
        x["atr_14"] = atr(x, 14)
        x["vwap_20"] = rolling_vwap(x, 20)

        x["ret_1"] = x["close"].pct_change(1).fillna(0.0)
        x["ret_5"] = x["close"].pct_change(5).fillna(0.0)
        x["ret_10"] = x["close"].pct_change(10).fillna(0.0)

        x["vol_ma_20"] = x["volume"].rolling(20).mean()
        x["rel_volume"] = (x["volume"] / x["vol_ma_20"].replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(1.0)

        x["momentum"] = (x["close"] / x["close"].shift(10) - 1).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        x["trend_spread"] = ((x["ema_9"] - x["ema_21"]) / x["close"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        x["long_trend_spread"] = ((x["ema_21"] - x["ema_50"]) / x["close"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        x["range_pct"] = ((x["high"] - x["low"]) / x["close"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        x["body_pct"] = ((x["close"] - x["open"]) / x["open"].replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        x["dist_to_vwap"] = ((x["close"] - x["vwap_20"]) / x["close"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        x["atr_pct"] = (x["atr_14"] / x["close"]).replace([np.inf, -np.inf], np.nan).fillna(0.0)

        return x


# =========================================================
# REGIME DETECTOR
# =========================================================
class MarketRegimeDetector:
    def detect(self, df: pd.DataFrame) -> Tuple[MarketRegime, List[str]]:
        row = df.iloc[-1]
        recent_high = float(df["high"].iloc[-10:-1].max())
        recent_low = float(df["low"].iloc[-10:-1].min())
        reasons: List[str] = []

        if row["rel_volume"] < 0.9:
            reasons.append("volume relativo baixo")
            return MarketRegime.LOW_VOLUME, reasons

        if row["close"] > recent_high and row["rel_volume"] >= 1.2:
            reasons.append("rompimento com volume")
            return MarketRegime.BREAKOUT, reasons

        if row["ema_9"] > row["ema_21"] > row["ema_50"] and row["rsi_14"] >= 52:
            reasons.append("estrutura de tendência de alta")
            return MarketRegime.TREND_UP, reasons

        if row["ema_9"] < row["ema_21"] < row["ema_50"] and row["rsi_14"] <= 48:
            reasons.append("estrutura de tendência de baixa")
            return MarketRegime.TREND_DOWN, reasons

        if abs(row["dist_to_vwap"]) >= 0.01 and ((row["rsi_14"] <= 32) or (row["rsi_14"] >= 68)):
            reasons.append("estiramento para reversão")
            return MarketRegime.MEAN_REVERSION, reasons

        reasons.append("regime neutro")
        return MarketRegime.NEUTRAL, reasons


# =========================================================
# STRATEGIES
# =========================================================
class BaseStrategy:
    name: str = "base"

    def evaluate(self, df: pd.DataFrame, regime: MarketRegime) -> StrategyOutput:
        raise NotImplementedError


class HollyLikeStrategy(BaseStrategy):
    name = "holly_like"

    def evaluate(self, df: pd.DataFrame, regime: MarketRegime) -> StrategyOutput:
        row = df.iloc[-1]
        score = 0.0
        reasons: List[str] = []

        if row["ema_9"] > row["ema_21"]:
            score += 0.26
            reasons.append("EMA9 > EMA21")
        else:
            score -= 0.26
            reasons.append("EMA9 < EMA21")

        if row["ret_5"] > 0:
            score += 0.18
            reasons.append("ret_5 positivo")
        else:
            score -= 0.18
            reasons.append("ret_5 negativo")

        if row["rel_volume"] > 1.15:
            score += 0.18
            reasons.append("volume relativo forte")
        elif row["rel_volume"] < 0.95:
            score -= 0.12
            reasons.append("volume relativo fraco")

        if row["body_pct"] > 0 and row["close"] > row["vwap_20"]:
            score += 0.12
            reasons.append("candle comprador acima do VWAP")
        elif row["body_pct"] < 0 and row["close"] < row["vwap_20"]:
            score -= 0.12
            reasons.append("candle vendedor abaixo do VWAP")

        if regime == MarketRegime.BREAKOUT:
            score += 0.08
            reasons.append("bônus de regime breakout")
        elif regime == MarketRegime.LOW_VOLUME:
            score -= 0.10
            reasons.append("penalidade por baixo volume")

        if row["rsi_14"] > 78:
            score -= 0.12
            reasons.append("RSI sobrecomprado")
        elif row["rsi_14"] < 32:
            score += 0.06
            reasons.append("RSI em possível recuperação")

        signal = Signal.HOLD
        if score >= 0.18:
            signal = Signal.BUY
        elif score <= -0.18:
            signal = Signal.SELL
        confidence = _clip(0.48 + abs(score) / 1.0, 0.0, 1.0)
        return StrategyOutput(self.name, signal, score, confidence, reasons)


class QuantLikeStrategy(BaseStrategy):
    name = "quant_like"

    def evaluate(self, df: pd.DataFrame, regime: MarketRegime) -> StrategyOutput:
        row = df.iloc[-1]
        feature_scores = {
            "momentum": _clip(row["momentum"] * 8.0, -0.28, 0.28),
            "trend_spread": _clip(row["trend_spread"] * 42.0, -0.24, 0.24),
            "long_trend_spread": _clip(row["long_trend_spread"] * 28.0, -0.18, 0.18),
            "ret_1": _clip(row["ret_1"] * 8.0, -0.10, 0.10),
            "ret_10": _clip(row["ret_10"] * 4.0, -0.12, 0.12),
            "dist_to_vwap": _clip(row["dist_to_vwap"] * 10.0, -0.08, 0.08),
        }
        score = float(sum(feature_scores.values()))
        reasons = [f"{k}={v:+.3f}" for k, v in feature_scores.items()]

        if regime == MarketRegime.TREND_UP:
            score += 0.06
            reasons.append("bônus regime tendência alta")
        elif regime == MarketRegime.TREND_DOWN:
            score -= 0.06
            reasons.append("penalidade regime tendência baixa")
        elif regime == MarketRegime.MEAN_REVERSION:
            score -= np.sign(score) * 0.04
            reasons.append("redução por regime de reversão")

        if row["rsi_14"] > 80:
            score -= 0.08
            reasons.append("penalidade RSI extremo")
        elif row["rsi_14"] < 20:
            score += 0.08
            reasons.append("bônus RSI extremo vendedor")

        signal = Signal.HOLD
        if score >= 0.16:
            signal = Signal.BUY
        elif score <= -0.16:
            signal = Signal.SELL
        confidence = _clip(0.50 + abs(score) / 0.85, 0.0, 1.0)
        return StrategyOutput(self.name, signal, score, confidence, reasons)


class EALikeStrategy(BaseStrategy):
    name = "ea_like"

    def evaluate(self, df: pd.DataFrame, regime: MarketRegime) -> StrategyOutput:
        row = df.iloc[-1]
        prev = df.iloc[-2]
        score = 0.0
        reasons: List[str] = []

        if row["ema_9"] > row["ema_21"] and prev["ema_9"] <= prev["ema_21"]:
            score += 0.34
            reasons.append("cruzamento altista EMA9/EMA21")
        elif row["ema_9"] < row["ema_21"] and prev["ema_9"] >= prev["ema_21"]:
            score -= 0.34
            reasons.append("cruzamento baixista EMA9/EMA21")
        else:
            if row["ema_9"] > row["ema_21"]:
                score += 0.10
                reasons.append("continuação altista")
            elif row["ema_9"] < row["ema_21"]:
                score -= 0.10
                reasons.append("continuação baixista")

        recent_high = float(df["high"].iloc[-6:-1].max())
        recent_low = float(df["low"].iloc[-6:-1].min())
        if row["close"] > recent_high:
            score += 0.18
            reasons.append("breakout máxima recente")
        elif row["close"] < recent_low:
            score -= 0.18
            reasons.append("breakdown mínima recente")

        if row["ema_21"] > row["ema_50"]:
            score += 0.14
            reasons.append("tendência maior favorável")
        else:
            score -= 0.14
            reasons.append("tendência maior desfavorável")

        if 52 <= row["rsi_14"] <= 70:
            score += 0.08
            reasons.append("RSI saudável para compra")
        elif 30 <= row["rsi_14"] <= 48:
            score -= 0.04
            reasons.append("RSI sem força compradora")

        if regime == MarketRegime.BREAKOUT:
            score += 0.05
            reasons.append("bônus de breakout")

        signal = Signal.HOLD
        if score >= 0.18:
            signal = Signal.BUY
        elif score <= -0.18:
            signal = Signal.SELL
        confidence = _clip(0.48 + abs(score) / 0.95, 0.0, 1.0)
        return StrategyOutput(self.name, signal, score, confidence, reasons)


# =========================================================
# ENSEMBLE
# =========================================================
class VAIIIxBRHybridEnsemble:
    def __init__(self, config: Optional[HybridConfig] = None):
        self.config = config or HybridConfig()
        self.regime_detector = MarketRegimeDetector()
        self.strategies: Dict[str, BaseStrategy] = {
            "holly_like": HollyLikeStrategy(),
            "quant_like": QuantLikeStrategy(),
            "ea_like": EALikeStrategy(),
        }

    def _dynamic_weights(self, regime: MarketRegime) -> Dict[str, float]:
        weights = {
            "holly_like": self.config.weight_holly_like,
            "quant_like": self.config.weight_quant_like,
            "ea_like": self.config.weight_ea_like,
        }

        if regime == MarketRegime.BREAKOUT:
            weights["holly_like"] += 0.08
            weights["ea_like"] += 0.05
            weights["quant_like"] -= 0.13
        elif regime == MarketRegime.TREND_UP:
            weights["quant_like"] += 0.06
            weights["ea_like"] += 0.03
            weights["holly_like"] -= 0.09
        elif regime == MarketRegime.TREND_DOWN:
            weights["quant_like"] += 0.08
            weights["holly_like"] -= 0.04
            weights["ea_like"] -= 0.04
        elif regime == MarketRegime.MEAN_REVERSION:
            weights["holly_like"] += 0.04
            weights["quant_like"] -= 0.04
        elif regime == MarketRegime.LOW_VOLUME:
            weights["quant_like"] += 0.05
            weights["holly_like"] -= 0.03
            weights["ea_like"] -= 0.02

        total = sum(max(v, 0.01) for v in weights.values())
        return {k: max(v, 0.01) / total for k, v in weights.items()}

    def evaluate(self, raw_df: pd.DataFrame) -> EnsembleDecision:
        validate_input(raw_df, self.config)
        df = FeatureEngine.build(raw_df)
        regime, regime_reasons = self.regime_detector.detect(df)
        weights = self._dynamic_weights(regime)

        outputs: Dict[str, StrategyOutput] = {}
        for name, strategy in self.strategies.items():
            outputs[name] = strategy.evaluate(df, regime)

        final_score = sum(outputs[name].score * weights[name] for name in outputs)
        avg_conf = sum(outputs[name].confidence * weights[name] for name in outputs)
        row = df.iloc[-1]

        reasons = [
            f"regime={regime.value}",
            *regime_reasons,
            *(f"weight_{k}={v:.3f}" for k, v in weights.items()),
            *(f"score_{k}={outputs[k].score:+.3f}" for k in outputs),
            f"score_final={final_score:+.3f}",
            f"confidence={avg_conf:.3f}",
            f"rel_volume={safe_last(df['rel_volume']):.3f}",
            f"rsi_14={safe_last(df['rsi_14']):.2f}",
        ]

        if self.config.use_volume_filter and row["rel_volume"] < self.config.min_relative_volume:
            reasons.append("filtro: volume relativo insuficiente")
            return EnsembleDecision(
                symbol=self.config.symbol,
                regime=regime,
                signal=Signal.HOLD,
                confidence=min(avg_conf, 0.60),
                final_score=final_score,
                dynamic_weights=weights,
                strategy_outputs=outputs,
                reasons=reasons,
            )

        final_signal = Signal.HOLD
        if final_score >= self.config.buy_threshold and avg_conf >= self.config.min_confidence:
            final_signal = Signal.BUY
        elif final_score <= self.config.sell_threshold and avg_conf >= self.config.min_confidence:
            final_signal = Signal.SELL

        # projeto focado em ITUB4 no mercado à vista: não abre short por padrão.
        if final_signal == Signal.SELL and not self.config.allow_short:
            reasons.append("SELL convertido em HOLD: short desabilitado para ITUB4")
            final_signal = Signal.HOLD

        return EnsembleDecision(
            symbol=self.config.symbol,
            regime=regime,
            signal=final_signal,
            confidence=avg_conf,
            final_score=final_score,
            dynamic_weights=weights,
            strategy_outputs=outputs,
            reasons=reasons,
        )


# =========================================================
# BRIDGE WITH MAIN VAIIIxBR
# =========================================================
class VAIIIxBRSignalBridge:
    def __init__(self, config: Optional[HybridConfig] = None):
        self.config = config or HybridConfig()
        self.ensemble = VAIIIxBRHybridEnsemble(self.config)

    def merge_with_vaiiixbr(self, df: pd.DataFrame, vaiiixbr_signal: str, vaiiixbr_confidence: float) -> Dict[str, Any]:
        if not (0.0 <= float(vaiiixbr_confidence) <= 1.0):
            raise ValueError("vaiiixbr_confidence deve estar entre 0 e 1")

        ensemble_decision = self.ensemble.evaluate(df)
        v_signal = str(vaiiixbr_signal).upper().strip()
        if v_signal not in {Signal.BUY.value, Signal.SELL.value, Signal.HOLD.value}:
            raise ValueError("vaiiixbr_signal deve ser BUY, SELL ou HOLD")

        merged_signal = Signal.HOLD.value
        merged_confidence = 0.50
        status = "NEUTRAL"
        reasons = list(ensemble_decision.reasons)

        if v_signal == ensemble_decision.signal.value and v_signal != Signal.HOLD.value:
            merged_signal = v_signal
            merged_confidence = min(0.99, (float(vaiiixbr_confidence) * 0.55) + (ensemble_decision.confidence * 0.45))
            status = "CONFIRMED"
            reasons.append("sinal confirmado entre VAIIIxBR e ensemble")
        elif v_signal == Signal.HOLD.value and ensemble_decision.signal != Signal.HOLD:
            merged_confidence = ensemble_decision.confidence
            status = "WATCHLIST"
            reasons.append("ensemble detectou oportunidade, VAIIIxBR principal ainda neutra")
        elif v_signal != Signal.HOLD.value and ensemble_decision.signal == Signal.HOLD:
            merged_confidence = min(float(vaiiixbr_confidence), 0.60)
            status = "WEAK_MAIN_SIGNAL"
            reasons.append("sinal principal sem confirmação do ensemble")
        elif v_signal != ensemble_decision.signal.value:
            merged_confidence = 0.45
            status = "CONFLICT"
            reasons.append("conflito entre sinais")
        else:
            merged_confidence = min(0.80, (float(vaiiixbr_confidence) + ensemble_decision.confidence) / 2)

        return {
            "symbol": self.config.symbol,
            "regime": ensemble_decision.regime.value,
            "status": status,
            "main_signal_vaiiixbr": v_signal,
            "main_confidence_vaiiixbr": round(float(vaiiixbr_confidence), 4),
            "hybrid_signal": ensemble_decision.signal.value,
            "hybrid_confidence": round(ensemble_decision.confidence, 4),
            "final_signal": merged_signal,
            "final_confidence": round(merged_confidence, 4),
            "hybrid_score": round(ensemble_decision.final_score, 4),
            "weights": {k: round(v, 4) for k, v in ensemble_decision.dynamic_weights.items()},
            "reasons": reasons,
            "strategies": {
                k: {
                    "signal": v.signal.value,
                    "score": round(v.score, 4),
                    "confidence": round(v.confidence, 4),
                    "reasons": v.reasons,
                }
                for k, v in ensemble_decision.strategy_outputs.items()
            },
        }


# =========================================================
# PAPER TRADING
# =========================================================
class VAIIIxBRPaperTrader:
    def __init__(self, config: Optional[HybridConfig] = None):
        self.config = config or HybridConfig()
        self.bridge = VAIIIxBRSignalBridge(self.config)

        self.cash = float(self.config.initial_cash)
        self.position: Optional[Position] = None
        self.realized_pnl = 0.0
        self.equity_peak = float(self.config.initial_cash)
        self.max_drawdown_pct = 0.0
        self.win_trades = 0
        self.loss_trades = 0
        self.trade_count = 0
        self.entry_alerts = 0
        self.guaranteed_alerts = 0
        self.cooldown_remaining = 0
        self.bar_counter = 0

        self.logs_dir = Path(self.config.logs_dir)
        ensure_parent(self.logs_dir / self.config.trades_file)
        ensure_parent(self.logs_dir / self.config.metrics_file)

    # ---------- persistence ----------
    def _write_json_line(self, path: Path, payload: Dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _write_trade_log(self, payload: Dict[str, Any]) -> None:
        self._write_json_line(self.logs_dir / self.config.trades_file, payload)

    def _write_metrics(self) -> None:
        with (self.logs_dir / self.config.metrics_file).open("w", encoding="utf-8") as handle:
            json.dump(self.metrics(), handle, ensure_ascii=False, indent=2)

    # ---------- portfolio ----------
    def _mark_to_market_equity(self, last_price: float) -> float:
        position_value = 0.0
        if self.position:
            position_value = self.position.quantity * last_price
        return self.cash + position_value

    def _update_drawdown(self, last_price: float) -> None:
        equity = self._mark_to_market_equity(last_price)
        self.equity_peak = max(self.equity_peak, equity)
        if self.equity_peak > 0:
            dd = (self.equity_peak - equity) / self.equity_peak
            self.max_drawdown_pct = max(self.max_drawdown_pct, dd)

    def _daily_loss_limit_hit(self, last_price: float) -> bool:
        equity = self._mark_to_market_equity(last_price)
        loss_pct = max(0.0, (self.config.initial_cash - equity) / self.config.initial_cash)
        return loss_pct >= self.config.risk.daily_loss_limit_pct

    def metrics(self) -> Dict[str, Any]:
        total = self.trade_count
        win_rate = (self.win_trades / total) if total else 0.0
        avg_pnl = (self.realized_pnl / total) if total else 0.0
        return {
            "symbol": self.config.symbol,
            "mode": "paper_trading",
            "initial_cash": round(self.config.initial_cash, 2),
            "cash": round(self.cash, 2),
            "position_open": self.position is not None,
            "realized_pnl": round(self.realized_pnl, 4),
            "trade_count": self.trade_count,
            "win_trades": self.win_trades,
            "loss_trades": self.loss_trades,
            "win_rate": round(win_rate, 4),
            "avg_pnl_per_trade": round(avg_pnl, 4),
            "entry_alerts": self.entry_alerts,
            "guaranteed_alerts": self.guaranteed_alerts,
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "cooldown_remaining": self.cooldown_remaining,
        }

    # ---------- execution ----------
    def _apply_slippage(self, price: float, is_buy: bool) -> float:
        factor = 1 + self.config.slippage_pct if is_buy else 1 - self.config.slippage_pct
        return price * factor

    def _build_alert(self, decision: Dict[str, Any]) -> str:
        if decision["final_signal"] in {Signal.BUY.value, Signal.SELL.value} and decision["final_confidence"] >= self.config.risk.guaranteed_entry_confidence:
            self.guaranteed_alerts += 1
            return f"ENTRADA GARANTIDA {decision['final_signal']} | conf={decision['final_confidence']:.2f} | {self.config.symbol}"
        if decision["final_signal"] in {Signal.BUY.value, Signal.SELL.value}:
            self.entry_alerts += 1
            return f"POSSÍVEL ENTRADA {decision['final_signal']} | conf={decision['final_confidence']:.2f} | {self.config.symbol}"
        return f"SEM ENTRADA | status={decision['status']} | {self.config.symbol}"

    def _position_size(self, price: float) -> int:
        spendable_cash = max(0.0, (self.cash - self.config.risk.min_cash_buffer) * self.config.risk.max_position_pct)
        total_cost_per_share = price + (self.config.brokerage_per_order / max(1, int(spendable_cash // max(price, 0.01))))
        qty = int(spendable_cash // total_cost_per_share) if total_cost_per_share > 0 else 0
        return max(0, qty)

    def _open_long(self, price: float, confidence: float, index: Any) -> bool:
        price = self._apply_slippage(price, is_buy=True)
        qty = self._position_size(price)
        if qty <= 0:
            logger.info("Sem caixa suficiente para abrir posição em %s", self.config.symbol)
            return False

        total_cost = qty * price + self.config.brokerage_per_order
        if total_cost > self.cash:
            return False

        self.cash -= total_cost
        self.position = Position(
            symbol=self.config.symbol,
            side="LONG",
            entry_price=price,
            quantity=qty,
            stop_price=price * (1 - self.config.risk.stop_loss_pct),
            take_price=price * (1 + self.config.risk.take_profit_pct),
            trailing_stop_price=price * (1 - self.config.risk.trailing_stop_pct),
            entry_index=index,
            entry_bar=self.bar_counter,
            highest_price=price,
        )
        self._write_trade_log({
            "event": "OPEN_LONG",
            "symbol": self.config.symbol,
            "price": round(price, 4),
            "quantity": qty,
            "confidence": round(confidence, 4),
            "entry_index": str(index),
            "cash_after": round(self.cash, 4),
        })
        return True

    def _update_trailing_stop(self, current_price: float) -> None:
        if not self.position:
            return
        self.position.highest_price = max(self.position.highest_price, current_price)
        dynamic_stop = self.position.highest_price * (1 - self.config.risk.trailing_stop_pct)
        self.position.trailing_stop_price = max(self.position.trailing_stop_price, dynamic_stop)

    def _close_position(self, price: float, reason: str, index: Any) -> None:
        if not self.position:
            return
        exec_price = self._apply_slippage(price, is_buy=False)
        gross = self.position.quantity * exec_price
        self.cash += gross - self.config.brokerage_per_order
        pnl = (exec_price - self.position.entry_price) * self.position.quantity - self.config.brokerage_per_order
        self.realized_pnl += pnl
        self.trade_count += 1
        self.win_trades += int(pnl >= 0)
        self.loss_trades += int(pnl < 0)

        self._write_trade_log({
            "event": "CLOSE_LONG",
            "symbol": self.config.symbol,
            "price": round(exec_price, 4),
            "quantity": self.position.quantity,
            "reason": reason,
            "pnl": round(pnl, 4),
            "exit_index": str(index),
            "cash_after": round(self.cash, 4),
        })
        self.position = None
        self.cooldown_remaining = self.config.risk.cooldown_bars_after_exit
        self._write_metrics()

    # ---------- event loop ----------
    def on_bar(self, df: pd.DataFrame, vaiiixbr_signal: str, vaiiixbr_confidence: float) -> Dict[str, Any]:
        self.bar_counter += 1
        row = df.iloc[-1]
        price = float(row["close"])
        index = df.index[-1]

        decision = self.bridge.merge_with_vaiiixbr(df, vaiiixbr_signal, vaiiixbr_confidence)
        alert = self._build_alert(decision)

        if self.cooldown_remaining > 0:
            self.cooldown_remaining -= 1

        if self.position:
            self._update_trailing_stop(price)
            max_bars_hit = (self.bar_counter - self.position.entry_bar) >= self.config.risk.max_bars_in_trade
            if price <= self.position.stop_price:
                self._close_position(price, "STOP_LOSS", index)
            elif price <= self.position.trailing_stop_price:
                self._close_position(price, "TRAILING_STOP", index)
            elif price >= self.position.take_price:
                self._close_position(price, "TAKE_PROFIT", index)
            elif decision["final_signal"] == Signal.SELL.value and self.config.allow_short:
                self._close_position(price, "SIGNAL_REVERSAL", index)
            elif max_bars_hit:
                self._close_position(price, "TIME_EXIT", index)
        else:
            if self._daily_loss_limit_hit(price):
                alert = f"TRAVA DE RISCO ATIVA | {self.config.symbol}"
            elif self.cooldown_remaining == 0 and decision["final_signal"] == Signal.BUY.value:
                self._open_long(price, decision["final_confidence"], index)

        self._update_drawdown(price)
        snapshot = {
            "alert": alert,
            "decision": decision,
            "position": asdict(self.position) if self.position else None,
            "metrics": self.metrics(),
        }
        logger.info(alert)
        self._write_metrics()
        return snapshot


# =========================================================
# BACKTEST / DIAGNOSTICS
# =========================================================
class VAIIIxBRBacktester:
    def __init__(self, config: Optional[HybridConfig] = None):
        self.config = config or HybridConfig()

    def _default_main_signal(self, df_slice: pd.DataFrame) -> Tuple[str, float]:
        row = FeatureEngine.build(df_slice).iloc[-1]
        bullish = row["ema_9"] > row["ema_21"] and row["close"] > row["vwap_20"]
        bearish = row["ema_9"] < row["ema_21"] and row["close"] < row["vwap_20"]
        if bullish:
            return Signal.BUY.value, 0.68
        if bearish:
            return Signal.SELL.value, 0.68
        return Signal.HOLD.value, 0.55

    def run(self, df: pd.DataFrame, signal_provider: Optional[Any] = None) -> Dict[str, Any]:
        validate_input(df, self.config)
        trader = VAIIIxBRPaperTrader(self.config)
        history: List[Dict[str, Any]] = []

        for end in range(self.config.min_rows, len(df) + 1):
            window = df.iloc[:end].copy()
            if signal_provider is None:
                main_signal, main_conf = self._default_main_signal(window)
            else:
                main_signal, main_conf = signal_provider(window)
            snapshot = trader.on_bar(window, main_signal, float(main_conf))
            history.append({
                "index": str(window.index[-1]),
                "alert": snapshot["alert"],
                "final_signal": snapshot["decision"]["final_signal"],
                "final_confidence": snapshot["decision"]["final_confidence"],
                "cash": snapshot["metrics"]["cash"],
                "realized_pnl": snapshot["metrics"]["realized_pnl"],
            })

        result = {
            "metrics": trader.metrics(),
            "history_tail": history[-10:],
        }
        return result


class VAIIIxBRAuditor:
    @staticmethod
    def audit_code_behavior(df: pd.DataFrame, config: Optional[HybridConfig] = None) -> Dict[str, Any]:
        config = config or HybridConfig()
        issues: List[str] = []
        recommendations: List[str] = []

        try:
            validate_input(df, config)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"falha de validação: {exc}")
            return {"ok": False, "issues": issues, "recommendations": recommendations}

        feat = FeatureEngine.build(df)
        latest = feat.iloc[-1]
        critical_cols = ["ema_9", "ema_21", "ema_50", "rsi_14", "atr_14", "rel_volume", "vwap_20"]
        nan_cols = [col for col in critical_cols if pd.isna(latest[col])]
        if nan_cols:
            issues.append(f"indicadores críticos com NaN: {nan_cols}")

        if not math.isfinite(float(latest["close"])):
            issues.append("close final não finito")

        if float(latest["close"]) < config.min_price:
            issues.append("preço abaixo do mínimo configurado")

        if float(latest["volume"]) == 0:
            recommendations.append("volume final zerado; revisar feed intraday")

        if config.weight_holly_like + config.weight_quant_like + config.weight_ea_like <= 0:
            issues.append("pesos base inválidos")

        if not issues:
            recommendations.append("pipeline validado sem inconsistências críticas")

        return {"ok": len(issues) == 0, "issues": issues, "recommendations": recommendations}


# =========================================================
# SAMPLE DATA / MAIN
# =========================================================
def fake_itub4_df(rows: int = 180) -> pd.DataFrame:
    np.random.seed(42)
    base_price = 30.0
    returns = np.random.normal(0.0007, 0.009, rows)
    close = base_price * (1 + pd.Series(returns)).cumprod()
    df = pd.DataFrame(
        {
            "open": close.shift(1).fillna(close.iloc[0]) * (1 + np.random.normal(0, 0.0015, rows)),
            "high": close * (1 + np.random.uniform(0.001, 0.007, rows)),
            "low": close * (1 - np.random.uniform(0.001, 0.007, rows)),
            "close": close,
            "volume": np.random.randint(500_000, 2_500_000, rows),
            "symbol": "ITUB4",
        }
    )
    df.index = pd.RangeIndex(start=0, stop=len(df), step=1)
    return df


if __name__ == "__main__":
    sample = fake_itub4_df()
    auditor = VAIIIxBRAuditor()
    audit = auditor.audit_code_behavior(sample)
    print("AUDIT:")
    print(json.dumps(audit, ensure_ascii=False, indent=2))

    trader = VAIIIxBRPaperTrader()
    snapshot = trader.on_bar(sample, vaiiixbr_signal="BUY", vaiiixbr_confidence=0.76)
    print("SNAPSHOT:")
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))

    backtester = VAIIIxBRBacktester()
    bt = backtester.run(sample)
    print("BACKTEST:")
    print(json.dumps(bt, ensure_ascii=False, indent=2))
