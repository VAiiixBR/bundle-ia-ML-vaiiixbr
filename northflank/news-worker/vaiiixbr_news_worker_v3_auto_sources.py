from __future__ import annotations

import base64
import html
import json
import os
import re
from datetime import timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote_plus, urljoin, urlparse
from xml.etree import ElementTree as ET

import pandas as pd
import requests
from fastapi import FastAPI
from pydantic import BaseModel, Field

from vaiiixbr_standard_itub4_market_news_learning import NewsPriceLearningEngine, NewsResearchConfig

APP_NAME = "VAIIIxBR Northflank News Worker v3"


class SiteRegistry:
    DEFAULT_SOURCES = [
        {"name": "InfoMoney Feed", "type": "rss", "url": "https://www.infomoney.com.br/feed/", "priority": 1.00},
        {"name": "Money Times Feed", "type": "rss", "url": "https://www.moneytimes.com.br/feed/", "priority": 0.95},
        {"name": "Seu Dinheiro Feed", "type": "rss", "url": "https://www.seudinheiro.com/feed/", "priority": 0.90},
        {"name": "Investing Brasil RSS", "type": "rss", "url": "https://br.investing.com/rss/news_25.rss", "priority": 0.90},
        {"name": "E-Investidor Mercado", "type": "html_list", "url": "https://einvestidor.estadao.com.br/mercado/", "priority": 0.92},
        {"name": "Suno Notícias", "type": "html_list", "url": "https://www.suno.com.br/noticias/", "priority": 0.85},
        {"name": "Bloomberg Línea Ações", "type": "html_list", "url": "https://www.bloomberglinea.com.br/acoes/", "priority": 0.88},
        {"name": "Brazil Journal", "type": "html_list", "url": "https://braziljournal.com/", "priority": 0.84},
        {"name": "Investalk BB Notícias", "type": "html_list", "url": "https://investalk.bb.com.br/noticias/mercado", "priority": 0.84},
        {"name": "Google News ITUB4", "type": "google_news_rss", "query": '("ITUB4" OR "Itaú" OR "Itau Unibanco") (ações OR bolsa OR bancos)', "priority": 1.15},
        {"name": "Google News Bancões Brasil", "type": "google_news_rss", "query": '("Itaú" OR "Banco do Brasil" OR "Bradesco" OR "Caixa" OR "Santander Brasil") (ações OR lucro OR balanço OR bancos)', "priority": 1.00},
        {"name": "Google News Bancos Brasil Global", "type": "google_news_rss", "query": '("Brazil banks" OR "Brazilian banks" OR "Itau" OR "Bradesco" OR "Banco do Brasil" OR "Santander Brasil") (shares OR earnings OR finance)', "priority": 0.82},
    ]

    @classmethod
    def from_env(cls) -> List[Dict[str, Any]]:
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
    PRIMARY_ITAU = ("itub4", "itub3", "itaú", "itau", "itaú unibanco", "itau unibanco")
    TOP5_BANKS = (
        "banco do brasil", "bbas3", "bradesco", "bbdc3", "bbdc4",
        "caixa", "caixa econômica federal", "caixa economica federal",
        "santander", "santander brasil", "sanb11"
    )
    SECONDARY_FINANCIALS = (
        "btg", "btg pactual", "bpac11", "nubank", "nu", "inter", "banco inter",
        "pagbank", "picpay", "safra", "mercado pago", "sicredi", "sicoob"
    )
    SECTOR_TERMS = (
        "bancos", "bancário", "bancario", "crédito", "credito", "inadimplência",
        "inadimplencia", "spread bancário", "spread bancario", "selic", "juros",
        "provisão", "provisao", "margem financeira", "roe", "npl", "pdd",
        "carteira de crédito", "carteira de credito"
    )
    POSITIVE = (
        "alta", "sobe", "subida", "crescimento", "lucro", "recorde", "compra",
        "upgrade", "supera", "dividendo", "eficiência", "eficiencia", "melhora",
        "expansão", "expansao", "forte", "otimista", "margem", "guidance",
        "retorno", "recuperação", "recuperacao", "ganha", "ganhos", "surpreende",
        "resiliente", "positivo"
    )
    NEGATIVE = (
        "queda", "cai", "baixa", "prejuízo", "prejuizo", "risco", "downgrade",
        "multa", "processo", "crise", "fraude", "piora", "rebaixamento",
        "provisão maior", "provisao maior", "calote", "recuo", "fraco",
        "pressão", "pressao", "perda", "alerta", "deterioração", "deterioracao"
    )
    MACRO_POS = ("queda de juros", "selic menor", "redução da inadimplência", "reducao da inadimplencia", "crédito forte", "credito forte", "inflação menor", "inflacao menor")
    MACRO_NEG = ("alta de juros", "selic maior", "crédito fraco", "credito fraco", "inflação maior", "inflacao maior", "piora do crédito", "piora do credito")

    def _tokens(self, text: str) -> List[str]:
        return re.findall(r"[a-zA-ZÀ-ÿ0-9_]+", (text or "").lower())

    def analyze(self, title: str, source: Optional[str] = None, url: Optional[str] = None) -> Dict[str, Any]:
        text = (title or "").lower()
        tokens = self._tokens(text)
        primary_match = any(term in text for term in self.PRIMARY_ITAU)
        top5_match = any(term in text for term in self.TOP5_BANKS)
        secondary_match = any(term in text for term in self.SECONDARY_FINANCIALS)
        sector_match = any(term in text for term in self.SECTOR_TERMS)

        pos = sum(tok in self.POSITIVE for tok in tokens)
        neg = sum(tok in self.NEGATIVE for tok in tokens)

        macro_bias = 0.0
        if any(expr in text for expr in self.MACRO_POS):
            macro_bias += 0.7
        if any(expr in text for expr in self.MACRO_NEG):
            macro_bias -= 0.7

        relevance = 0.0
        if primary_match:
            relevance += 1.40
        if top5_match:
            relevance += 1.00
        if secondary_match:
            relevance += 0.55
        if sector_match:
            relevance += 0.45

        source_bonus = 0.0
        src = (source or "").lower()
        if any(x in src for x in ("infomoney", "money times", "investing", "bloomberg", "reuters", "e-investidor", "investalk", "suno", "brazil journal")):
            source_bonus = 0.08

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
            "asset_direct_match": primary_match,
            "top5_bank_match": top5_match,
            "secondary_financial_match": secondary_match,
            "sector_match": sector_match,
            "relevance_score": round(float(relevance + source_bonus), 4),
            "sentiment_score": round(float(sentiment_score), 4),
            "bias": bias,
            "positive_hits": pos,
            "negative_hits": neg,
        }


