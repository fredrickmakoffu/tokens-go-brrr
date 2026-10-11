"""Facade — implementation lives in ``notify_engine.core`` until further extract."""

from __future__ import annotations

from .core import (
    _eta_label,
    event_messages,
)

__all__ = [
    "_eta_label",
    "event_messages",
]
