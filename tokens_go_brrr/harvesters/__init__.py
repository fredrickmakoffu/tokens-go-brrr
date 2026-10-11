"""Readers that fill the usage ledger from the tools' own stores.

`REGISTRY` is the single place that lists what ships, so `harvest` and the
daemon's deep-harvest timer discover readers the same way and nothing else in
the codebase has to know a reader exists. Phases append to it; order is
presentation order only.
"""

from __future__ import annotations

from .base import Harvester, HarvestResult
from .claude_transcripts import ClaudeTranscriptHarvester
from .codex_state import CodexStateHarvester
from .dashboard_usage import CursorApiHarvester
from .opencode_db import OpenCodeHarvester
from .pi_sessions import PiSessionHarvester

REGISTRY: list[type] = [
    OpenCodeHarvester,
    ClaudeTranscriptHarvester,
    CursorApiHarvester,
    CodexStateHarvester,
    PiSessionHarvester,
]


def build(providers: list[str] | None = None) -> list[Harvester]:
    """One instance per registered reader, optionally only for some providers.

    `providers` filters on the provider a reader feeds, so `--provider cursor`
    selects the reader that writes Cursor rows even when the reader's own id is
    `cursor_api`. Passing nothing harvests everything installed: the ledger is
    about what was spent, not about which rows the panel currently shows.
    """
    wanted = set(providers) if providers else None
    readers: list[Harvester] = []
    for cls in REGISTRY:
        reader = cls()
        if wanted is not None and reader.provider not in wanted:
            continue
        readers.append(reader)
    return readers


__all__ = [
    "ClaudeTranscriptHarvester",
    "CodexStateHarvester",
    "CursorApiHarvester",
    "HarvestResult",
    "Harvester",
    "OpenCodeHarvester",
    "PiSessionHarvester",
    "REGISTRY",
    "build",
]
