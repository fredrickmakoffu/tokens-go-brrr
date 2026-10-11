"""Shared coercion for vendor JSON and config values.

Meter policy (utilization / percent used):
  unparsable → None (caller drops the meter or uses error_snapshot);
  never publish a healthy 0% for "unknown".
  A real ``0`` / ``"0"`` from the vendor is a reading, not unknown.

Config and non-meter figures may pass an explicit default instead.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any


def as_int(value: Any, default: int = 0) -> int:
    """Coerce to int, or ``default`` when the value will not parse."""
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def as_int_or_none(value: Any) -> int | None:
    """Coerce to int, or None when missing/unparsable."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def as_float(value: Any, default: float = 0.0) -> float:
    """Coerce to float, or ``default`` when the value will not parse."""
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default


def as_float_or_none(value: Any) -> float | None:
    """Coerce to float, or None when missing/unparsable.

    Use for utilization / percent-used fields so a bad reading is dropped
    instead of becoming a healthy zero.
    """
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def parse_iso(value: Any) -> datetime | None:
    """ISO-8601 timestamp (accepting a trailing Z), or None."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_ms_or_iso(value: Any) -> datetime | None:
    """Unix milliseconds (int/str) or ISO-8601, or None."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
        return parse_iso(value)
    except (ValueError, OSError, OverflowError, TypeError):
        return None


def jwt_exp(token: str) -> int | None:
    """JWT ``exp`` claim in seconds, without verifying the signature.

    Used only to decide whether a locally stored access token looks stale;
    the vendor CLI owns refresh.
    """
    if not token:
        return None
    try:
        payload = token.split(".")[1]
        pad = "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload + pad))
    except (IndexError, ValueError, json.JSONDecodeError):
        return None
    exp = data.get("exp")
    if not isinstance(exp, (int, float)):
        return None
    try:
        return int(exp)
    except (TypeError, ValueError, OverflowError):
        return None
