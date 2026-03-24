
from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence
from xml.etree import ElementTree as ET

import pandas as pd
import requests
from fastapi import FastAPI
from pydantic import BaseModel, Field

from vaiiixbr_standard_itub4_market_news_learning import NewsPriceLearningEngine, NewsResearchConfig

APP_NAME = "VAIIIxBR Northflank News Worker v3"


class SiteRegistry:
    DEFAULT_SOURCES = [
        {"name": "InfoMoney", "type": "rss", "url": "https://www.infomoney.com.br/feed/"},
        {"name": "MoneyTimes", "type": "rss", "url": "https://www.moneytimes.com.br/feed/"},
        {"name": "Investing Brasil", "type": "rss", "url": "https://br.investing.com/rss/news_25.rss"},
        {"name": "Seu Dinheiro", "type": "rss", "url": "https://www.seudinheiro.com/feed/"},
    ]

    @classmethod
    def from_env(cls) -> List[Dict[str, str]]:
        raw = os.getenv("NEWS_SOURCE_REGISTRY_JSON", "").strip()
        if not raw:
            return list(cls.DEFAULT_SOURCES)
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed:
                return parsed
        except Exception:
            pass
        return list(cls.DEFAULT_SOURCES)


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


class NewsSemanticAnalyzer:
    ITUB4_TERMS = ("itub4", "itau", "itaú", "itaú unibanco", "itau unibanco", "itub")
    POSITIVE = (
        "alta", "sobe", "subida", "crescimento", "lucro", "recorde", "compra",
        "upgrade", "supera", "dividendo", "eficiência", "melhora", "expansão",
        "forte", "otimista", "margem", "guidance", "retorno", "recuperação"
    )
    NEGATIVE = (
        "queda", "cai", "baixa", "prejuízo", "risco", "downgrade", "multa",
        "processo", "crise", "fraude", "inadimplência", "piora", "rebaixamento",
        "provisão", "calote", "recuo", "fraco"
    )
    MACRO_POS = ("queda de juros", "selic menor", "crédito forte", "redução da inadimplência")
    MACRO_NEG = ("alta de juros", "selic maior", "inadimplência maior", "crédito fraco")

    def _tokens(self, text: str) -> List[str]:
        return re.findall(r"[a-zA-ZÀ-ÿ0-9_]+", (text or "").lower())

    def analyze(self, title: str, source: Optional[str] = None, url: Optional[str] = None) -> Dict[str, Any]:
        text = (title or "").lower()
        tokens = self._tokens(text)
        direct_asset = any(term in text for term in self.ITUB4_TERMS)
        pos = sum(tok in self.POSITIVE for tok in tokens)
        neg = sum(tok in self.NEGATIVE for tok in tokens)
        macro_bias = 0.0
        if any(expr in text for expr in self.MACRO_POS):
            macro_bias += 0.7
        if any(expr in text for expr in self.MACRO_NEG):
            macro_bias -= 0.7
        relevance = 1.0 if direct_asset else 0.0
        if any(x in text for x in ("bancos", "bancário", "bancario", "selic", "juros", "crédito", "credito", "inadimplência", "inadimplencia")):
            relevance += 0.45
        sentiment_score = (pos - neg) + macro_bias
        if sentiment_score >= 0.75:
            bias = "UP_BIAS"
        elif sentiment_score <= -0.75:
            bias = "DOWN_BIAS"
        else:
            bias = "NEUTRAL"
        return {
            "title": title,
            "source": source,
            "url": url,
            "asset_direct_match": direct_asset,
            "relevance_score": round(float(relevance), 4),
            "sentiment_score": round(float(sentiment_score), 4),
            "bias": bias,
            "positive_hits": pos,
            "negative_hits": neg,
        }


class FeedCollector:
    USER_AGENT = "VAIIIxBR-NewsWorker/3.0"

    def __init__(self, sources: Optional[Sequence[Dict[str, str]]] = None):
        self.sources = list(sources or SiteRegistry.from_env())

    def fetch_all(self, max_items_per_source: int = 20) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for src in self.sources:
            if src.get("type") != "rss":
                continue
            rows.extend(self._fetch_rss(src, max_items=max_items_per_source))
        return rows

    def _fetch_rss(self, source: Dict[str, str], max_items: int = 20) -> List[Dict[str, Any]]:
        try:
            r = requests.get(source["url"], headers={"User-Agent": self.USER_AGENT}, timeout=30)
            r.raise_for_status()
            xml = ET.fromstring(r.content)
        except Exception:
            return []

        out: List[Dict[str, Any]] = []
        for item in xml.findall(".//item")[:max_items]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or item.findtext("updated") or "").strip()
            out.append({"timestamp": pub_date, "source": source.get("name"), "title": title, "url": link})

        if not out:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in xml.findall(".//atom:entry", ns)[:max_items]:
                title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
                updated = (entry.findtext("atom:updated", default="", namespaces=ns) or "").strip()
                href = None
                for link_el in entry.findall("atom:link", ns):
                    href = link_el.attrib.get("href") or href
                out.append({"timestamp": updated, "source": source.get("name"), "title": title, "url": href})
        return out


