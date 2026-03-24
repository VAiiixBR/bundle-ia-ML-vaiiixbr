from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from vaiiixbr_standard_itub4_market_news_learning import (
    HybridConfig,
    MarketAwareVAIIIxBRPaperTrader,
    MarketHoursConfig,
    NewsResearchConfig,
)

APP_NAME = "VAIIIxBR Northflank Service"
BASE_DIR = Path(__file__).resolve().parent
DASHBOARD_PATH = BASE_DIR / "dashboard.html"

app = FastAPI(title=APP_NAME, version="3.3.0")


class GitHubArtifactsClient:
    def __init__(self) -> None:
        self.owner = os.getenv("GITHUB_REPO_OWNER", "")
        self.repo = os.getenv("GITHUB_REPO_NAME", "")
        self.branch = os.getenv("GITHUB_REPO_BRANCH", "main")
        self.token = os.getenv("GITHUB_TOKEN", "")
        self.enabled = all([self.owner, self.repo, self.token])
        self.base_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/contents"

    def _headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get_json(self, path: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        r = requests.get(f"{self.base_url}/{path}", headers=self._headers(), timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        payload = r.json()
        content = base64.b64decode(payload["content"]).decode("utf-8")
        return json.loads(content)


TRADER = MarketAwareVAIIIxBRPaperTrader(
    config=HybridConfig(symbol="ITUB4"),
    market_hours=MarketHoursConfig(
        allow_after_market=os.getenv("ALLOW_AFTER_MARKET", "false").lower() == "true"
    ),
    news_research=NewsResearchConfig(
        symbol="ITUB4",
        storage_dir=os.getenv("VAIII_LOG_DIR", "logs_vaiiixbr"),
    ),
)
GITHUB = GitHubArtifactsClient()


class Candle(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class Headline(BaseModel):
    timestamp: Optional[str] = None
    source: Optional[str] = None
    title: str
    url: Optional[str] = None


class DecisionRequest(BaseModel):
    candles: List[Candle] = Field(min_length=80)
    vaiiixbr_signal: str
    vaiiixbr_confidence: float
    headlines: List[Headline] = Field(default_factory=list)


def candles_to_df(candles: List[Candle]) -> pd.DataFrame:
    df = pd.DataFrame([c.model_dump() for c in candles])
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).set_index("timestamp").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_PATH.read_text(encoding="utf-8"))


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "service": APP_NAME, "github_enabled": GITHUB.enabled}


@app.get("/status")
def status() -> Dict[str, Any]:
    stats = GITHUB.get_json("vaiiixbr/artifacts/stats.json") if GITHUB.enabled else None
    latest_news = TRADER.research_engine.latest_insight()
    action = latest_news.get("price_bias", "NEUTRAL")
    if action == "UP_BIAS":
        action_display = "COMPRA"
    elif action == "DOWN_BIAS":
        action_display = "VENDA"
    else:
        action_display = "NEUTRO"

    metrics = TRADER.metrics()

    return {
        "ok": True,
        "symbol": "ITUB4",
        "mode": getattr(TRADER, "last_mode", "UNKNOWN"),
        "metrics": metrics,
        "latest_news_insight": latest_news,
        "colab_artifact_stats": stats,
        "dashboard_state": {
            "action": action_display,
            "raw_action": action,
            "confidence_hint": latest_news.get("confidence_adjustment_hint", 0.0),
            "news_score": latest_news.get("news_price_score", 0.0),
            "status": latest_news.get("status", "UNKNOWN"),
            "headline_count": latest_news.get("headline_count", 0),
            "summary": latest_news.get("summary", ""),
            "learned_tokens": latest_news.get("learned_tokens", 0),
            "mode": getattr(TRADER, "last_mode", "UNKNOWN"),
            "model_samples": (stats or {}).get("samples", 0) if isinstance(stats, dict) else 0,
            "positive_rate": (stats or {}).get("positive_rate", 0.0) if isinstance(stats, dict) else 0.0,
            "news_bias": latest_news.get("price_bias", "NEUTRAL"),
        }
    }


@app.post("/decision")
def decision(req: DecisionRequest) -> Dict[str, Any]:
    df = candles_to_df(req.candles)
    headlines = [h.model_dump() for h in req.headlines]
    result = TRADER.on_bar(
        df=df,
        vaiiixbr_signal=req.vaiiixbr_signal,
        vaiiixbr_confidence=req.vaiiixbr_confidence,
        headlines=headlines,
    )
    stats = GITHUB.get_json("vaiiixbr/artifacts/stats.json") if GITHUB.enabled else None
    if stats:
        result["colab_artifact_stats"] = stats
    return result
