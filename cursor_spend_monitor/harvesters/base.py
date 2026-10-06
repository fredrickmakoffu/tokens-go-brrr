"""The contract every vendor reader implements.

A harvester reads one tool's own store and writes only sessions it can prove.
The rules it must follow are what make the ledger trustworthy:

* **Never raise into the daemon.** A locked database, a rotated log or a
  refused request is this reader's problem for this cycle. It is reported as a
  `HarvestResult` note, not raised at the caller.

* **Be idempotent.** Write through `ledger.upsert_sessions`, which skips rows
  whose values are unchanged; a second run over an untouched store reports zero.

* **Advance the watermark only after the rows are stored.** If the write fails
  halfway, the next run has to see the same rows again. A watermark that leads
  the data silently loses history, which is the one thing this store exists to
  prevent.

* **Absolute, not incremental.** Token columns are session totals; a reader
  that tails a file accumulates before it calls.

* **Say where a number came from.** `source` is `local-db`, `local-transcript`,
  `api` or `estimate` — never blank, and never a guess dressed as a measurement.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Protocol


@dataclass
class HarvestResult:
  """What one reader did, in terms the CLI prints and tests assert."""

  harvester: str
  provider: str
  scanned: int = 0
  # Rows that actually changed in the ledger. Re-reading an unchanged store
  # reports 0 here, which is the evidence that idempotency holds.
  sessions: int = 0
  per_model: int = 0
  folded_days: int = 0
  watermark: str | None = None
  note: str = ""
  failed: bool = False

  @property
  def changed(self) -> int:
    return self.sessions + self.per_model


class Harvester(Protocol):
  # Stable name for watermarks and log lines (`opencode`, `claude_jsonl`).
  id: str
  # The provider id this reader feeds, matching the panel's provider list.
  # `cursor_api` reads for provider `cursor`, so the two differ.
  provider: str

  def available(self) -> bool:
    """True when the local store this reader needs is present."""
    ...

  def harvest(self, con: sqlite3.Connection, *, full: bool = False) -> HarvestResult:
    """Read the store and write what changed. Must not raise."""
    ...
