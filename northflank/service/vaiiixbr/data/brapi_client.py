from __future__ import annotations

from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from vaiiixbr.config import Settings


class BrapiClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.brapi_base_url.rstrip("/")
        self.session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = dict(params or {})
        headers = {"Accept": "application/json"}
        if self.settings.brapi_token:
            query.setdefault("token", self.settings.brapi_token)
            headers["Authorization"] = f"Bearer {self.settings.brapi_token}"
        response = self.session.get(
            f"{self.base_url}{path}",
            params=query,
            headers=headers,
            timeout=self.settings.http_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(payload.get("message") or payload.get("error") or "Erro desconhecido da brapi.dev")
        return payload

    def get_ohlcv(self) -> pd.DataFrame:
        payload = self._request(
            f"/quote/{self.settings.asset}",
            params={"interval": self.settings.interval, "range": self.settings.range_period},
        )
        results = payload.get("results", [])
        if not results:
            raise RuntimeError(f"Nenhum resultado OHLCV retornado para {self.settings.asset}")
        history = results[0].get("historicalDataPrice") or []
        if not history:
            raise RuntimeError("A brapi.dev não retornou historicalDataPrice para o ativo/intervalo informados")

        df = pd.DataFrame(history)
        required = {"date", "open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns):
            raise RuntimeError(f"Resposta incompleta da brapi.dev. Faltando: {required - set(df.columns)}")

        df["timestamp"] = pd.to_datetime(df["date"], unit="s", utc=True).dt.tz_convert(self.settings.timezone)
        df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna().drop_duplicates(subset=["timestamp"]).set_index("timestamp").sort_index()
        return df
