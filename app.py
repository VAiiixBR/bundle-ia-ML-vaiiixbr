from __future__ import annotations

"""
Wrapper de entrada para execução local/Northflank.

Use:
    uvicorn app:app --reload
"""

from vaiiixbr_standard.app import app

__all__ = ["app"]
