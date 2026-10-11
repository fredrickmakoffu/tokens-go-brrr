"""Facade — implementation lives in ``ledger.core`` until further extract."""

from __future__ import annotations

from .core import (
    LedgerRecorder,
)

__all__ = [
    "LedgerRecorder",
]
