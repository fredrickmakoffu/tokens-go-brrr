"""Read OpenCode's own session record.

`~/.local/share/opencode/opencode.db` is the OpenCode TUI's database, and its
`session` table is the tool's own billing record: exact cost and exact token
kinds per session, including cache reads and cache writes. That makes it the
best source in the ledger — the only one where cost needs no interpretation.

Two things it is not. It is not a store we own: the TUI writes it while this
reads, so the connection is read-only and a busy moment skips the cycle rather
than holding a lock. And it is not complete: Pi sessions never land here, so
Pi's usage has to come from the Pi reader.

Attribution: `provider` is the tool (`opencode`) because that is the row the
panel and the digests group by. The account a session was billed to —
`opencode-go`, or a bring-your-own-key provider — is kept in `meta.account`,
so a digest can still tell the two apart without splitting the tool in two.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .. import ledger
from .base import HarvestResult

HARVESTER_ID = "opencode"
PROVIDER = "opencode"

# The shape of the `session` table this reader was written against. Bumped when
# a column it depends on moves, so the movement is recorded rather than
# silently misread.
READER_VERSION = 1


def default_db_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return base / "opencode" / "opencode.db"


def _basename(directory: Any) -> str | None:
    """The project name for a working directory, which is what the panel shows."""
    if not directory:
        return None
    text = str(directory).rstrip("/")
    base = os.path.basename(text)
    if base:
        return base
    return text if text else None


def _text_or_none(value: Any) -> str | None:
    """A trimmed string, or None when there is nothing left of it."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _model_of(raw: Any) -> tuple[str | None, str]:
    """(model id, account) from the `model` JSON column.

    Stored as `{"id": "deepseek-v4-flash", "providerID": "opencode-go"}`. A
    value that is not that shape is kept as the model name rather than dropped:
    a model we cannot parse is still the model that ran.
    """
    if not raw:
        return None, ""
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return _text_or_none(raw), ""
    if not isinstance(parsed, dict):
        return _text_or_none(raw), ""
    model = parsed.get("id")
    if not model:
        model = parsed.get("modelID")
    account = parsed.get("providerID")
    if not account:
        account = parsed.get("providerId")
    account_text = _text_or_none(account)
    return _text_or_none(model), (account_text if account_text else "")


def _as_ms(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _seconds(value: Any) -> int | None:
    """Epoch milliseconds → epoch seconds, or None when unreadable."""
    try:
        return int(value) // 1000
    except (TypeError, ValueError):
        return None


class OpenCodeHarvester:
    id = HARVESTER_ID
    provider = PROVIDER

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_db_path()

    def available(self) -> bool:
        return self.path.exists()

    def harvest(self, con: sqlite3.Connection, *, full: bool = False) -> HarvestResult:
        result = HarvestResult(harvester=self.id, provider=self.provider)
        if not self.available():
            result.note = "no local database"
            return result

        since = 0 if full else _as_ms(ledger.watermark(con, self.id)[0])

        try:
            rows, has_messages = self._read(since)
        except sqlite3.Error as exc:
            # Locked by the TUI, or the file moved mid-read. This cycle is a
            # miss; the watermark is untouched, so the next one re-reads it.
            result.failed = True
            result.note = f"skipped: {exc}"
            return result

        sessions = [self._to_row(row, has_messages) for row in rows]
        result.scanned = len(sessions)

        newest = since
        for row in rows:
            newest = max(newest, _as_ms(row["time_updated"]))

        # Rows first, then the rollups, and the watermark last: if anything
        # fails in between, the next run sees the same rows again.
        result.sessions = ledger.upsert_sessions(con, sessions)
        result.folded_days = ledger.fold_days(con, ledger.affected_days(sessions))
        result.watermark = str(newest)
        ledger.set_watermark(
            con,
            self.id,
            result.watermark,
            note=f"read {result.scanned} session(s)",
        )
        ledger.set_reader_format(con, self.id, READER_VERSION)
        return result

    def _read(self, since: int) -> tuple[list[sqlite3.Row], bool]:
        """Rows newer than `since`, plus whether turn counts were available.

        Opened read-only and closed immediately: the TUI is a live writer, so
        the window in which this holds a connection is kept as short as the
        query allows. `mode=ro` (not `immutable=1`) is deliberate — the
        immutable flag would hide a WAL that is still being written.
        """
        read = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=5)
        try:
            read.row_factory = sqlite3.Row
            has_messages = (
                read.execute(
                    "SELECT 1 FROM sqlite_master"
                    " WHERE type = 'table' AND name = 'message' LIMIT 1"
                ).fetchone()
                is not None
            )
            if has_messages:
                rows = read.execute(
                    "SELECT s.id, s.directory, s.model, s.agent, s.cost,"
                    " s.tokens_input, s.tokens_output, s.tokens_reasoning,"
                    " s.tokens_cache_read, s.tokens_cache_write,"
                    " s.time_created, s.time_updated,"
                    " (SELECT COUNT(*) FROM message m WHERE m.session_id = s.id)"
                    " AS turns"
                    " FROM session s WHERE s.time_updated > ?"
                    " ORDER BY s.time_updated ASC",
                    (since,),
                ).fetchall()
            else:
                rows = read.execute(
                    "SELECT s.id, s.directory, s.model, s.agent, s.cost,"
                    " s.tokens_input, s.tokens_output, s.tokens_reasoning,"
                    " s.tokens_cache_read, s.tokens_cache_write,"
                    " s.time_created, s.time_updated, NULL AS turns"
                    " FROM session s WHERE s.time_updated > ?"
                    " ORDER BY s.time_updated ASC",
                    (since,),
                ).fetchall()
            return list(rows), has_messages
        finally:
            read.close()

    def _to_row(self, row: sqlite3.Row, has_messages: bool) -> ledger.SessionRow:
        model, account = _model_of(row["model"])
        started = _seconds(row["time_created"])
        ended = _seconds(row["time_updated"])
        duration = None
        if started is not None and ended is not None:
            duration = max(0, ended - started)

        meta: dict[str, Any] = {}
        if account:
            meta["account"] = account
        if row["agent"]:
            meta["agent"] = str(row["agent"])

        return ledger.SessionRow(
            provider=self.provider,
            source="local-db",
            external_id=str(row["id"]),
            model=model,
            project=_basename(row["directory"]),
            directory=str(row["directory"]) if row["directory"] else None,
            started_at=started,
            ended_at=ended,
            duration_s=duration,
            tokens_input=row["tokens_input"],
            tokens_output=row["tokens_output"],
            tokens_reasoning=row["tokens_reasoning"],
            tokens_cache_read=row["tokens_cache_read"],
            tokens_cache_write=row["tokens_cache_write"],
            cost_usd=row["cost"],
            turns=row["turns"] if has_messages else None,
            meta=meta or None,
        )
