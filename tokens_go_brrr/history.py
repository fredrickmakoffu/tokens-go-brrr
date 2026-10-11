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
import time
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
    return base / "tokens-go-brrr" / "history.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or default_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(target)
    con.executescript(SCHEMA)
    con.commit()
    return con


# A meter only climbs within a window, so a percent that has fallen by more
# than this between two samples means the window rolled over in between.
# Loose enough to absorb a provider rounding its own figure.
ROLLOVER_DROP = 0.5

# Two samples further apart than this did not come from one continuous watch —
# the daemon was stopped, or the machine slept — and the line between them
# describes nothing.
MAX_GAP_SECONDS = 3600


def _epoch(moment: datetime | None = None) -> int:
    """Epoch seconds, never raising.

    `time.time()` is the net for a date so extreme that `.timestamp()` refuses;
    it cannot itself fail, and returning 0 here would be worse than useless in
    `prune`, where a zero cutoff means "delete everything".
    """
    try:
        return int((moment or datetime.now(timezone.utc)).timestamp())
    except (OSError, OverflowError, ValueError):
        return int(time.time())


def _as_float(value: Any) -> float:
    """A meter's percentage is whatever the provider returned; treat junk as 0."""
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _window_key(resets_at: datetime | None) -> str:
    """The reset a sample was counting towards, stored for reference.

    Deliberately not used to group samples. It looked like the obvious key and
    is not one: Claude returns the same reset with microsecond jitter
    (15:00:00.653206, then 15:00:00.933186), and OpenCode's rolling window
    slides forward every poll by design. Either one turns a continuous series
    into a pile of one-sample groups. Rollovers are detected from the meter
    itself instead, in `window_samples`.
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
    stamp = _epoch(at)
    # The batch is built inline: every argument to the statement is a value,
    # never a query composed at runtime.
    before = con.total_changes
    con.executemany(
        "INSERT INTO samples (ts, provider, metric, percent, resets_at)"
        " VALUES (?, ?, ?, ?, ?)",
        [
            (
                stamp,
                snap.provider_id,
                meter.key,
                _as_float(meter.percent),
                _window_key(meter.resets_at),
            )
            for snap in snapshots
            if snap.status == "ok" and snap.borrowed_from is None
            for meter in snap.metrics
            if meter.key != "—"
        ],
    )
    con.commit()
    return con.total_changes - before


def window_samples(
    con: sqlite3.Connection,
    provider: str,
    metric: str,
    *,
    limit: int = 200,
) -> list[tuple[float, float]]:
    """(timestamp, percent) for the window currently open, oldest first.

    Walks back from the newest sample and stops at the first thing that breaks
    the series: a meter that was higher earlier than it is now — which only
    happens across a reset — or a gap too long to have been one continuous
    watch. What survives is the run of samples describing the window in
    progress, whether the provider's window is fixed, rolling, or reported with
    a jittering reset time.
    """
    cur = con.execute(
        "SELECT ts, percent FROM samples"
        " WHERE provider = ? AND metric = ?"
        " ORDER BY ts DESC LIMIT ?",
        (provider, metric, limit),
    )
    newest_first = [(_as_float(ts), _as_float(pct)) for ts, pct in cur.fetchall()]

    kept: list[tuple[float, float]] = []
    for sample in newest_first:
        if kept:
            newer_ts, newer_pct = kept[-1]
            if newer_ts - sample[0] > MAX_GAP_SECONDS:
                break
            if sample[1] > newer_pct + ROLLOVER_DROP:
                break
        kept.append(sample)
    return list(reversed(kept))


def prune(con: sqlite3.Connection, *, keep_days: int = 90) -> int:
    """Drop samples past the retention window. Returns rows removed."""
    if keep_days <= 0:
        return 0
    cutoff = _epoch() - keep_days * 86400
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
        # Narrow once here: `active` proves the connection exists, but only a
        # local check tells the type checker so.
        con = self._con if self.active else None
        if con is None:
            return 0
        try:
            return record(con, snapshots, at=at)
        except sqlite3.Error as exc:
            self._disable(f"Could not record usage history: {exc}")
            return 0

    def window_samples(self, provider: str, metric: str) -> list[tuple[float, float]]:
        con = self._con if self.active else None
        if con is None:
            return []
        try:
            return window_samples(con, provider, metric)
        except sqlite3.Error as exc:
            self._disable(f"Could not read usage history: {exc}")
            return []

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None