class FeedCollector:
    USER_AGENT = "VAIIIxBR-NewsWorker/3.3"

    def __init__(self, sources: Optional[Sequence[Dict[str, Any]]] = None):
        self.sources = list(sources or SiteRegistry.from_env())

    def fetch_all(self, max_items_per_source: int = 20) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for src in self.sources:
            stype = src.get("type")
            if stype == "rss":
                rows.extend(self._fetch_rss(src, max_items=max_items_per_source))
            elif stype == "html_list":
                rows.extend(self._fetch_html_list(src, max_items=max_items_per_source))
            elif stype == "google_news_rss":
                rows.extend(self._fetch_google_news_rss(src, max_items=max_items_per_source))
        return self._dedupe(rows)

    def _fetch_rss(self, source: Dict[str, Any], max_items: int = 20) -> List[Dict[str, Any]]:
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
            pub_date = (item.findtext("pubDate") or item.findtext("{http://www.w3.org/2005/Atom}updated") or item.findtext("updated") or "").strip()
            if title and link:
                out.append({
                    "timestamp": pub_date,
                    "source": source.get("name"),
                    "title": html.unescape(title),
                    "url": link,
                    "source_priority": float(source.get("priority", 1.0)),
                })

        if not out:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in xml.findall(".//atom:entry", ns)[:max_items]:
                title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
                updated = (entry.findtext("atom:updated", default="", namespaces=ns) or "").strip()
                href = None
                for link_el in entry.findall("atom:link", ns):
                    href = link_el.attrib.get("href") or href
                if title and href:
                    out.append({
                        "timestamp": updated,
                        "source": source.get("name"),
                        "title": html.unescape(title),
                        "url": href,
                        "source_priority": float(source.get("priority", 1.0)),
                    })
        return out

    def _fetch_google_news_rss(self, source: Dict[str, Any], max_items: int = 20) -> List[Dict[str, Any]]:
        query = source.get("query", "").strip()
        if not query:
            return []
        url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        return self._fetch_rss({"name": source.get("name", "Google News"), "url": url, "priority": source.get("priority", 1.0)}, max_items=max_items)

    def _fetch_html_list(self, source: Dict[str, Any], max_items: int = 20) -> List[Dict[str, Any]]:
        try:
            r = requests.get(source["url"], headers={"User-Agent": self.USER_AGENT}, timeout=30)
            r.raise_for_status()
            html_text = r.text
        except Exception:
            return []

        href_pat = re.compile(r'<a[^>]+href=["\\\']([^"\\\']+)["\\\'][^>]*>(.*?)</a>', flags=re.IGNORECASE | re.DOTALL)
        out: List[Dict[str, Any]] = []
        seen: set[Tuple[str, str]] = set()
        source_domain = (urlparse(source["url"]).netloc or "").lower()

        for href, inner in href_pat.findall(html_text):
            text = re.sub(r"<[^>]+>", " ", inner)
            text = html.unescape(re.sub(r"\s+", " ", text)).strip()
            href = html.unescape(href.strip())
            if not text or len(text) < 25:
                continue

            abs_url = urljoin(source["url"], href)
            parsed = urlparse(abs_url)
            netloc = (parsed.netloc or "").lower()
            if parsed.scheme not in ("http", "https"):
                continue
            if netloc and not (netloc == source_domain or netloc.endswith(f".{source_domain}") or "google.com" in netloc):
                continue

            key = (text.lower(), abs_url)
            if key in seen:
                continue
            seen.add(key)

            out.append({
                "timestamp": "",
                "source": source.get("name"),
                "title": text,
                "url": abs_url,
                "source_priority": float(source.get("priority", 1.0)),
            })
            if len(out) >= max_items:
                break
        return out

    def _dedupe(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen_titles = set()
        for row in rows:
            title_key = re.sub(r"\s+", " ", (row.get("title") or "").strip().lower())
            if not title_key or title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            out.append(row)
        return out


ENGINE = NewsPriceLearningEngine(NewsResearchConfig(symbol="ITUB4", storage_dir=os.getenv("VAIII_LOG_DIR", "logs_vaiiixbr")))
GITHUB = GitHubRepoSync()
ANALYZER = NewsSemanticAnalyzer()
COLLECTOR = FeedCollector()

app = FastAPI(title=APP_NAME, version="3.3.0")


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
    days_back: int = 10
    include_undated: bool = False


def candles_to_df(candles: List[Candle]) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame([c.model_dump() for c in candles])
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).set_index("timestamp").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def filter_headlines_by_days(rows: List[Dict[str, Any]], days_back: int = 10, include_undated: bool = False) -> List[Dict[str, Any]]:
    if days_back <= 0:
        return list(rows)

    now = pd.Timestamp.utcnow().tz_localize(None)
    cutoff = now - timedelta(days=int(days_back))
    filtered: List[Dict[str, Any]] = []

    for row in rows:
        raw_ts = row.get("timestamp")
        parsed_ts = pd.to_datetime(raw_ts, errors="coerce", utc=True)
        if pd.isna(parsed_ts):
            if include_undated:
                filtered.append(row)
            continue
        normalized = parsed_ts.tz_convert(None)
        if normalized >= cutoff:
            item = dict(row)
            item["timestamp"] = normalized.isoformat()
            filtered.append(item)
    return filtered


