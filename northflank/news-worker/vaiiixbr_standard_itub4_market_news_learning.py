
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Sequence
import hashlib
import json
import logging
from pathlib import Path
import math
import re

import numpy as np
import pandas as pd

from vaiiixbr_standard_itub4 import (
    HybridConfig,
    VAIIIxBRPaperTrader as BaseVAIIIxBRPaperTrader,
)

logger = logging.getLogger("VAIIIxBR.MarketAwareNewsLearning")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


@dataclass
class MarketHoursConfig:
    timezone: str = "America/Sao_Paulo"
    trade_start: str = "10:00"
    trade_end: str = "17:00"
    allow_after_market: bool = False
    after_market_start: str = "17:40"
    after_market_end: str = "18:10"
    enabled_weekdays: Sequence[int] = field(default_factory=lambda: (0, 1, 2, 3, 4))
    holiday_dates: Sequence[str] = field(default_factory=lambda: (
        "2026-01-01", "2026-02-16", "2026-02-17", "2026-04-03",
        "2026-04-21", "2026-05-01", "2026-06-04", "2026-09-07",
        "2026-10-12", "2026-11-02", "2026-11-15", "2026-11-20",
        "2026-12-25",
    ))

    def _parse(self, hhmm: str) -> time:
        h, m = hhmm.split(":")
        return time(int(h), int(m))

    @property
    def trade_start_time(self) -> time:
        return self._parse(self.trade_start)

    @property
    def trade_end_time(self) -> time:
        return self._parse(self.trade_end)

    @property
    def after_market_start_time(self) -> time:
        return self._parse(self.after_market_start)

    @property
    def after_market_end_time(self) -> time:
        return self._parse(self.after_market_end)


