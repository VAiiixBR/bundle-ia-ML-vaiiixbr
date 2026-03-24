
from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from fastapi import FastAPI
from pydantic import BaseModel, Field

from vaiiixbr_standard_itub4_market_news_learning import NewsPriceLearningEngine, NewsResearchConfig

APP_NAME = "VAIIIxBR Northflank News Worker"
app = FastAPI(title=APP_NAME, version="3.0.0")


class GitHubRepoSync:
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


ENGINE = NewsPriceLearningEngine(
    NewsResearchConfig(
        symbol="ITUB4",
        storage_dir=os.getenv("VAIII_LOG_DIR", "logs_vaiiixbr"),
    )
)
GITHUB = GitHubRepoSync()


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


class NewsBatchRequest(BaseModel):
    candles: List[Candle] = Field(default_factory=list)
    headlines: List[Headline] = Field(default_factory=list)
    mode: str = "LIVE_NEWS_LEARNING"
    export_daily: bool = False


def candles_to_df(candles: List[Candle]) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame([c.model_dump() for c in candles])
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).set_index("timestamp").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "service": APP_NAME, "github_enabled": GITHUB.enabled}


@app.get("/insight/latest")
def latest() -> Dict[str, Any]:
    return {"ok": True, "insight": ENGINE.latest_insight()}


@app.post("/news/ingest")
def ingest(req: NewsBatchRequest) -> Dict[str, Any]:
    df = candles_to_df(req.candles)
    headlines = [h.model_dump() for h in req.headlines]
    stored = ENGINE.store_headlines(headlines) if headlines else 0
    labeled = ENGINE.update_labels_from_prices(df) if not df.empty else 0

    if req.mode == "OFF_HOURS_RESEARCH":
        insight = ENGINE.run_offhours_cycle(df if not df.empty else pd.DataFrame(columns=["close"]), headlines=[])
    else:
        insight = ENGINE.run_live_cycle(df if not df.empty else pd.DataFrame(columns=["close"]), headlines=[])

    export_result = None
    if req.export_daily and not df.empty:
        day = pd.Timestamp(df.index[-1]).strftime("%Y-%m-%d")
        payload = {
            "date": day,
            "symbol": "ITUB4",
            "stored_headlines": stored,
            "labeled_headlines": labeled,
            "insight": insight,
            "headlines": headlines,
        }
        export_result = GITHUB.put_json(
            f"vaiiixbr/daily/{day}/news_summary.json",
            payload,
            f"VAIIIxBR news summary {day}",
        )

    return {
        "ok": True,
        "stored_headlines": stored,
        "labeled_headlines": labeled,
        "insight": insight,
        "github_export": export_result,
    }
