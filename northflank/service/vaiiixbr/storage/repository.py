from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from vaiiixbr.storage.sqlite_store import SQLiteStore


class Repository:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def upsert_status(self, payload: dict[str, Any]) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload, ensure_ascii=False)
        with self.store.connect() as conn:
            conn.execute(
                """
                INSERT INTO engine_status (id, updated_at, payload_json)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, payload_json=excluded.payload_json
                """,
                (updated_at, payload_json),
            )

    def save_signal(self, signal: dict[str, Any]) -> None:
        with self.store.connect() as conn:
            conn.execute(
                "INSERT INTO signals (timestamp, asset, decision, decision_gate, payload_json) VALUES (?, ?, ?, ?, ?)",
                (
                    str(signal.get("timestamp", "")),
                    str(signal.get("asset", "")),
                    str(signal.get("decision", "neutro")),
                    str(signal.get("decision_gate", "desconhecido")),
                    json.dumps(signal, ensure_ascii=False),
                ),
            )

    def save_paper_trade(self, trade: dict[str, Any]) -> None:
        with self.store.connect() as conn:
            conn.execute(
                "INSERT INTO paper_trades (entry_time, exit_time, outcome, payload_json) VALUES (?, ?, ?, ?)",
                (
                    str(trade.get("entry_time", "")),
                    trade.get("exit_time"),
                    trade.get("outcome"),
                    json.dumps(trade, ensure_ascii=False),
                ),
            )

    def get_status(self) -> dict[str, Any]:
        with self.store.connect() as conn:
            row = conn.execute("SELECT payload_json FROM engine_status WHERE id = 1").fetchone()
        if not row:
            return {}
        return json.loads(row["payload_json"])

    def list_signals(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.store.connect() as conn:
            rows = conn.execute("SELECT payload_json FROM signals ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def list_paper_trades(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.store.connect() as conn:
            rows = conn.execute("SELECT payload_json FROM paper_trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def trade_metrics(self) -> dict[str, Any]:
        trades = self.list_paper_trades(limit=500)
        if not trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "prediction_accuracy": 0.0,
                "avg_pnl": 0.0,
                "total_net_pnl": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0,
                "avg_return_pct_asset": 0.0,
                "avg_return_pct_on_initial_cash": 0.0,
                "total_return_pct_on_initial_cash": 0.0,
                "avg_score": 0.0,
                "avg_score_wins": 0.0,
                "avg_score_losses": 0.0,
                "high_confidence_trade_rate": 0.0,
            }
        pnls = [float(t.get("net_pnl", t.get("pnl", 0.0)) or 0.0) for t in trades]
        scores = [float(t.get("score", 0.0) or 0.0) for t in trades]
        asset_returns = [float(t.get("return_pct_asset", 0.0) or 0.0) for t in trades]
        capital_returns = [float(t.get("return_pct_on_initial_cash", 0.0) or 0.0) for t in trades]
        wins_idx = [i for i, p in enumerate(pnls) if p > 0]
        losses_idx = [i for i, p in enumerate(pnls) if p <= 0]
        avg = lambda xs: sum(xs) / len(xs) if xs else 0.0
        prediction_correct = sum(1 for t in trades if bool(t.get("prediction_correct")))
        return {
            "total_trades": len(trades),
            "win_rate": (len(wins_idx) / len(trades)) * 100,
            "prediction_accuracy": (prediction_correct / len(trades)) * 100,
            "avg_pnl": avg(pnls),
            "total_net_pnl": sum(pnls),
            "best_trade": max(pnls),
            "worst_trade": min(pnls),
            "avg_return_pct_asset": avg(asset_returns),
            "avg_return_pct_on_initial_cash": avg(capital_returns),
            "total_return_pct_on_initial_cash": sum(capital_returns),
            "avg_score": avg(scores),
            "avg_score_wins": avg([scores[i] for i in wins_idx]),
            "avg_score_losses": avg([scores[i] for i in losses_idx]),
            "high_confidence_trade_rate": (sum(1 for s in scores if s >= 80) / len(scores)) * 100,
        }

    def signal_metrics(self) -> dict[str, Any]:
        signals = self.list_signals(limit=500)
        if not signals:
            return {
                "total_signals": 0,
                "buy_signals": 0,
                "sell_signals": 0,
                "neutral_signals": 0,
                "avg_long_score": 0.0,
                "avg_short_score": 0.0,
                "max_long_score": 0.0,
                "min_long_score": 0.0,
                "high_confidence_signals": 0,
            }
        long_scores = [float(s.get("long_score", 0.0) or 0.0) for s in signals]
        short_scores = [float(s.get("short_score", 0.0) or 0.0) for s in signals]
        avg = lambda xs: sum(xs) / len(xs) if xs else 0.0
        return {
            "total_signals": len(signals),
            "buy_signals": sum(1 for s in signals if s.get("decision") == "compra"),
            "sell_signals": sum(1 for s in signals if s.get("decision") == "venda"),
            "neutral_signals": sum(1 for s in signals if s.get("decision") == "neutro"),
            "avg_long_score": avg(long_scores),
            "avg_short_score": avg(short_scores),
            "max_long_score": max(long_scores),
            "min_long_score": min(long_scores),
            "high_confidence_signals": sum(1 for s in signals if float(s.get("long_score", 0.0) or 0.0) >= 80),
        }
