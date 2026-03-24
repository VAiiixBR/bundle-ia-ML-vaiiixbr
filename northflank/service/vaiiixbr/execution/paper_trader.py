from __future__ import annotations

from typing import Any

import pandas as pd

from vaiiixbr.config import Settings
from vaiiixbr.risk import RiskManager


class PaperTrader:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.risk = RiskManager(settings)
        self.position: dict[str, Any] | None = None
        self.cash = settings.paper_initial_cash
        self.equity = settings.paper_initial_cash
        self.initial_cash = settings.paper_initial_cash

    def _round(self, value: float) -> float:
        return round(float(value), 4)

    def _build_position_snapshot(self, mark_price: float) -> dict[str, Any] | None:
        if self.position is None:
            return None
        quantity = float(self.position["quantity"])
        entry_price = float(self.position["entry"])
        invested_entry = quantity * entry_price
        market_value = quantity * mark_price
        gross_pnl = market_value - invested_entry
        total_costs = float(self.position["entry_cost"]) + (market_value * self.settings.fee_per_trade) + (market_value * self.settings.slippage_per_trade)
        net_pnl = gross_pnl - total_costs
        return {
            "entry_time": self.position["entry_time"],
            "entry_price": self._round(entry_price),
            "stop_price": self._round(float(self.position["stop"])),
            "target_price": self._round(float(self.position["target"])),
            "quantity": self._round(quantity),
            "invested_entry": self._round(invested_entry),
            "market_value": self._round(market_value),
            "gross_pnl": self._round(gross_pnl),
            "net_pnl": self._round(net_pnl),
            "return_pct_asset": self._round(((mark_price / entry_price) - 1) * 100 if entry_price else 0.0),
            "return_pct_on_initial_cash": self._round((net_pnl / self.initial_cash) * 100 if self.initial_cash else 0.0),
            "score": int(self.position.get("score", 0)),
        }

    def _close_position(self, *, timestamp: str, exit_price: float, outcome: str) -> dict[str, Any]:
        assert self.position is not None
        quantity = float(self.position["quantity"])
        entry_price = float(self.position["entry"])
        invested_entry = quantity * entry_price
        exit_value = quantity * exit_price
        gross_pnl = exit_value - invested_entry
        exit_cost = exit_value * self.settings.fee_per_trade + exit_value * self.settings.slippage_per_trade
        total_costs = float(self.position["entry_cost"]) + exit_cost
        net_pnl = gross_pnl - total_costs
        self.cash += net_pnl
        self.equity = self.cash
        trade = {
            "entry_time": self.position["entry_time"],
            "exit_time": timestamp,
            "entry_price": self._round(entry_price),
            "exit_price": self._round(exit_price),
            "stop_price": self._round(float(self.position["stop"])),
            "target_price": self._round(float(self.position["target"])),
            "quantity": self._round(quantity),
            "invested_entry": self._round(invested_entry),
            "exit_value": self._round(exit_value),
            "gross_pnl": self._round(gross_pnl),
            "fees": self._round(total_costs),
            "net_pnl": self._round(net_pnl),
            "pnl": self._round(net_pnl),
            "outcome": outcome,
            "score": int(self.position["score"]),
            "prediction_correct": net_pnl > 0,
            "return_pct_asset": self._round(((exit_price / entry_price) - 1) * 100 if entry_price else 0.0),
            "return_pct_on_initial_cash": self._round((net_pnl / self.initial_cash) * 100 if self.initial_cash else 0.0),
            "capital_after_trade": self._round(self.cash),
        }
        self.position = None
        return trade

    def step(self, prepared: pd.DataFrame, signal: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        last = prepared.iloc[-1]
        timestamp = str(prepared.index[-1])
        event = "aguardando"
        closed_trade = None
        close_price = float(last["close"])

        if self.position is None and signal.get("decision") == "compra":
            plan = self.risk.build_long_plan(close_price, float(last["atr"]), self.cash)
            if plan:
                quantity = float(plan.quantity)
                entry_cost = (quantity * plan.entry * self.settings.fee_per_trade) + (quantity * plan.entry * self.settings.slippage_per_trade)
                self.position = {
                    "entry_time": timestamp,
                    "entry": plan.entry,
                    "stop": plan.stop,
                    "target": plan.target,
                    "quantity": quantity,
                    "score": signal.get("long_score", 0),
                    "entry_cost": entry_cost,
                }
                event = "paper_buy"
        elif self.position is not None:
            low = float(last["low"])
            high = float(last["high"])
            exit_price = None
            outcome = "holding"
            if low <= float(self.position["stop"]):
                exit_price = float(self.position["stop"])
                outcome = "stop"
            elif high >= float(self.position["target"]):
                exit_price = float(self.position["target"])
                outcome = "target"
            elif self.settings.exit_on_signal_loss and signal.get("decision") != "compra":
                exit_price = close_price
                outcome = "signal_loss"

            if exit_price is not None:
                closed_trade = self._close_position(timestamp=timestamp, exit_price=exit_price, outcome=outcome)
                event = f"paper_exit_{outcome}"
            else:
                snapshot = self._build_position_snapshot(close_price)
                self.equity = self.cash + float(snapshot["net_pnl"] if snapshot else 0.0)
                event = "paper_holding"

        position_snapshot = self._build_position_snapshot(close_price)
        state = {
            "paper_event": event,
            "paper_cash": round(self.cash, 2),
            "paper_equity": round(self.equity, 2),
            "paper_in_position": self.position is not None,
            "paper_position": position_snapshot,
            "paper_total_return_pct": self._round(((self.equity / self.initial_cash) - 1) * 100 if self.initial_cash else 0.0),
            "paper_realized_gain": self._round(self.cash - self.initial_cash),
        }
        return state, closed_trade
