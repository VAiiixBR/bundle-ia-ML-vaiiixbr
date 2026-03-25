from __future__ import annotations

import json
from pathlib import Path

from .news_contract import HeadlineItem, build_snapshot

def run_demo() -> None:
    artifact_dir = Path("artifacts")
    artifact_dir.mkdir(exist_ok=True)
    headlines = [
        HeadlineItem(title="ITUB4 mantém atenção do mercado", source="demo", timestamp="--", url=""),
        HeadlineItem(title="Fluxo segue neutro com leve viés positivo", source="demo", timestamp="--", url=""),
    ]
    snapshot = build_snapshot(
        symbol="ITUB4",
        headlines=headlines,
        summary="Resumo de demonstração para validar integração com o VAIIIxBR.",
        price_bias="UP_BIAS",
        news_price_score=0.18,
        confidence_hint=0.07,
        last_price=31.45,
    )
    (artifact_dir / "news_snapshot.json").write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    run_demo()
