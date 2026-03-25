from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List


@dataclass
class LearnStats:
    samples: int
    positive_rate: float
    model_version: str
    updated_at: str
    feature_set: List[str]
    thresholds: dict

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def generate_demo_stats() -> LearnStats:
    return LearnStats(
        samples=128,
        positive_rate=0.5469,
        model_version="vaiiixaprende-colab-v1",
        updated_at=datetime.now(timezone.utc).isoformat(),
        feature_set=["retorno", "volume", "news_score", "confidence_hint"],
        thresholds={"buy_confirmed": 0.78, "buy_watchlist": 0.58},
    )


def save_stats(output_dir: str = "artifacts") -> Path:
    path = Path(output_dir)
    path.mkdir(exist_ok=True)
    target = path / "stats.json"
    target.write_text(generate_demo_stats().to_json(), encoding="utf-8")
    return target


if __name__ == "__main__":
    save_stats()
