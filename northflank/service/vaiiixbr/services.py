from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from vaiiixbr.config import Settings
from vaiiixbr.data.brapi_client import BrapiClient
from vaiiixbr.execution.paper_trader import PaperTrader
from vaiiixbr.storage.repository import Repository
from vaiiixbr.strategy.pipeline import TradeAIPipeline


class EngineService:
    def __init__(self, settings: Settings, repository: Repository):
        self.settings = settings
        self.repository = repository
        self.client = BrapiClient(settings)
        self.paper_trader = PaperTrader(settings)
        self.pipeline = TradeAIPipeline(settings, repository.signal_metrics, repository.trade_metrics)

    def tick(self) -> dict[str, Any]:
        market = self.client.get_ohlcv()
        prepared = self.pipeline.prepare(market)
        signal = self.pipeline.latest_signal(prepared)
        paper_state, closed_trade = self.paper_trader.step(prepared, signal)
        signal.update(paper_state)
        self.repository.save_signal(signal)
        if closed_trade:
            self.repository.save_paper_trade(closed_trade)

        paper_position = paper_state.get("paper_position") or {}
        status = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "asset": self.settings.asset,
            "interval": self.settings.interval,
            "signal": signal,
            "pre_analysis": dict(self.pipeline._pre_cache),
            "paper": {
                "cash": round(self.paper_trader.cash, 2),
                "equity": round(self.paper_trader.equity, 2),
                "in_position": self.paper_trader.position is not None,
                "position": paper_position,
                "realized_gain": paper_state.get("paper_realized_gain", 0.0),
                "total_return_pct": paper_state.get("paper_total_return_pct", 0.0),
                "initial_cash": self.paper_trader.initial_cash,
            },
            "metrics": {
                "signals": self.repository.signal_metrics(),
                "trades": self.repository.trade_metrics(),
            },
        }
        self.repository.upsert_status(status)
        return status
