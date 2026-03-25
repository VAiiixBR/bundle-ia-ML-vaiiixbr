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

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - opcional em produção
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

try:
    from .contract import build_audit_payload, build_dashboard_state, normalize_trade_result
except ImportError:  # execução direta: uvicorn app:app --reload
    from contract import build_audit_payload, build_dashboard_state, normalize_trade_result

APP_NAME = "VAIIIxBR Northflank Service"
BASE_DIR = Path(__file__).resolve().parent
DASHBOARD_PATH = BASE_DIR / "dashboard.html"
DEFAULT_STATS_PATH = "vaiiixbr/artifacts/stats.json"

app = FastAPI(title=APP_NAME, version="4.1.0")


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

        response = requests.get(
            f"{self.base_url}/{path}",
            headers=self._headers(),
            params={"ref": self.branch},
            timeout=30,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        content = base64.b64decode(payload["content"]).decode("utf-8")
        return json.loads(content)


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


class FileBackedResearchEngine:
    def __init__(self, snapshot_path: str | Path | None = None) -> None:
        configured = snapshot_path or os.getenv("NEWS_SNAPSHOT_PATH", "artifacts/news_snapshot.json")
        self.snapshot_path = Path(configured)

    def latest_insight(self) -> Dict[str, Any]:
        if self.snapshot_path.exists():
            try:
                payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    return payload
            except Exception:
                pass
        return {
            "timestamp": "--",
            "price_bias": "NEUTRAL",
            "headline_count": 0,
            "summary": "Sem snapshot de notícias carregado.",
            "news_price_score": 0.0,
            "confidence_adjustment_hint": 0.0,
            "last_price": 0.0,
            "reference_entry_price": 0.0,
            "reference_stop_price": 0.0,
            "reference_take_price": 0.0,
            "reference_trailing_stop_price": 0.0,
            "learned_tokens": 0,
            "status": "UNKNOWN",
            "headlines": [],
        }


class DummyTrader:
    def __init__(self) -> None:
        self.research_engine = FileBackedResearchEngine()
        self.last_mode = "UNINITIALIZED"

    def metrics(self) -> Dict[str, Any]:
        return {
            "symbol": "ITUB4",
            "mode": "paper_trading",
            "initial_cash": 50.0,
            "cash": 50.0,
            "position_open": False,
            "realized_pnl": 0.0,
            "trade_count": 0,
            "win_trades": 0,
            "loss_trades": 0,
            "win_rate": 0.0,
            "avg_pnl_per_trade": 0.0,
            "entry_alerts": 0,
            "guaranteed_alerts": 0,
            "max_drawdown_pct": 0.0,
            "cooldown_remaining": 0,
        }

    def on_bar(
        self,
        df: pd.DataFrame,
        vaiiixbr_signal: str,
        vaiiixbr_confidence: float,
        headlines: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        last_price = float(df["close"].iloc[-1])
        status = "WATCHLIST" if vaiiixbr_signal.upper() == "BUY" else "NEUTRAL"
        return {
            "symbol": "ITUB4",
            "timestamp": str(df.index[-1]),
            "last_price": last_price,
            "entry_price": last_price,
            "stop_price": max(last_price - 0.5, 0.0),
            "take_price": last_price + 1.0,
            "trailing_stop_price": max(last_price - 0.25, 0.0),
            "decision": {
                "status": status,
                "final_signal": vaiiixbr_signal.upper(),
                "final_confidence": float(vaiiixbr_confidence),
                "hybrid_score": 0.0,
                "regime": "PAPER",
                "main_signal_vaiiixbr": vaiiixbr_signal.upper(),
                "main_confidence_vaiiixbr": float(vaiiixbr_confidence),
                "hybrid_signal": "HOLD",
                "hybrid_confidence": 0.0,
                "strategies": {"headline_count": len(headlines)},
                "reasons": ["dummy trader ativo para patch inicial"],
            },
            "metrics": self.metrics(),
        }


TRADER = DummyTrader()
GITHUB = GitHubArtifactsClient()


def _build_status_payload() -> Dict[str, Any]:
    stats = GITHUB.get_json(DEFAULT_STATS_PATH) if GITHUB.enabled else None
    latest_news = TRADER.research_engine.latest_insight() or {}
    metrics = TRADER.metrics() or {}

    normalized = normalize_trade_result(
        {
            "symbol": "ITUB4",
            "timestamp": latest_news.get("timestamp"),
            "last_price": latest_news.get("last_price", 0.0),
            "entry_price": latest_news.get("reference_entry_price", 0.0),
            "stop_price": latest_news.get("reference_stop_price", 0.0),
            "take_price": latest_news.get("reference_take_price", 0.0),
            "trailing_stop_price": latest_news.get("reference_trailing_stop_price", 0.0),
            "decision": {
                "status": latest_news.get("status", "UNKNOWN"),
                "final_signal": (
                    "BUY"
                    if latest_news.get("price_bias") == "UP_BIAS"
                    else "SELL"
                    if latest_news.get("price_bias") == "DOWN_BIAS"
                    else "HOLD"
                ),
                "final_confidence": latest_news.get("confidence_adjustment_hint", 0.0),
                "hybrid_score": latest_news.get("news_price_score", 0.0),
                "regime": getattr(TRADER, "last_mode", "UNKNOWN"),
                "main_signal_vaiiixbr": "HOLD",
                "main_confidence_vaiiixbr": 0.0,
                "hybrid_signal": "HOLD",
                "hybrid_confidence": 0.0,
                "strategies": {},
                "reasons": [],
            },
            "metrics": metrics,
        },
        latest_news=latest_news,
        stats=stats or {},
    )

    return {
        "ok": True,
        "symbol": "ITUB4",
        "mode": getattr(TRADER, "last_mode", "UNKNOWN"),
        "metrics": metrics,
        "latest_news_insight": latest_news,
        "colab_artifact_stats": stats,
        "audit": build_audit_payload(normalized),
        "dashboard_state": build_dashboard_state(normalized),
    }


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_PATH.read_text(encoding="utf-8"))


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": APP_NAME,
        "github_enabled": GITHUB.enabled,
        "mode": getattr(TRADER, "last_mode", "UNKNOWN"),
    }


@app.get("/status")
def status() -> Dict[str, Any]:
    return _build_status_payload()


@app.get("/audit")
def audit() -> Dict[str, Any]:
    payload = _build_status_payload()
    return {"ok": payload["ok"], "audit": payload["audit"]}


@app.post("/decision")
def decision(req: DecisionRequest) -> Dict[str, Any]:
    df = candles_to_df(req.candles)
    raw_result = TRADER.on_bar(
        df=df,
        vaiiixbr_signal=req.vaiiixbr_signal,
        vaiiixbr_confidence=req.vaiiixbr_confidence,
        headlines=[h.model_dump() for h in req.headlines],
    )
    stats = GITHUB.get_json(DEFAULT_STATS_PATH) if GITHUB.enabled else None
    normalized = normalize_trade_result(
        raw_result,
        latest_news=TRADER.research_engine.latest_insight(),
        stats=stats or {},
    )
    normalized["audit"] = build_audit_payload(normalized)
    normalized["dashboard_state"] = build_dashboard_state(normalized)
    return normalized
