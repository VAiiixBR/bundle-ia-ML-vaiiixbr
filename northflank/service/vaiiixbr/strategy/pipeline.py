from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from vaiiixbr.config import Settings
from vaiiixbr.features import FeatureEngineer
from vaiiixbr.reporting import build_backtest_report
from vaiiixbr.risk import RiskManager
from vaiiixbr.scoring import EntryScorer
from vaiiixbr.strategy.pre_analysis import build_pre_analysis


@dataclass(slots=True)
class BacktestTrade:
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    quantity: float
    pnl: float
    outcome: str
    score: int
    reasons: str


class TradeAIPipeline:
    def __init__(self, settings: Settings, signal_metrics_provider, trade_metrics_provider):
        self.settings = settings
        self.features = FeatureEngineer(settings)
        self.scorer = EntryScorer(settings)
        self.risk = RiskManager(settings)
        self.signal_metrics_provider = signal_metrics_provider
        self.trade_metrics_provider = trade_metrics_provider
        self._last_signal_timestamp: str | None = None
        self._pre_cache: dict[str, Any] = {}

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        data = self.features.transform(df)
        data = self.scorer.apply(data)
        data["strong_volume"] = data["volume_ratio"] >= self.settings.min_volume_ratio_for_entry
        data["rsi_trade_zone_long"] = data["rsi"].between(self.settings.min_rsi_long, self.settings.max_rsi_long, inclusive="both")
        data["long_signal"] = data["long_score"] >= self.settings.min_score_long
        if self.settings.require_breakout_confirmation:
            data["long_signal"] = data["long_signal"] & data["break_recent_high"]
        data["long_signal"] = data["long_signal"] & data["strong_volume"] & data["rsi_trade_zone_long"]

        pre = build_pre_analysis(data, self.signal_metrics_provider(), self.trade_metrics_provider(), self.settings)
        self._pre_cache = pre
        data["long_signal"] = data["long_signal"] & (data["long_score"] >= float(pre["recommended_min_score"]))
        return data

    def latest_signal(self, prepared: pd.DataFrame) -> dict[str, Any]:
        last = prepared.iloc[-1]
        current_timestamp = str(prepared.index[-1])
        gate = self._gate_signal(prepared)
        decision = "compra" if bool(last.get("long_signal", False)) else "neutro"
        if self._last_signal_timestamp == current_timestamp:
            decision = "neutro"
        if gate != "liberado":
            decision = "neutro"
        if decision == "compra":
            self._last_signal_timestamp = current_timestamp
        return {
            "timestamp": current_timestamp,
            "asset": self.settings.asset,
            "decision": decision,
            "decision_gate": gate,
            "pre_analysis_mode": str(self._pre_cache.get("operation_mode", "normal")),
            "pre_previous_day_label": str(self._pre_cache.get("previous_day_label", "indefinido")),
            "pre_recommended_min_score": float(self._pre_cache.get("recommended_min_score", self.settings.high_confidence_score)),
            "close": float(last["close"]),
            "long_score": int(last.get("long_score", 0)),
            "long_reasons": str(last.get("long_reasons", "")),
            "trend_up": bool(last.get("trend_up", False)),
            "rsi": float(last["rsi"]) if pd.notna(last["rsi"]) else None,
            "atr": float(last["atr"]) if pd.notna(last["atr"]) else None,
            "volume_ratio": float(last["volume_ratio"]) if pd.notna(last["volume_ratio"]) else None,
            "entry_quality": str(last.get("entry_quality", "normal")),
        }

    def _gate_signal(self, prepared: pd.DataFrame) -> str:
        trade_metrics = self.trade_metrics_provider()
        total_trades = int(trade_metrics.get("total_trades", 0) or 0)
        win_rate = float(trade_metrics.get("win_rate", 0.0) or 0.0)
        avg_score_wins = float(trade_metrics.get("avg_score_wins", 0.0) or 0.0)
        current_score = float(prepared.iloc[-1].get("long_score", 0) or 0)
        mode = str(self._pre_cache.get("operation_mode", "normal"))

        if mode == "defensivo" and current_score < 85:
            return "bloqueado_modo_defensivo"
        if total_trades < 20:
            return "liberado"
        if win_rate < 55.0:
            return "bloqueado_win_rate_baixo"
        if avg_score_wins > 0 and current_score < avg_score_wins:
            return "bloqueado_score_abaixo_media_wins"
        return "liberado"

    def backtest(self, prepared: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
        trades: list[BacktestTrade] = []
        equity_curve: list[dict[str, float]] = []
        cash = self.settings.paper_initial_cash
        position = None
        for idx in range(len(prepared)):
            row = prepared.iloc[idx]
            ts = str(prepared.index[idx])
            if position is None and bool(row.get("long_signal", False)):
                plan = self.risk.build_long_plan(float(row["close"]), float(row["atr"]), cash)
                if plan:
                    position = {"entry_time": ts, "plan": plan, "score": int(row["long_score"]), "reasons": str(row["long_reasons"])}
            elif position is not None:
                plan = position["plan"]
                stop_hit = float(row["low"]) <= plan.stop
                target_hit = float(row["high"]) >= plan.target
                if stop_hit or target_hit:
                    exit_price = plan.stop if stop_hit else plan.target
                    pnl = (exit_price - plan.entry) * plan.quantity
                    cash += pnl
                    trades.append(
                        BacktestTrade(
                            entry_time=position["entry_time"],
                            exit_time=ts,
                            entry_price=plan.entry,
                            exit_price=exit_price,
                            stop_price=plan.stop,
                            target_price=plan.target,
                            quantity=plan.quantity,
                            pnl=pnl,
                            outcome="stop" if stop_hit else "target",
                            score=position["score"],
                            reasons=position["reasons"],
                        )
                    )
                    position = None
            equity_curve.append({"timestamp": ts, "equity": cash})

        trades_df = pd.DataFrame([asdict(t) for t in trades])
        equity_df = pd.DataFrame(equity_curve)
        report = build_backtest_report(trades_df, equity_df.rename(columns={"timestamp": "time"}), self.settings.paper_initial_cash)
        return trades_df, equity_df, report