ENGINE = NewsPriceLearningEngine(
    NewsResearchConfig(symbol="ITUB4", storage_dir=os.getenv("VAIII_LOG_DIR", "logs_vaiiixbr"))
)
GITHUB = GitHubRepoSync()
ANALYZER = NewsSemanticAnalyzer()
COLLECTOR = FeedCollector()

app = FastAPI(title=APP_NAME, version="3.1.0")


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


class NewsBatchRequest(BaseModel):
    candles: List[Candle] = Field(default_factory=list)
    headlines: List[Headline] = Field(default_factory=list)
    mode: str = "LIVE_NEWS_LEARNING"
    export_daily: bool = False


class AutoCollectRequest(BaseModel):
    candles: List[Candle] = Field(default_factory=list)
    mode: str = "LIVE_NEWS_LEARNING"
    export_daily: bool = False
    max_items_per_source: int = 20
    keep_only_relevant: bool = True


def candles_to_df(candles: List[Candle]) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame([c.model_dump() for c in candles])
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).set_index("timestamp").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def analyze_headlines(rows: List[Dict[str, Any]], keep_only_relevant: bool = True) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for row in rows:
        merged = {**row, **ANALYZER.analyze(row.get("title", ""), source=row.get("source"), url=row.get("url"))}
        if keep_only_relevant and float(merged.get("relevance_score", 0.0)) <= 0:
            continue
        enriched.append(merged)
    return enriched


def run_engine(df: pd.DataFrame, headlines: List[Dict[str, Any]], mode: str) -> Dict[str, Any]:
    stored = ENGINE.store_headlines(headlines) if headlines else 0
    labeled = ENGINE.update_labels_from_prices(df) if not df.empty else 0
    if mode == "OFF_HOURS_RESEARCH":
        insight = ENGINE.run_offhours_cycle(df if not df.empty else pd.DataFrame(columns=["close"]), headlines=[])
    else:
        insight = ENGINE.run_live_cycle(df if not df.empty else pd.DataFrame(columns=["close"]), headlines=[])
    return {"stored_headlines": stored, "labeled_headlines": labeled, "insight": insight}


def export_daily(df: pd.DataFrame, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if df.empty:
        return None
    day = pd.Timestamp(df.index[-1]).strftime("%Y-%m-%d")
    return GITHUB.put_json(
        f"vaiiixbr/daily/{day}/news_summary.json",
        {"date": day, "symbol": "ITUB4", **payload},
        f"VAIIIxBR news summary {day}",
    )


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "service": APP_NAME, "github_enabled": GITHUB.enabled, "registered_sources": [s.get("name") for s in COLLECTOR.sources]}


@app.get("/insight/latest")
def latest() -> Dict[str, Any]:
    return {"ok": True, "insight": ENGINE.latest_insight()}


@app.post("/news/ingest")
def ingest(req: NewsBatchRequest) -> Dict[str, Any]:
    df = candles_to_df(req.candles)
    raw_headlines = [h.model_dump() for h in req.headlines]
    analyzed = analyze_headlines(raw_headlines, keep_only_relevant=False)
    engine_result = run_engine(df, analyzed, req.mode)
    export_result = None
    if req.export_daily:
        export_result = export_daily(df, {
            "raw_headlines_count": len(raw_headlines),
            "filtered_headlines_count": len(analyzed),
            "headlines": analyzed,
            "insight": engine_result["insight"],
            "stored_headlines": engine_result["stored_headlines"],
            "labeled_headlines": engine_result["labeled_headlines"],
        })
    return {"ok": True, "raw_headlines_count": len(raw_headlines), "filtered_headlines_count": len(analyzed), **engine_result, "github_export": export_result}


@app.post("/news/auto-collect")
def auto_collect(req: AutoCollectRequest) -> Dict[str, Any]:
    df = candles_to_df(req.candles)
    fetched = COLLECTOR.fetch_all(max_items_per_source=req.max_items_per_source)
    analyzed = analyze_headlines(fetched, keep_only_relevant=req.keep_only_relevant)
    engine_result = run_engine(df, analyzed, req.mode)
    export_result = None
    if req.export_daily:
        export_result = export_daily(df, {
            "auto_collected": True,
            "source_count": len(COLLECTOR.sources),
            "raw_headlines_count": len(fetched),
            "filtered_headlines_count": len(analyzed),
            "headlines": analyzed,
            "insight": engine_result["insight"],
            "stored_headlines": engine_result["stored_headlines"],
            "labeled_headlines": engine_result["labeled_headlines"],
            "sources": COLLECTOR.sources,
        })
    return {"ok": True, "source_count": len(COLLECTOR.sources), "raw_headlines_count": len(fetched), "filtered_headlines_count": len(analyzed), **engine_result, "github_export": export_result}
