"""Facade — implementation lives in ``notify_engine.core`` until further extract."""

from __future__ import annotations

from .core import (
    _insight,
    has_pending_insight,
    insight_cache,
    insight_candidates,
    insight_focus,
    insight_peak,
    insight_rhythm,
    insight_week,
    next_insight,
)

__all__ = [
    "_insight",
    "has_pending_insight",
    "insight_cache",
    "insight_candidates",
    "insight_focus",
    "insight_peak",
    "insight_rhythm",
    "insight_week",
    "next_insight",
]
