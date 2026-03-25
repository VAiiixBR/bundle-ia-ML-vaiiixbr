from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import List


@dataclass
class HeadlineItem:
    title: str
    source: str = "unknown"
    timestamp: str = ""
    url: str = ""


@dataclass
class NewsSnapshot:
    symbol: str
    timestamp: str
    headline_count: int
    summary: str
    price_bias: str
    news_price_score: float
    confidence_adjustment_hint: float
    last_price: float
    reference_entry_price: float
    reference_stop_price: float
    reference_take_price: float
    reference_trailing_stop_price: float
    headlines: List[dict]

    def to_dict(self) -> dict:
        return asdict(self)


def build_snapshot(
    symbol: str,
    headlines: List[HeadlineItem],
    summary: str,
    price_bias: str,
    news_price_score: float,
    confidence_hint: float,
    last_price: float,
) -> NewsSnapshot:
    entry_price = float(last_price)
    stop_price = max(entry_price - 0.5, 0.0)
    take_price = entry_price + 1.0
    trailing = max(entry_price - 0.25, 0.0)
    return NewsSnapshot(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc).isoformat(),
        headline_count=len(headlines),
        summary=summary,
        price_bias=price_bias,
        news_price_score=float(news_price_score),
        confidence_adjustment_hint=float(confidence_hint),
        last_price=entry_price,
        reference_entry_price=entry_price,
        reference_stop_price=stop_price,
        reference_take_price=take_price,
        reference_trailing_stop_price=trailing,
        headlines=[asdict(item) for item in headlines],
    )
