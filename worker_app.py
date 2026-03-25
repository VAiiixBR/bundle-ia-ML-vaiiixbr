from __future__ import annotations

"""
Wrapper de entrada para o newsworker.

Use:
    uvicorn worker_app:app --reload
ou:
    uvicorn newsworker.worker:app --reload
"""

from newsworker.worker import app

__all__ = ["app"]
