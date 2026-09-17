"""Keep every sample the daemon publishes, because usage questions are about time.

A percentage on its own says where you are; it takes a series to say where you
are heading. Nothing here is backfillable — a window that was not recorded while
it was open cannot be reconstructed afterwards — so the daemon records from the
moment this ships, whether or not anything reads it yet.

One row per meter per poll. At the default five-minute interval that is a few
thousand rows a day, which SQLite does not notice.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    ts        INTEGER NOT NULL,
    provider  TEXT    NOT NULL,
    metric    TEXT    NOT NULL,
    percent   REAL    NOT NULL,
    resets_at TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS samples_lookup
    ON samples (provider, metric, resets_at, ts);
"""


def default_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return base / "cursor-spend-monitor" / "history.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or default_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(target)
    con.executescript(SCHEMA)
    con.commit()
    return con


def _window_key(resets_at: datetime | None) -> str:
    """What makes two samples part of the same limit window.

    A meter falls back to zero when its window rolls over, so a series that
    spans a reset describes no trend at all. Tagging each sample with the reset
    it was counting towards keeps the two sides apart.
    """
    return resets_at.isoformat() if resets_at else ""


def record(
    con: sqlite3.Connection, snapshots: list[Any], *, at: datetime | None = None
) -> int:
    """Store one row per meter. Returns how many rows were written.

    Only providers that own their meters are recorded. A harness row holds a
    copy of another account's numbers, so storing it too would write every
    sample of that subscription twice and double-weight it in any later fit.
    """
    stamp = int((at or datetime.now(timezone.utc)).timestamp())
    rows = []
    for snap in snapshots:
        if snap.status != "ok" or snap.borrowed_from is not None:
            continue
        for meter in snap.metrics:
            if meter.key == "—":
                continue
            rows.append(
                (stamp, snap.provider_id, meter.key, float(meter.percent),
                 _window_key(meter.resets_at))
            )
    if not rows:
        return 0
    con.executemany(
        "INSERT INTO samples (ts, provider, metric, percent, resets_at)"
        " VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    con.commit()
    return len(rows)


def window_samples(
    con: sqlite3.Connection,
    provider: str,
    metric: str,
    resets_at: datetime | None,
    *,
    limit: int = 200,
) -> list[tuple[float, float]]:
    """(timestamp, percent) for the window currently open, oldest first."""
    cur = con.execute(
        "SELECT ts, percent FROM samples"
        " WHERE provider = ? AND metric = ? AND resets_at = ?"
        " ORDER BY ts DESC LIMIT ?",
        (provider, metric, _window_key(resets_at), limit),
    )
    return [(float(ts), float(pct)) for ts, pct in reversed(cur.fetchall())]


def prune(con: sqlite3.Connection, *, keep_days: int = 90) -> int:
    """Drop samples past the retention window. Returns rows removed."""
    if keep_days <= 0:
        return 0
    cutoff = int(datetime.now(timezone.utc).timestamp()) - keep_days * 86400
    cur = con.execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
    con.commit()
    return cur.rowcount or 0


class Recorder:
    """Daemon-side wrapper that never lets a storage problem stop monitoring.

    History is a nice-to-have; the panel is the product. A locked or unwritable
    database disables recording for the session and says so once, rather than
    raising on every poll.
    """

    def __init__(self, path: Path | None = None, *, keep_days: int = 90) -> None:
        self.keep_days = keep_days
        self._con: sqlite3.Connection | None = None
        self._failed = False
        try:
            self._con = connect(path)
            prune(self._con, keep_days=keep_days)
        except (sqlite3.Error, OSError) as exc:
            self._disable(f"Could not open usage history: {exc}")

    @property
    def active(self) -> bool:
        return self._con is not None and not self._failed

    def _disable(self, message: str) -> None:
        if not self._failed:
            print(message, file=sys.stderr, flush=True)
        self._failed = True
        self._con = None

    def record(self, snapshots: list[Any], *, at: datetime | None = None) -> int:
        if not self.active:
            return 0
        try:
            return record(self._con, snapshots, at=at)
        except sqlite3.Error as exc:
            self._disable(f"Could not record usage history: {exc}")
            return 0

    def window_samples(
        self, provider: str, metric: str, resets_at: datetime | None
    ) -> list[tuple[float, float]]:
        if not self.active:
            return []
        try:
            return window_samples(self._con, provider, metric, resets_at)
        except sqlite3.Error as exc:
            self._disable(f"Could not read usage history: {exc}")
            return []

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None
