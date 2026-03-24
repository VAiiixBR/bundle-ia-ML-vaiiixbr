from __future__ import annotations

from dataclasses import dataclass

from vaiiixbr.config import Settings


@dataclass(slots=True)
class PositionPlan:
    entry: float
    stop: float
    target: float
    quantity: float
    risk_amount: float


class RiskManager:
    def __init__(self, settings: Settings):
        self.settings = settings

    def build_long_plan(self, entry_price: float, atr_value: float, cash: float) -> PositionPlan | None:
        if entry_price <= 0 or atr_value <= 0 or cash <= 0:
            return None
        stop = entry_price - (atr_value * self.settings.atr_stop_multiplier)
        target = entry_price + (atr_value * self.settings.atr_target_multiplier)
        if stop <= 0 or target <= entry_price:
            return None
        risk_amount = cash * self.settings.risk_per_trade
        quantity = cash / entry_price
        return PositionPlan(entry=entry_price, stop=stop, target=target, quantity=quantity, risk_amount=risk_amount)
