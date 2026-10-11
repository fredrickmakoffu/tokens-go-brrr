"""Compatibility shim — Cursor HTTP lives in ``providers.cursor_api``."""

from __future__ import annotations

from .providers.cursor_api import *  # noqa: F403
from .providers.cursor_api import (  # noqa: F401
    AGGREGATED_PATH,
    API2_BASE,
    API2_HOST,
    HARD_LIMIT_PATH,
    PLAN_PATH,
    POLICY_PATH,
    USAGE_PATH,
    CursorUsageClient,
    UsageSummary,
)

__all__ = [
    "AGGREGATED_PATH",
    "API2_BASE",
    "API2_HOST",
    "HARD_LIMIT_PATH",
    "PLAN_PATH",
    "POLICY_PATH",
    "USAGE_PATH",
    "CursorUsageClient",
    "UsageSummary",
]
