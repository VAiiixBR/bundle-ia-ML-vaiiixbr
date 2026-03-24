
from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from fastapi import FastAPI
from pydantic import BaseModel, Field

from vaiiixbr_standard_itub4_market_news_learning import (
    HybridConfig,
    MarketAwareVAIIIxBRPaperTrader,
    MarketHoursConfig,
    NewsResearchConfig,
)

APP_NAME = "VAIIIxBR Northflank Service"
app = FastAPI(title=APP_NAME, version="3.0.0")


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

    def put_json(self, path: str, data: Dict[str, Any], message: str) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "reason": "github_sync_disabled"}
        current = requests.get(f"{self.base_url}/{path}", headers=self._headers(), timeout=30)
        sha = current.json().get("sha") if current.status_code == 200 else None
        body: Dict[str, Any] = {
            "message": message,
            "branch": self.branch,
            "content": base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")).decode("utf-8"),
        }
        if sha:
            body["sha"] = sha
        r = requests.put(f"{self.base_url}/{path}", headers=self._headers(), json=body, timeout=30)
        r.raise_for_status()
        return {"ok": True, "path": path}


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
    timestamp: str
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


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "service": APP_NAME, "github_enabled": GITHUB.enabled}


@app.get("/status")
def status() -> Dict[str, Any]:
    stats = GITHUB.get_json("vaiiixbr/artifacts/stats.json") if GITHUB.enabled else None
    return {
        "ok": True,
        "symbol": "ITUB4",
        "mode": getattr(TRADER, "last_mode", "UNKNOWN"),
        "metrics": TRADER.metrics(),
        "latest_news_insight": TRADER.research_engine.latest_insight(),
        "colab_artifact_stats": stats,
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
