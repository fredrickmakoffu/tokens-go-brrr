"""Read Codex's local thread store, when it has anything to read.

On this machine it does not. `~/.codex/state_5.sqlite` has an empty `threads`
table and `logs_2.sqlite` carries no token fields, so Codex contributes no
ledger rows today. The reader exists anyway, as the design asks, because the
store is one schema change away from having the data — and a reader that records
what it actually found is how that change gets noticed rather than silently
missed.

It never guesses. With no recognisable token column it writes nothing and
records the columns it did see as a cross-check, so "Codex shows no usage" is a
statement about evidence rather than an absence of effort.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .. import ledger
from ..coerce import as_int as _as_int
from ..coerce import as_int_or_none as _as_optional_int
from .base import HarvestResult

HARVESTER_ID = "codex_state"
PROVIDER = "codex"

# The shape this reader was written against: the design's target field names.
READER_VERSION = 1

# Column names that would carry each value, most specific first. The store has
# moved schema four times already, so nothing is assumed to exist.
TOKEN_COLUMNS = ("tokens_used", "total_tokens", "tokens")
MODEL_COLUMNS = ("model",)
PROVIDER_COLUMNS = ("model_provider", "provider")
DIRECTORY_COLUMNS = ("cwd", "working_directory")
ID_COLUMNS = ("id", "thread_id", "conversation_id")
CREATED_COLUMNS = ("created_at", "created", "time_created")
UPDATED_COLUMNS = ("updated_at", "updated", "time_updated")


def default_db_path() -> Path:
    return Path.home() / ".codex" / "state_5.sqlite"


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _pick(row: Any, index_of: dict[str, int], candidates: tuple[str, ...]) -> Any:
    """The first of `candidates` this row has, by position."""
    for name in candidates:
        index = index_of.get(name)
        if index is not None:
            return row[index]
    return None


def _seconds(value: Any) -> int | None:
    """Epoch seconds or milliseconds — Codex has used both."""
    stamp = _as_optional_int(value)
    if stamp is None:
        return None
    return stamp // 1000 if stamp > 10**11 else stamp


class CodexStateHarvester:
    id = HARVESTER_ID
    provider = PROVIDER

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_db_path()

    def available(self) -> bool:
        return self.path.exists()

    def harvest(self, con: sqlite3.Connection, *, full: bool = False) -> HarvestResult:
        result = HarvestResult(harvester=self.id, provider=self.provider)
        if not self.available():
            result.note = "no local store"
            return result

        try:
            index_of = self._columns()
        except sqlite3.Error as exc:
            result.failed = True
            result.note = f"skipped: {exc}"
            return result

        token_column = next((name for name in TOKEN_COLUMNS if name in index_of), None)
        if token_column is None:
            ledger.record_check(
                con,
                ledger.CheckRow(
                    provider=self.provider,
                    kind="threads_schema",
                    detail=f"threads columns {sorted(index_of)}; no token column yet",
                    ok=True,
                ),
            )
            ledger.set_reader_format(con, self.id, READER_VERSION)
            result.note = "no token column in the local thread store"
            return result

        try:
            rows = self._read(index_of, token_column)
        except sqlite3.Error as exc:
            result.failed = True
            result.note = f"skipped: {exc}"
            return result

        result.scanned = len(rows)
        result.sessions = ledger.upsert_sessions(con, rows)
        result.folded_days = ledger.fold_days(con, ledger.affected_days(rows))
        ledger.set_reader_format(con, self.id, READER_VERSION)
        ledger.set_watermark(
            con, self.id, str(result.sessions), note=f"read {result.scanned} thread(s)"
        )
        return result

    def _columns(self) -> dict[str, int]:
        """Column name → position, read straight from the store's own schema."""
        read = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=5)
        try:
            return {
                row[1]: row[0] for row in read.execute("PRAGMA table_info(threads)")
            }
        finally:
            read.close()

    def _read(
        self, index_of: dict[str, int], token_column: str
    ) -> list[ledger.SessionRow]:
        read = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=5)
        try:
            read.row_factory = sqlite3.Row
            raw = read.execute("SELECT * FROM threads").fetchall()
        finally:
            read.close()

        rows: list[ledger.SessionRow] = []
        for position, entry in enumerate(raw):
            identifier = (
                _text(_pick(entry, index_of, ID_COLUMNS)) or f"thread-{position}"
            )
            started = _seconds(_pick(entry, index_of, CREATED_COLUMNS))
            ended = _seconds(_pick(entry, index_of, UPDATED_COLUMNS))
            directory = _text(_pick(entry, index_of, DIRECTORY_COLUMNS))
            account = _text(_pick(entry, index_of, PROVIDER_COLUMNS))
            duration = None
            if started is not None and ended is not None and ended >= started:
                duration = ended - started
            rows.append(
                ledger.SessionRow(
                    provider=self.provider,
                    source="local-db",
                    external_id=identifier,
                    model=_text(_pick(entry, index_of, MODEL_COLUMNS)),
                    project=ledger.project_of(directory),
                    directory=directory,
                    started_at=started,
                    ended_at=ended,
                    duration_s=duration,
                    # Codex reports one figure, not a split, so it is recorded as
                    # input and the rest stay zero rather than being distributed.
                    tokens_input=_as_int(entry[index_of[token_column]]),
                    meta={"account": account} if account else None,
                )
            )
        return rows