def analyze_headlines(rows: List[Dict[str, Any]], keep_only_relevant: bool = True) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for row in rows:
        analysis = ANALYZER.analyze(row.get("title", ""), source=row.get("source"), url=row.get("url"))
        merged = {**row, **analysis}
        merged["relevance_score"] = round(float(merged.get("relevance_score", 0.0)) + float(row.get("source_priority", 0.0)) * 0.05, 4)
        if keep_only_relevant and float(merged.get("relevance_score", 0.0)) < 0.55:
            continue
        enriched.append(merged)

    enriched.sort(
        key=lambda x: (
            float(x.get("asset_direct_match", False)),
            float(x.get("top5_bank_match", False)),
            float(x.get("relevance_score", 0.0)),
            float(abs(x.get("sentiment_score", 0.0))),
        ),
        reverse=True,
    )
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
    data = {"date": day, "symbol": "ITUB4", **payload}
    return GITHUB.put_json(f"vaiiixbr/daily/{day}/news_summary.json", data, f"VAIIIxBR news summary {day}")


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": APP_NAME,
        "github_enabled": GITHUB.enabled,
        "registered_sources": [s.get("name") for s in COLLECTOR.sources],
        "focus_banks": ["Itaú/ITUB4", "Banco do Brasil/BBAS3", "Bradesco/BBDC4", "Caixa", "Santander Brasil/SANB11"],
    }


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
    time_filtered = filter_headlines_by_days(fetched, days_back=req.days_back, include_undated=req.include_undated)
    analyzed = analyze_headlines(time_filtered, keep_only_relevant=req.keep_only_relevant)
    engine_result = run_engine(df, analyzed, req.mode)
    export_result = None
    if req.export_daily:
        export_result = export_daily(df, {
            "auto_collected": True,
            "source_count": len(COLLECTOR.sources),
            "raw_headlines_count": len(fetched),
            "time_filtered_headlines_count": len(time_filtered),
            "filtered_headlines_count": len(analyzed),
            "days_back": req.days_back,
            "include_undated": req.include_undated,
            "headlines": analyzed,
            "insight": engine_result["insight"],
            "stored_headlines": engine_result["stored_headlines"],
            "labeled_headlines": engine_result["labeled_headlines"],
            "sources": COLLECTOR.sources,
        })
    return {
        "ok": True,
        "source_count": len(COLLECTOR.sources),
        "raw_headlines_count": len(fetched),
        "time_filtered_headlines_count": len(time_filtered),
        "filtered_headlines_count": len(analyzed),
        "days_back": req.days_back,
        "include_undated": req.include_undated,
        **engine_result,
        "github_export": export_result,
    }
