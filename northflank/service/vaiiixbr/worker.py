from __future__ import annotations

import logging
import time

from vaiiixbr.config import Settings
from vaiiixbr.services import EngineService
from vaiiixbr.storage.repository import Repository
from vaiiixbr.storage.sqlite_store import SQLiteStore


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings()
    store = SQLiteStore(settings)
    repository = Repository(store)
    engine = EngineService(settings, repository)

    logging.info("VAIIIxBR worker iniciado para %s", settings.asset)
    while True:
        try:
            status = engine.tick()
            logging.info(
                "tick | decision=%s | score=%s | cash=%.2f | equity=%.2f",
                status.get("signal", {}).get("decision"),
                status.get("signal", {}).get("long_score"),
                float(status.get("paper", {}).get("cash", 0.0)),
                float(status.get("paper", {}).get("equity", 0.0)),
            )
        except Exception as exc:
            logging.exception("Falha no worker: %s", exc)
        time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
