from __future__ import annotations

from typing import Any
import logging


class LogNotifier:
    def __init__(self) -> None:
        self.logger = logging.getLogger("vaiiixbr.notifier")

    def notify(self, payload: dict[str, Any]) -> None:
        decision = payload.get("decision")
        if decision == "compra":
            self.logger.info("ENTRADA GARANTIDA | %s | score=%s | gate=%s", payload.get("asset"), payload.get("long_score"), payload.get("decision_gate"))
        else:
            self.logger.info("Possível entrada | score=%s | modo=%s | qualidade=%s", payload.get("long_score"), payload.get("pre_analysis_mode"), payload.get("entry_quality"))
