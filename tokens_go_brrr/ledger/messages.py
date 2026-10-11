"""Facade — implementation lives in ``ledger.core`` until further extract."""

from __future__ import annotations

from .core import (
    last_generated_at,
    last_message_age,
    latest_message,
    mark_message_seen,
    pending_messages,
    recent_messages,
    store_message,
)

__all__ = [
    "last_generated_at",
    "last_message_age",
    "latest_message",
    "mark_message_seen",
    "pending_messages",
    "recent_messages",
    "store_message",
]
