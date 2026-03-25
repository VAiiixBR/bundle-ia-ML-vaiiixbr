from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI

try:
    from .news_contract import HeadlineItem, build_snapshot
except ImportError:  # fallback for direct execution in some local setups
    from news_contract import HeadlineItem, build_snapshot


APP_NAME = "VAIIIxBR Newsworker"
DEFAULT_ARTIFACT_DIR = Path("artifacts")
DEFAULT_ARTIFACT_FILE = DEFAULT_ARTIFACT_DIR / "news_snapshot.json"

app = FastAPI(title=APP_NAME, version="1.0.0")


def run_demo(output_dir: Path | str = DEFAULT_ARTIFACT_DIR) -> Path:
    artifact_dir = Path(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
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
    target = artifact_dir / "news_snapshot.json"
    target.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_snapshot(path: Path | str = DEFAULT_ARTIFACT_FILE) -> Dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


@app.get("/health")
def health() -> Dict[str, Any]:
    payload = load_snapshot()
    return {
        "ok": True,
        "service": APP_NAME,
        "snapshot_available": bool(payload),
        "artifact_path": str(DEFAULT_ARTIFACT_FILE),
    }


@app.get("/latest")
def latest() -> Dict[str, Any]:
    payload = load_snapshot()
    return {
        "ok": True,
        "snapshot": payload,
    }


@app.post("/run-demo")
def run_demo_endpoint() -> Dict[str, Any]:
    target = run_demo()
    payload = load_snapshot(target)
    return {
        "ok": True,
        "written_to": str(target),
        "snapshot": payload,
    }


if __name__ == "__main__":
    target = run_demo()
    print(f"snapshot salvo em: {target}")
