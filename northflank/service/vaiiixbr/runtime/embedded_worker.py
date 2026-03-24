from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from vaiiixbr.services import EngineService


@dataclass(slots=True)
class EmbeddedWorkerState:
    enabled: bool = False
    running: bool = False
    started_at: str | None = None
    last_tick_at: str | None = None
    last_error: str | None = None
    tick_count: int = 0
    sleep_seconds: int = 60
    mode: str = "disabled"
    last_status: dict[str, Any] = field(default_factory=dict)


class EmbeddedWorker:
    def __init__(self, engine: EngineService, poll_seconds: int):
        self.engine = engine
        self.poll_seconds = poll_seconds
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.state = EmbeddedWorkerState(sleep_seconds=poll_seconds)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self.state.enabled = True
        self.state.running = True
        self.state.mode = "embedded"
        self.state.started_at = datetime.now(timezone.utc).isoformat()
        self._thread = threading.Thread(target=self._run, name="vaiiixbr-embedded-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self.state.running = False

    def snapshot(self) -> dict[str, Any]:
        return {
            "enabled": self.state.enabled,
            "running": self.state.running,
            "started_at": self.state.started_at,
            "last_tick_at": self.state.last_tick_at,
            "last_error": self.state.last_error,
            "tick_count": self.state.tick_count,
            "sleep_seconds": self.state.sleep_seconds,
            "mode": self.state.mode,
        }

    def _run(self) -> None:
        logger = logging.getLogger("vaiiixbr.embedded_worker")
        logger.info("Embedded worker iniciado")
        while not self._stop_event.is_set():
            try:
                status = self.engine.tick()
                self.state.tick_count += 1
                self.state.last_tick_at = datetime.now(timezone.utc).isoformat()
                self.state.last_status = status
                self.state.last_error = None
                logger.info(
                    "embedded tick | decision=%s | score=%s",
                    status.get("signal", {}).get("decision"),
                    status.get("signal", {}).get("long_score"),
                )
            except Exception as exc:  # pragma: no cover
                self.state.last_error = str(exc)
                logger.exception("Falha no embedded worker: %s", exc)
            self._stop_event.wait(self.poll_seconds)
        self.state.running = False
