from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(slots=True)
class Settings:
    asset: str = os.getenv("VAIII_ASSET", "ITUB4")
    interval: str = os.getenv("VAIII_INTERVAL", "5m")
    range_period: str = os.getenv("VAIII_RANGE", "5d")
    timezone: str = os.getenv("VAIII_TIMEZONE", "America/Sao_Paulo")

    brapi_token: str | None = os.getenv("BRAPI_TOKEN")
    brapi_base_url: str = os.getenv("BRAPI_BASE_URL", "https://brapi.dev/api")
    http_timeout_seconds: int = int(os.getenv("VAIII_HTTP_TIMEOUT", "20"))

    fast_ma: int = int(os.getenv("VAIII_FAST_MA", "9"))
    slow_ma: int = int(os.getenv("VAIII_SLOW_MA", "21"))
    trend_ma: int = int(os.getenv("VAIII_TREND_MA", "50"))
    rsi_period: int = int(os.getenv("VAIII_RSI_PERIOD", "14"))
    atr_period: int = int(os.getenv("VAIII_ATR_PERIOD", "14"))
    volume_window: int = int(os.getenv("VAIII_VOLUME_WINDOW", "20"))
    swing_lookback: int = int(os.getenv("VAIII_SWING_LOOKBACK", "20"))

    min_score_long: int = int(os.getenv("VAIII_MIN_SCORE_LONG", "70"))
    high_confidence_score: int = int(os.getenv("VAIII_HIGH_CONFIDENCE_SCORE", "80"))
    min_volume_ratio_for_entry: float = float(os.getenv("VAIII_MIN_VOLUME_RATIO", "1.10"))
    min_rsi_long: float = float(os.getenv("VAIII_MIN_RSI_LONG", "53.0"))
    max_rsi_long: float = float(os.getenv("VAIII_MAX_RSI_LONG", "68.0"))
    require_breakout_confirmation: bool = os.getenv("VAIII_REQUIRE_BREAKOUT", "true").lower() == "true"

    atr_stop_multiplier: float = float(os.getenv("VAIII_ATR_STOP_MULTIPLIER", "1.2"))
    atr_target_multiplier: float = float(os.getenv("VAIII_ATR_TARGET_MULTIPLIER", "2.0"))
    risk_per_trade: float = float(os.getenv("VAIII_RISK_PER_TRADE", "0.01"))
    paper_initial_cash: float = float(os.getenv("VAIII_PAPER_INITIAL_CASH", "50.0"))
    fee_per_trade: float = float(os.getenv("VAIII_FEE_PER_TRADE", "0.0005"))
    slippage_per_trade: float = float(os.getenv("VAIII_SLIPPAGE_PER_TRADE", "0.0003"))
    exit_on_signal_loss: bool = os.getenv("VAIII_EXIT_ON_SIGNAL_LOSS", "true").lower() == "true"

    worker_poll_seconds: int = int(os.getenv("VAIII_POLL_SECONDS", "60"))
    embedded_worker_enabled: bool = os.getenv("VAIII_EMBEDDED_WORKER", "true").lower() == "true"
    api_host: str = os.getenv("VAIII_API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("PORT", os.getenv("VAIII_API_PORT", "8000")))
    environment: str = os.getenv("VAIII_ENV", "production")

    data_dir: Path = Path(os.getenv("VAIII_DATA_DIR", "/app/data"))
    sqlite_path: Path = Path(os.getenv("VAIII_SQLITE_PATH", "/app/data/vaiiixbr.db"))
    worker_state_path: Path = Path(os.getenv("VAIII_WORKER_STATE_PATH", "/app/data/worker_state.json"))

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.worker_state_path.parent.mkdir(parents=True, exist_ok=True)