class B3MarketClock:
    def __init__(self, config: Optional[MarketHoursConfig] = None):
        self.config = config or MarketHoursConfig()
        self.tz = ZoneInfo(self.config.timezone)
        self.holidays = {str(x) for x in self.config.holiday_dates}

    def _normalize_timestamp(self, ts: Optional[pd.Timestamp]) -> pd.Timestamp:
        if ts is None:
            ts = pd.Timestamp.now(tz=self.tz)
        else:
            ts = pd.Timestamp(ts)
            if ts.tzinfo is None:
                ts = ts.tz_localize(self.tz)
            else:
                ts = ts.tz_convert(self.tz)
        return ts

    def is_business_day(self, ts: Optional[pd.Timestamp]) -> bool:
        ts = self._normalize_timestamp(ts)
        return ts.weekday() in self.config.enabled_weekdays and ts.strftime("%Y-%m-%d") not in self.holidays

    def is_open(self, ts: Optional[pd.Timestamp]) -> bool:
        ts = self._normalize_timestamp(ts)
        if not self.is_business_day(ts):
            return False
        current = ts.timetz().replace(tzinfo=None)
        if self.config.trade_start_time <= current <= self.config.trade_end_time:
            return True
        if self.config.allow_after_market and self.config.after_market_start_time <= current <= self.config.after_market_end_time:
            return True
        return False

    def current_session_label(self, ts: Optional[pd.Timestamp]) -> str:
        ts = self._normalize_timestamp(ts)
        if not self.is_business_day(ts):
            return "B3_CLOSED"
        current = ts.timetz().replace(tzinfo=None)
        if current < self.config.trade_start_time:
            return "PRE_MARKET"
        if self.config.trade_start_time <= current <= self.config.trade_end_time:
            return "REGULAR"
        if self.config.allow_after_market and self.config.after_market_start_time <= current <= self.config.after_market_end_time:
            return "AFTER_MARKET"
        return "POST_MARKET"

    def next_open(self, ts: Optional[pd.Timestamp]) -> pd.Timestamp:
        probe = self._normalize_timestamp(ts)
        for _ in range(14):
            if self.is_business_day(probe):
                candidate = probe.replace(
                    hour=self.config.trade_start_time.hour,
                    minute=self.config.trade_start_time.minute,
                    second=0,
                    microsecond=0,
                )
                if probe <= candidate:
                    return candidate
            probe = (probe + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return probe


def _bounded(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


@dataclass
class NewsResearchConfig:
    symbol: str = "ITUB4"
    enabled: bool = True
    storage_dir: str = "logs_vaiiixbr"
    headlines_file: str = "itub4_news_memory.jsonl"
    insights_file: str = "itub4_news_insights.json"
    token_stats_file: str = "itub4_news_token_stats.json"
    min_headlines_to_score: int = 2
    lookback_rows: int = 200
    label_horizon_bars: int = 6
    min_abs_return_to_label: float = 0.0015
    learning_min_token_occurrences: int = 2
    confidence_hint_cap: float = 0.08
    positive_terms: Sequence[str] = field(default_factory=lambda: (
        "lucro", "crescimento", "alta", "compra", "otimista", "recorde", "acordo",
        "supera", "upgrade", "dividendo", "eficiencia", "expansao", "melhora",
        "guidance", "margem", "retorno", "recuperacao"
    ))
    negative_terms: Sequence[str] = field(default_factory=lambda: (
        "queda", "baixa", "processo", "multa", "downgrade", "fraude", "risco",
        "inadimplencia", "crise", "prejuizo", "reduz", "rebaixamento", "piora",
        "provisao", "calote", "recuo"
    ))
    asset_aliases: Sequence[str] = field(default_factory=lambda: (
        "itub4", "itau", "itaú", "itau unibanco", "itaú unibanco"
    ))
    macro_aliases: Sequence[str] = field(default_factory=lambda: (
        "bancos", "selic", "juros", "credito", "crédito", "fintech",
        "spread bancario", "spread bancário", "inadimplencia", "inadimplência"
    ))


class NewsPriceLearningEngine:
    def __init__(self, config: Optional[NewsResearchConfig] = None):
        self.config = config or NewsResearchConfig()
        self.base_dir = Path(self.config.storage_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.headlines_path = self.base_dir / self.config.headlines_file
        self.insights_path = self.base_dir / self.config.insights_file
        self.token_stats_path = self.base_dir / self.config.token_stats_file
        self.token_stats = self._load_token_stats()

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"[a-zA-ZÀ-ÿ0-9_]+", (text or "").lower())

    def _normalize_title(self, title: str) -> str:
        return re.sub(r"\s+", " ", (title or "").strip())

    def _headline_id(self, timestamp: Any, title: str, source: Any) -> str:
        raw = f"{timestamp}|{source}|{self._normalize_title(title)}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _headline_relevance(self, headline: str) -> float:
        text = (headline or "").lower()
        score = 0.0
        if any(alias in text for alias in self.config.asset_aliases):
            score += 1.0
        if any(alias in text for alias in self.config.macro_aliases):
            score += 0.4
        return score

    def _lexicon_sentiment(self, headline: str) -> float:
        tokens = self._tokenize(headline)
        pos = sum(t in self.config.positive_terms for t in tokens)
        neg = sum(t in self.config.negative_terms for t in tokens)
        return float(pos - neg)

    def _load_token_stats(self) -> Dict[str, Dict[str, float]]:
        if not self.token_stats_path.exists():
            return {}
        try:
            return json.loads(self.token_stats_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_token_stats(self) -> None:
        self.token_stats_path.write_text(json.dumps(self.token_stats, ensure_ascii=False, indent=2), encoding="utf-8")

    def store_headlines(self, headlines: Sequence[Dict[str, Any]]) -> int:
        existing_ids = set()
        if self.headlines_path.exists():
            try:
                for line in self.headlines_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    payload = json.loads(line)
                    existing_ids.add(payload.get("headline_id"))
            except Exception:
                existing_ids = set()

        count = 0
        with self.headlines_path.open("a", encoding="utf-8") as f:
            for row in headlines:
                title = row.get("title") or row.get("headline") or ""
                source = row.get("source")
                ts = row.get("timestamp")
                headline_id = self._headline_id(ts, title, source)
                if headline_id in existing_ids:
                    continue
                payload = {
                    "headline_id": headline_id,
                    "timestamp": ts,
                    "source": source,
                    "title": self._normalize_title(title),
                    "url": row.get("url"),
                    "labeled": False,
                    "anchor_time": None,
                    "anchor_price": None,
                    "labeled_at": None,
                    "realized_return": None,
                    "return_label": None,
                    "label_horizon_bars": self.config.label_horizon_bars,
                }
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
                existing_ids.add(headline_id)
                count += 1
        return count

    def load_headlines(self) -> pd.DataFrame:
        if not self.headlines_path.exists():
            return pd.DataFrame(columns=["headline_id", "timestamp", "source", "title"])
        rows: List[Dict[str, Any]] = []
        for line in self.headlines_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        for col in ("timestamp", "anchor_time", "labeled_at"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        return df

    def _write_headlines_df(self, df: pd.DataFrame) -> None:
        rows = []
        for _, row in df.iterrows():
            payload = row.to_dict()
            for col in ("timestamp", "anchor_time", "labeled_at"):
                value = payload.get(col)
                if pd.isna(value):
                    payload[col] = None
                elif isinstance(value, pd.Timestamp):
                    payload[col] = value.isoformat()
            rows.append(json.dumps(payload, ensure_ascii=False))
        self.headlines_path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")

    def _learn_from_row(self, row: pd.Series) -> None:
        title = str(row.get("title") or "")
        ret = float(row.get("realized_return") or 0.0)
        label = str(row.get("return_label") or "flat")
        relevance = float(self._headline_relevance(title))
        if relevance <= 0:
            return
        for token in self._tokenize(title):
            stats = self.token_stats.setdefault(token, {
                "n": 0.0, "up": 0.0, "down": 0.0, "flat": 0.0, "sum_return": 0.0
            })
            stats["n"] += 1.0
            stats[label] += 1.0
            stats["sum_return"] += ret

    def update_labels_from_prices(self, price_df: pd.DataFrame) -> int:
        df = self.load_headlines()
        if df.empty or len(price_df) < max(3, self.config.label_horizon_bars + 1):
            return 0

        price = price_df.copy()
        price.index = pd.to_datetime(price.index, errors="coerce")
        price = price[~price.index.isna()].sort_index()
        if price.empty:
            return 0

        close = pd.to_numeric(price["close"], errors="coerce")
        changed = 0
        for idx, row in df[df["labeled"] != True].iterrows():
            ts = row.get("timestamp")
            if pd.isna(ts):
                continue
            anchor_candidates = price.index[price.index >= ts]
            if len(anchor_candidates) == 0:
                continue
            anchor_idx = anchor_candidates[0]
            anchor_pos = price.index.get_loc(anchor_idx)
            if isinstance(anchor_pos, slice):
                anchor_pos = anchor_pos.start
            target_pos = anchor_pos + int(self.config.label_horizon_bars)
            if target_pos >= len(price.index):
                continue

            anchor_price = float(close.iloc[anchor_pos])
            target_price = float(close.iloc[target_pos])
            if not np.isfinite(anchor_price) or not np.isfinite(target_price) or anchor_price == 0:
                continue

            realized_return = (target_price / anchor_price) - 1.0
            if abs(realized_return) < self.config.min_abs_return_to_label:
                label = "flat"
            else:
                label = "up" if realized_return > 0 else "down"

            df.at[idx, "anchor_time"] = anchor_idx
            df.at[idx, "anchor_price"] = anchor_price
            df.at[idx, "labeled_at"] = price.index[target_pos]
            df.at[idx, "realized_return"] = realized_return
            df.at[idx, "return_label"] = label
            df.at[idx, "labeled"] = True
            self._learn_from_row(df.loc[idx])
            changed += 1

        if changed:
            self._write_headlines_df(df)
            self._save_token_stats()
        return changed

    def _learned_token_score(self, headline: str) -> float:
        score = 0.0
        for token in self._tokenize(headline):
            stats = self.token_stats.get(token)
            if not stats:
                continue
            n = float(stats.get("n", 0.0))
            if n < self.config.learning_min_token_occurrences:
                continue
            up = float(stats.get("up", 0.0))
            down = float(stats.get("down", 0.0))
            avg_ret = float(stats.get("sum_return", 0.0)) / max(n, 1.0)
            directional = (up - down) / (n + 2.0)
            score += directional + math.tanh(avg_ret * 50.0) * 0.35
        return score

    def _score_title(self, title: str) -> float:
        relevance = self._headline_relevance(title)
        if relevance <= 0:
            return 0.0
        lexicon = self._lexicon_sentiment(title)
        learned = self._learned_token_score(title)
        total = relevance * (0.55 * lexicon + 0.45 * learned)
        return float(total)

    def _build_insight(self, price_df: pd.DataFrame, headlines_df: pd.DataFrame, mode: str) -> Dict[str, Any]:
        relevant = headlines_df.copy()
        if relevant.empty:
            insight = {
                "mode": mode,
                "status": "NO_NEWS_DATA",
                "headline_count": 0,
                "labeled_samples": int(sum(float(v.get("n", 0)) for v in self.token_stats.values()) / 5) if self.token_stats else 0,
                "price_bias": "NEUTRAL",
                "confidence_adjustment_hint": 0.0,
                "news_price_score": 0.0,
                "summary": "Sem manchetes relevantes armazenadas para ITUB4.",
            }
            self.insights_path.write_text(json.dumps(insight, ensure_ascii=False, indent=2), encoding="utf-8")
            return insight

        recent = relevant.tail(max(self.config.lookback_rows, self.config.min_headlines_to_score)).copy()
        recent["title"] = recent["title"].fillna("").astype(str)
        recent["relevance"] = recent["title"].map(self._headline_relevance)
        recent = recent[recent["relevance"] > 0].copy()

        if recent.empty:
            return self._build_insight(price_df, pd.DataFrame(), mode)

        recent["lexicon_sentiment"] = recent["title"].map(self._lexicon_sentiment)
        recent["learned_sentiment"] = recent["title"].map(self._learned_token_score)
        recent["news_score"] = recent["title"].map(self._score_title)

        close = pd.to_numeric(price_df["close"], errors="coerce")
        returns = close.pct_change().dropna()
        realized_vol = float(returns.tail(20).std()) if len(returns) >= 5 else 0.0
        dispersion = float(recent["news_score"].std()) if len(recent) > 1 else 0.0

        aggregated_news = float(recent["news_score"].mean())
        normalized = math.tanh(aggregated_news / 2.4)
        vol_penalty = min(0.30, realized_vol * 3.5 + dispersion * 0.05)
        final_score = float(_bounded(normalized * (1.0 - vol_penalty), -1.0, 1.0))

        if final_score >= 0.15:
            bias = "UP_BIAS"
        elif final_score <= -0.15:
            bias = "DOWN_BIAS"
        else:
            bias = "NEUTRAL"

        confidence_hint = _bounded(final_score * 0.08, -self.config.confidence_hint_cap, self.config.confidence_hint_cap)
        learned_tokens = sum(1 for _, v in self.token_stats.items() if float(v.get("n", 0.0)) >= self.config.learning_min_token_occurrences)

        insight = {
            "mode": mode,
            "status": "OK",
            "headline_count": int(len(recent)),
            "labeled_samples": int(sum(1 for v in self.token_stats.values() if float(v.get("n", 0.0)) > 0)),
            "learned_tokens": learned_tokens,
            "news_price_score": round(final_score, 4),
            "headline_lexicon_mean": round(float(recent["lexicon_sentiment"].mean()), 4),
            "headline_learned_mean": round(float(recent["learned_sentiment"].mean()), 4),
            "price_bias": bias,
            "confidence_adjustment_hint": round(confidence_hint, 4),
            "realized_vol_20": round(realized_vol, 6),
            "summary": self._summary_text(recent, bias, final_score),
            "sample_titles": recent["title"].tail(3).tolist(),
        }
        self.insights_path.write_text(json.dumps(insight, ensure_ascii=False, indent=2), encoding="utf-8")
        return insight

    def latest_insight(self) -> Dict[str, Any]:
        if not self.insights_path.exists():
            return {}
        try:
            return json.loads(self.insights_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def run_offhours_cycle(self, price_df: pd.DataFrame, headlines: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
        if headlines:
            self.store_headlines(headlines)
        stored = self.load_headlines()
        return self._build_insight(price_df, stored, mode="OFF_HOURS_RESEARCH")

    def run_live_cycle(self, price_df: pd.DataFrame, headlines: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
        if headlines:
            self.store_headlines(headlines)
        self.update_labels_from_prices(price_df)
        stored = self.load_headlines()
        live_recent = stored.copy()
        if not live_recent.empty and "timestamp" in live_recent.columns:
            ts_series = pd.to_datetime(live_recent["timestamp"], errors="coerce", utc=True)
            last_ts = pd.Timestamp(price_df.index[-1])
            if last_ts.tzinfo is None:
                last_ts = last_ts.tz_localize("UTC")
            else:
                last_ts = last_ts.tz_convert("UTC")
            live_recent = live_recent.loc[ts_series.notna()].copy()
            ts_series = ts_series.loc[ts_series.notna()]
            live_recent = live_recent[ts_series <= last_ts]
            live_recent = live_recent.tail(max(self.config.min_headlines_to_score, 12))
        return self._build_insight(price_df, live_recent, mode="LIVE_NEWS_LEARNING")

    def _summary_text(self, recent: pd.DataFrame, bias: str, final_score: float) -> str:
        if recent.empty:
            return "Sem manchetes relevantes para ITUB4."
        direction = "altista" if final_score > 0 else "baixista" if final_score < 0 else "neutra"
        return (
            f"Foram avaliadas {len(recent)} manchetes relevantes; "
            f"o motor de aprendizado notícia-preço inferiu leitura {direction}; "
            f"viés final={bias}."
        )


class MarketAwareVAIIIxBRPaperTrader(BaseVAIIIxBRPaperTrader):
    def __init__(
        self,
        config: Optional[HybridConfig] = None,
        market_hours: Optional[MarketHoursConfig] = None,
        news_research: Optional[NewsResearchConfig] = None,
    ):
        super().__init__(config=config)
        self.market_clock = B3MarketClock(market_hours)
        self.research_engine = NewsPriceLearningEngine(news_research or NewsResearchConfig(storage_dir=self.config.logs_dir))
        self.last_mode = "UNINITIALIZED"

    def _apply_news_bias(
        self,
        vaiiixbr_signal: str,
        vaiiixbr_confidence: float,
        research: Dict[str, Any],
    ) -> tuple[str, float]:
        signal = str(vaiiixbr_signal).upper().strip()
        confidence = float(vaiiixbr_confidence)
        hint = float(research.get("confidence_adjustment_hint", 0.0))
        bias = str(research.get("price_bias", "NEUTRAL"))

        if signal == "BUY":
            if bias == "UP_BIAS":
                confidence += abs(hint)
            elif bias == "DOWN_BIAS":
                confidence -= abs(hint)
        elif signal == "SELL":
            if bias == "DOWN_BIAS":
                confidence += abs(hint)
            elif bias == "UP_BIAS":
                confidence -= abs(hint)

        confidence = _bounded(confidence, 0.01, 0.99)
        return signal, confidence

    def on_bar(
        self,
        df: pd.DataFrame,
        vaiiixbr_signal: str,
        vaiiixbr_confidence: float,
        headlines: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        timestamp = df.index[-1] if len(df.index) else None
        session_label = self.market_clock.current_session_label(timestamp)

        if not self.market_clock.is_open(timestamp):
            insight = self.research_engine.run_offhours_cycle(df, headlines=headlines)
            self.last_mode = "OFF_HOURS_RESEARCH"
            snapshot = {
                "mode": "OFF_HOURS_RESEARCH",
                "session": session_label,
                "market_open": False,
                "next_open": self.market_clock.next_open(timestamp).isoformat(),
                "decision": None,
                "position": asdict(self.position) if self.position else None,
                "metrics": self.metrics(),
                "research": insight,
                "alert": f"MERCADO FECHADO | ciclos de trade pausados | {self.config.symbol} | sessão={session_label}",
            }
            logger.info(snapshot["alert"])
            self._write_metrics()
            return snapshot

        live_research = self.research_engine.run_live_cycle(df, headlines=headlines)
        adjusted_signal, adjusted_confidence = self._apply_news_bias(
            vaiiixbr_signal=vaiiixbr_signal,
            vaiiixbr_confidence=vaiiixbr_confidence,
            research=live_research,
        )

        trading_snapshot = super().on_bar(df, adjusted_signal, adjusted_confidence)
        trading_snapshot["mode"] = "LIVE_TRADING"
        trading_snapshot["session"] = session_label
        trading_snapshot["market_open"] = True
        trading_snapshot["news_learning"] = live_research
        trading_snapshot["decision"]["news_adjusted_input_confidence"] = round(adjusted_confidence, 4)
        trading_snapshot["decision"]["news_bias"] = live_research.get("price_bias", "NEUTRAL")
        trading_snapshot["decision"]["news_confidence_hint"] = live_research.get("confidence_adjustment_hint", 0.0)
        trading_snapshot["decision"]["news_price_score"] = live_research.get("news_price_score", 0.0)
        self.last_mode = "LIVE_TRADING"
        return trading_snapshot


VAIIIxBRPaperTrader = MarketAwareVAIIIxBRPaperTrader


def fake_headlines() -> List[Dict[str, Any]]:
    return [
        {"timestamp": "2026-03-24T19:10:00-03:00", "source": "demo", "title": "Itaú Unibanco tem crescimento de lucro e melhora de eficiência"},
        {"timestamp": "2026-03-24T19:20:00-03:00", "source": "demo", "title": "Setor de bancos reage à queda da inadimplência e cenário de juros"},
        {"timestamp": "2026-03-25T10:20:00-03:00", "source": "demo", "title": "Analistas veem alta moderada para ITUB4 após resultados"},
    ]


if __name__ == "__main__":
    from vaiiixbr_standard_itub4 import fake_itub4_df

    df = fake_itub4_df()
    trader = VAIIIxBRPaperTrader()

    closed_df = df.copy()
    closed_df.index = pd.date_range("2026-03-24 19:00:00", periods=len(df), freq="5min", tz="America/Sao_Paulo")
    result_closed = trader.on_bar(closed_df, "BUY", 0.76, headlines=fake_headlines()[:2])

    open_df = df.copy()
    open_df.index = pd.date_range("2026-03-25 10:00:00", periods=len(df), freq="5min", tz="America/Sao_Paulo")
    result_open = trader.on_bar(open_df, "BUY", 0.76, headlines=fake_headlines()[2:])

    print(json.dumps(result_closed, ensure_ascii=False, indent=2))
    print(json.dumps(result_open, ensure_ascii=False, indent=2))
