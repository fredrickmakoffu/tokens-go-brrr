"""Facade — implementation lives in ``notify_engine.core`` until further extract."""

from __future__ import annotations

from .core import (
    _best_room,
    cold_note,
    find_elsewhere,
    render_warm,
    tightest_short_meter,
    warm_facts,
    warm_fingerprint,
    warm_note,
)

__all__ = [
    "_best_room",
    "cold_note",
    "find_elsewhere",
    "render_warm",
    "tightest_short_meter",
    "warm_facts",
    "warm_fingerprint",
    "warm_note",
]
