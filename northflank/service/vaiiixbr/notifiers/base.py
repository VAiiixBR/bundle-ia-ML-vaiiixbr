from __future__ import annotations

from typing import Protocol, Any


class Notifier(Protocol):
    def notify(self, payload: dict[str, Any]) -> None: ...
