"""The usage ledger: what the AI spend was actually spent on.

The panel answers "how much is left". This answers "what did it go on" —
tokens per provider, model, project and hour, harvested from the tools' own
stores. It is written to be read by the notification engine, not by an
analyst, so the shape is optimised for a handful of indexed aggregations over a
period rather than for arbitrary queries.

Design decisions worth knowing before changing anything here:

* **Every row is keyed.** `sessions` is unique on `(provider, external_id)`,
  and harvesters upsert, so re-harvesting an unchanged store writes nothing.
  A session that is still running therefore *grows* in place rather than being
  written twice.

* **Token columns are absolute session totals, not increments.** A harvester
  that tails a file must accumulate before calling; passing only the new bytes'
  usage would replace a total with a fragment.

* **`daily`/`hourly` are recomputed, never accumulated.** A live session's
  totals change between harvests, so adding a delta and marking the row folded
  double-counts. Folding deletes the affected day and rebuilds it from
  `sessions`, which is idempotent however many times it runs.

* **`daily` buckets by UTC day, `hourly` by local day.** The design asks for
  time-of-day facts in the user's own timezone and period totals in a stable
  one. The two keys are therefore not the same day string, and `fold_days`
  rebuilds both.

* **Values from a vendor store are untrusted.** Token counts, costs and
  timestamps arrive as whatever JSON/sqlite happened to hold, so they go
  through the `_as_*` helpers: a malformed number becomes zero or NULL instead
  of taking a harvest down.

* **SQL is written as an inline literal at each call site.** No statement is
  built by interpolation, and no statement is passed as a variable — only
  values are bound. This keeps every query auditable by reading it.

* **Storage trouble never takes the daemon down.** Callers that run inside the
  daemon use `LedgerRecorder`, which follows `history.Recorder`: a failure
  disables the ledger for the session and says so once.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

from ..coerce import as_float_or_none as _as_float
from ..coerce import as_int as _as_int
from ..coerce import as_int_or_none as _as_optional_int

# Bumped when a column changes meaning or disappears. A store stamped newer
# than this build is refused by `assert_writable` rather than written blind —
# an older daemon that silently drops a column it does not understand is how
# history gets corrupted.
FORMAT_VERSION = 1

# Long enough to ride out a writer that holds the file briefly. OpenCode's TUI
# writes its own database while we read it, so a short timeout would turn a
# busy moment into a disabled harvester.
BUSY_TIMEOUT_MS = 5000

# Groupings `period_totals` understands. Validated before anything is run; the
# column list is never taken from input.
GROUPINGS = frozenset(
    {"provider", "project", "model", "provider_model", "project_model", "day", "hour"}
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    provider           TEXT    NOT NULL,
    source             TEXT    NOT NULL,   -- api | local-transcript | local-db | estimate
    external_id        TEXT    NOT NULL,   -- the tool's own id
    model              TEXT,
    model_family       TEXT,               -- downcased, de-versioned
    project            TEXT,
    directory          TEXT,
    started_at         INTEGER,            -- epoch s (UTC)
    ended_at           INTEGER,
    duration_s         INTEGER,
    tokens_input       INTEGER NOT NULL DEFAULT 0,
    tokens_output      INTEGER NOT NULL DEFAULT 0,
    tokens_reasoning   INTEGER NOT NULL DEFAULT 0,
    tokens_cache_read  INTEGER NOT NULL DEFAULT 0,
    tokens_cache_write INTEGER NOT NULL DEFAULT 0,
    cost_usd           REAL,
    turns              INTEGER,
    meta               TEXT,               -- json: agent kind, entrypoint, plan…
    content_key        TEXT,               -- hash of the mutable values, for no-op detection
    harvested_at       INTEGER,
    UNIQUE(provider, external_id)
);
CREATE INDEX IF NOT EXISTS idx_sessions_provider_start
    ON sessions(provider, started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);

-- Cursor's cycle-level per-model rows. Cursor reports per billing cycle, not
-- per session, so these are kept apart from `sessions` rather than being
-- decomposed into rows the vendor never gave us.
CREATE TABLE IF NOT EXISTS per_model (
    provider           TEXT NOT NULL,
    model              TEXT NOT NULL,
    cycle_key          TEXT NOT NULL,      -- billing-cycle end
    tokens_input       INTEGER NOT NULL DEFAULT 0,
    tokens_output      INTEGER NOT NULL DEFAULT 0,
    tokens_cache_read  INTEGER NOT NULL DEFAULT 0,
    tokens_cache_write INTEGER NOT NULL DEFAULT 0,
    cost_usd           REAL,
    content_key        TEXT,
    updated_at         INTEGER,
    UNIQUE(provider, model, cycle_key)
);

-- The fast path to "usage against projects over a period", and the input to
-- every digest. `project`/`model` are '' rather than NULL because a UNIQUE
-- constraint does not consider two NULLs equal in SQLite, so a nullable key
-- would silently admit duplicate rows.
CREATE TABLE IF NOT EXISTS daily (
    day                TEXT NOT NULL,      -- YYYY-MM-DD (UTC)
    provider           TEXT NOT NULL,
    project            TEXT NOT NULL DEFAULT '',
    model              TEXT NOT NULL DEFAULT '',
    sessions           INTEGER NOT NULL DEFAULT 0,
    minutes            INTEGER NOT NULL DEFAULT 0,
    tokens             INTEGER NOT NULL DEFAULT 0,  -- all five kinds summed
    cache_read_tokens  INTEGER NOT NULL DEFAULT 0,  -- the subset from cache
    cost_usd           REAL    NOT NULL DEFAULT 0,
    estimated_sessions INTEGER NOT NULL DEFAULT 0,
    UNIQUE(day, provider, project, model)
);
CREATE INDEX IF NOT EXISTS idx_daily_day ON daily(day);
CREATE INDEX IF NOT EXISTS idx_daily_provider ON daily(provider, day);

-- Time-of-day and weekday facts, in the user's own timezone. `day` here is a
-- local day, unlike `daily.day`.
CREATE TABLE IF NOT EXISTS hourly (
    day           TEXT    NOT NULL,        -- YYYY-MM-DD (local)
    hour          INTEGER NOT NULL,        -- 0..23 (local)
    provider      TEXT    NOT NULL DEFAULT '',
    model         TEXT    NOT NULL DEFAULT '',
    minutes       INTEGER NOT NULL DEFAULT 0,
    tokens        INTEGER NOT NULL DEFAULT 0,
    cost_usd      REAL    NOT NULL DEFAULT 0,
    session_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(day, hour, provider, model)
);
CREATE INDEX IF NOT EXISTS idx_hourly_day ON hourly(day, hour);

-- Where each harvester got to. A byte offset for a transcript, a millisecond
-- timestamp for a database, a rowid for a tracking table — the reader decides
-- the encoding, this table only carries it.
CREATE TABLE IF NOT EXISTS harvest_state (
    harvester  TEXT PRIMARY KEY,
    watermark  TEXT,
    note       TEXT,
    updated_at INTEGER
);

-- Cross-checks between two authorities for the same spend. A disagreement is
-- recorded, never used to rewrite a number: the vendor's own figure stays.
CREATE TABLE IF NOT EXISTS checks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at INTEGER NOT NULL,
    provider   TEXT    NOT NULL,
    kind       TEXT    NOT NULL,
    detail     TEXT,
    ok         INTEGER NOT NULL DEFAULT 1
);

-- Generated notifications, which double as the cache and the cooldown key for
-- the notification engine and as the source for `quote` and the panel
-- billboard.
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT    NOT NULL,
    key        TEXT    NOT NULL,
    created_at INTEGER NOT NULL,
    provider   TEXT,
    body       TEXT    NOT NULL,
    share      TEXT,
    meta       TEXT,
    seen_at    INTEGER,                    -- set when the panel has shown it
    UNIQUE(kind, key)                      -- one row per message, ever
);

-- Per-message transcript facts. Claude Code writes one API response as several
-- records (streamed partials share the message id), and a transcript can be
-- re-read after a rotation, so the dedupe key has to outlive a byte offset.
-- Session totals are summed from here, which makes re-reading any file free of
-- double counting.
CREATE TABLE IF NOT EXISTS transcript_messages (
    provider           TEXT NOT NULL,
    message_id         TEXT NOT NULL,
    session_id         TEXT NOT NULL,
    model              TEXT,
    cwd                TEXT,
    entrypoint         TEXT,
    ts                 INTEGER,
    tokens_input       INTEGER NOT NULL DEFAULT 0,
    tokens_cache_write INTEGER NOT NULL DEFAULT 0,
    tokens_cache_read  INTEGER NOT NULL DEFAULT 0,
    tokens_output      INTEGER NOT NULL DEFAULT 0,
    tokens_reasoning   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (provider, message_id)
);
CREATE INDEX IF NOT EXISTS idx_transcript_session
    ON transcript_messages(provider, session_id);

-- Reader format versions, so a vendor schema move is recorded rather than
-- silently misread. Also carries `format_version` for this database itself.
CREATE TABLE IF NOT EXISTS ledger_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class LedgerTooNewError(RuntimeError):
    """The store on disk was written by a newer build than this one."""


# -- coercion ----------------------------------------------------------------
#
# Everything below reads from a store we do not control, so "a number" may be
# a string, a float, null, or absent. These return a usable value or a neutral
# one; none of them raise.


def _epoch_now() -> int:
    try:
        return int(datetime.now(UTC).timestamp())
    except (OSError, OverflowError, ValueError):
        return 0


def _stamp(at: datetime | None = None) -> int:
    """Epoch seconds for `at`, or now. Never raises."""
    if isinstance(at, datetime):
        try:
            return int(at.timestamp())
        except (OSError, OverflowError, ValueError):
            return _epoch_now()
    return _epoch_now()


def _as_json(value: Any) -> str | None:
    if not value:
        return None
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return None


def _utc_from_epoch(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(value), UTC)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _local_from_epoch(value: Any) -> datetime | None:
    try:
        # Naive local time is the point: hour-of-day facts are the user's clock.
        return datetime.fromtimestamp(float(value))  # noqa: DTZ006
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _as_date(value: Any) -> date | None:
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        return None


# -- rows --------------------------------------------------------------------


@dataclass
class SessionRow:
    """One tool-session, with absolute totals.

    `model_family` is left to the harvester when it knows better than
    `model_family_of`; the default is a best-effort de-versioning.
    """

    provider: str
    source: str
    external_id: str
    model: str | None = None
    model_family: str | None = None
    project: str | None = None
    directory: str | None = None
    started_at: int | None = None
    ended_at: int | None = None
    duration_s: int | None = None
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_reasoning: int = 0
    tokens_cache_read: int = 0
    tokens_cache_write: int = 0
    cost_usd: float | None = None
    turns: int | None = None
    meta: dict[str, Any] | None = None

    def family(self) -> str | None:
        return self.model_family or model_family_of(self.model)


@dataclass
class PerModelRow:
    provider: str
    model: str
    cycle_key: str
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_cache_read: int = 0
    tokens_cache_write: int = 0
    cost_usd: float | None = None


@dataclass
class CheckRow:
    provider: str
    kind: str
    detail: str = ""
    ok: bool = True


@dataclass
class TranscriptMessage:
    """One API response read from a transcript, keyed by its `message_id`.

    The fields mirror what a vendor transcript records per assistant turn; the
    ledger turns them into session totals so a reader never has to hold state
    of its own.
    """

    provider: str
    message_id: str
    session_id: str
    model: str | None = None
    cwd: str | None = None
    entrypoint: str | None = None
    ts: int | None = None
    tokens_input: int = 0
    tokens_cache_write: int = 0
    tokens_cache_read: int = 0
    tokens_output: int = 0
    tokens_reasoning: int = 0


def project_of(directory: Any) -> str | None:
    """The project name the panel shows, taken from a working directory."""
    if not directory:
        return None
    text = str(directory).rstrip("/")
    base = os.path.basename(text)
    return base if base else (text or None)


def model_family_of(model: str | None) -> str | None:
    """A stable grouping name for a model id.

    Vendors version ids in different ways, so a trailing purely-numeric segment
    is dropped only when it reads as a version suffix: the segment before it is
    also numeric, or it is an eight-digit date. That groups `claude-opus-5-5`
    as `claude-opus-5` and `claude-3-5-sonnet-20241022` as `claude-3-5-sonnet`,
    while leaving `gpt-5`, `deepseek-v4-flash` and `gpt-5.6-sol` alone — a
    family is never invented by trimming a number that was the name.
    """
    if not model:
        return None
    text = str(model).strip().lower()
    parts = text.split("-")
    if len(parts) < 3:
        return text
    last = parts[-1]
    if last.isdigit() and (parts[-2].isdigit() or len(last) == 8):
        trimmed = "-".join(parts[:-1])
        if trimmed:
            return trimmed
    return text


# -- connection --------------------------------------------------------------


def default_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return base / "tokens-go-brrr" / "usage.db"


def connect(path: Path | None = None, *, prepare: bool = True) -> sqlite3.Connection:
    """Open the ledger, creating it if needed. Never refuses to open.

    A too-new store still opens so `report` can read it; only writing is
    refused, by `assert_writable`.

    `prepare=False` skips the schema, the migrations and the format stamp, for a
    second connection opened while the first already holds them: two connections
    racing the same `ALTER TABLE` is an error, and re-creating the schema on every
    worker connection is waste besides.
    """
    target = path or default_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(target, timeout=BUSY_TIMEOUT_MS / 1000)
    con.row_factory = sqlite3.Row
    if not prepare:
        return con
    # `timeout` above already sets SQLite's busy handler to BUSY_TIMEOUT_MS, so
    # there is no separate `PRAGMA busy_timeout` to issue.
    # WAL keeps the reporting reads from blocking a harvester's write, and vice
    # versa; the daemon and a `report` in a terminal are routinely concurrent.
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(SCHEMA)
    _migrate_messages(con)
    _stamp_format(con)
    con.commit()
    return con


def _migrate_messages(con: sqlite3.Connection) -> None:
    """Bring an older `messages` table up to the current identity rules.

    Two changes have landed here: `seen_at` for durable acknowledgement, and the
    uniqueness narrowed from `(kind, key, created_at)` to `(kind, key)`.

    A `CREATE TABLE IF NOT EXISTS` cannot alter a table that already exists, so
    each change needs a step of its own. This is idempotent, and safe in both
    directions: an older daemon never reads the column, and a newer one upgrades
    the store in place rather than demanding a fresh database or a
    `harvest --full`.
    """
    columns = {row[1] for row in con.execute("PRAGMA table_info(messages)")}
    if "seen_at" not in columns:
        con.execute("ALTER TABLE messages ADD COLUMN seen_at INTEGER")
    if _messages_key_repeats(con):
        _collapse_messages(con)


def _messages_key_repeats(con: sqlite3.Connection) -> bool:
    """True when `messages` still lets one key be stored more than once.

    Read from the table's own DDL: a PRAGMA cannot be parameterised, and what has
    to be spotted is the constraint, not an index name that could be looked up.
    """
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'messages'"
    ).fetchone()
    if row is None:
        return False
    return "unique(kind,key,created_at)" in "".join((row[0] or "").lower().split())


def _collapse_messages(con: sqlite3.Connection) -> None:
    """Rebuild `messages` unique by `(kind, key)`, folding duplicates into one.

    SQLite cannot drop a constraint in place, so this is the table-rebuild dance:
    new table, copy, drop, rename. A timestamp used to be part of the identity, so
    the same logical message generated twice -- which `quote --generate` does on
    every run -- became two rows; and since a dismissal is recorded per row,
    acknowledging the one on screen left the others to be offered again under a
    fresh id.

    The survivor keeps its own id, the newest wording, and is acknowledged if
    *any* of the duplicates was: a dismissal is a statement about the message.
    """
    con.execute("DROP TABLE IF EXISTS messages_rebuilt")
    con.execute(
        "CREATE TABLE messages_rebuilt ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " kind TEXT NOT NULL,"
        " key TEXT NOT NULL,"
        " created_at INTEGER NOT NULL,"
        " provider TEXT,"
        " body TEXT NOT NULL,"
        " share TEXT,"
        " meta TEXT,"
        " seen_at INTEGER,"
        " UNIQUE(kind, key)"
        ")"
    )
    con.execute(
        "INSERT INTO messages_rebuilt"
        " (id, kind, key, created_at, provider, body, share, meta, seen_at)"
        " SELECT m.id, m.kind, m.key, m.created_at, m.provider, m.body, m.share,"
        "        m.meta, g.acked_at"
        "   FROM messages m"
        "   JOIN (SELECT kind, key, MAX(created_at) AS newest,"
        "                MAX(seen_at) AS acked_at"
        "           FROM messages GROUP BY kind, key) g"
        "     ON g.kind = m.kind AND g.key = m.key AND g.newest = m.created_at"
    )
    con.execute("DROP TABLE messages")
    con.execute("ALTER TABLE messages_rebuilt RENAME TO messages")


def _stamp_format(con: sqlite3.Connection) -> None:
    row = con.execute("SELECT value FROM ledger_meta WHERE key = 'format_version'").fetchone()
    if row is None:
        con.execute(
            "INSERT INTO ledger_meta (key, value) VALUES ('format_version', ?)",
            (str(FORMAT_VERSION),),
        )


def stored_format_version(con: sqlite3.Connection) -> int:
    row = con.execute("SELECT value FROM ledger_meta WHERE key = 'format_version'").fetchone()
    found = _as_optional_int(row[0]) if row is not None else None
    return FORMAT_VERSION if found is None else found


def assert_writable(con: sqlite3.Connection) -> None:
    """Raise rather than write a store this build does not fully understand."""
    found = stored_format_version(con)
    if found > FORMAT_VERSION:
        raise LedgerTooNewError(
            f"usage.db is format {found}, this build writes format "
            f"{FORMAT_VERSION}. Upgrade before harvesting."
        )


def set_reader_format(con: sqlite3.Connection, reader: str, version: int) -> None:
    """Record which shape of a vendor's store a reader was written against."""
    con.execute(
        "INSERT OR REPLACE INTO ledger_meta (key, value) VALUES (?, ?)",
        (f"reader.{reader}", str(_as_int(version))),
    )


def reader_format(con: sqlite3.Connection, reader: str) -> int | None:
    row = con.execute(
        "SELECT value FROM ledger_meta WHERE key = ?", (f"reader.{reader}",)
    ).fetchone()
    return _as_optional_int(row[0]) if row is not None else None


# -- writes ------------------------------------------------------------------


def _content_key(*parts: Any) -> str:
    """A short hash of a row's mutable values.

    Re-harvesting an unchanged store must write nothing, and SQLite counts an
    `ON CONFLICT DO UPDATE` as a change even when every value is identical. The
    statement therefore carries a `WHERE` that skips the update unless this key
    differs, which makes the returned row count mean "rows that changed".
    """
    try:
        payload = json.dumps(parts, default=str)
    except (TypeError, ValueError):
        payload = repr(parts)
    return hashlib.blake2b(payload.encode("utf-8", "replace"), digest_size=8).hexdigest()


def _session_values(row: SessionRow, stamp: int) -> tuple:
    """One session as the tuple the INSERT binds, including its content key."""
    source = row.source
    model = row.model
    family = row.family()
    project = row.project
    directory = row.directory
    started_at = _as_optional_int(row.started_at)
    ended_at = _as_optional_int(row.ended_at)
    duration_s = _as_optional_int(row.duration_s)
    tokens_input = _as_int(row.tokens_input)
    tokens_output = _as_int(row.tokens_output)
    tokens_reasoning = _as_int(row.tokens_reasoning)
    tokens_cache_read = _as_int(row.tokens_cache_read)
    tokens_cache_write = _as_int(row.tokens_cache_write)
    cost_usd = _as_float(row.cost_usd)
    turns = _as_optional_int(row.turns)
    meta = _as_json(row.meta)
    key = _content_key(
        source,
        model,
        family,
        project,
        directory,
        started_at,
        ended_at,
        duration_s,
        tokens_input,
        tokens_output,
        tokens_reasoning,
        tokens_cache_read,
        tokens_cache_write,
        cost_usd,
        turns,
        meta,
    )
    return (
        row.provider,
        source,
        row.external_id,
        model,
        family,
        project,
        directory,
        started_at,
        ended_at,
        duration_s,
        tokens_input,
        tokens_output,
        tokens_reasoning,
        tokens_cache_read,
        tokens_cache_write,
        cost_usd,
        turns,
        meta,
        key,
        stamp,
    )


def _per_model_values(row: PerModelRow, stamp: int) -> tuple:
    """One cycle-level row as the tuple the INSERT binds, with its content key."""
    tokens_input = _as_int(row.tokens_input)
    tokens_output = _as_int(row.tokens_output)
    tokens_cache_read = _as_int(row.tokens_cache_read)
    tokens_cache_write = _as_int(row.tokens_cache_write)
    cost_usd = _as_float(row.cost_usd)
    key = _content_key(
        row.provider,
        row.model,
        row.cycle_key,
        tokens_input,
        tokens_output,
        tokens_cache_read,
        tokens_cache_write,
        cost_usd,
    )
    return (
        row.provider,
        row.model,
        row.cycle_key,
        tokens_input,
        tokens_output,
        tokens_cache_read,
        tokens_cache_write,
        cost_usd,
        key,
        stamp,
    )


def upsert_sessions(
    con: sqlite3.Connection,
    rows: Iterable[SessionRow],
    *,
    at: datetime | None = None,
) -> int:
    """Insert or update sessions by `(provider, external_id)`. Returns rows written.

    Token columns are replaced with the values given: they are absolute session
    totals, so a session that grew overwrites its own earlier row. `started_at`
    and `cost_usd` keep an earlier value when the new row omits one, because a
    harness with no cost must not erase a measured one.

    A row whose values are unchanged is not written at all, so the returned
    count is "rows that changed" and a second harvest of an untouched store
    reports zero.
    """
    stamp = _stamp(at)
    # An UPSERT counts as a change even when every value is identical, so the
    # statement carries a WHERE that skips the update unless the content key
    # differs. `total_changes` then answers "rows that changed", which is what
    # a harvest reports.
    before = con.total_changes
    con.executemany(
        "INSERT INTO sessions (provider, source, external_id, model, model_family,"
        " project, directory, started_at, ended_at, duration_s, tokens_input,"
        " tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write,"
        " cost_usd, turns, meta, content_key, harvested_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(provider, external_id) DO UPDATE SET"
        " source = excluded.source,"
        " model = excluded.model,"
        " model_family = excluded.model_family,"
        " project = excluded.project,"
        " directory = excluded.directory,"
        " started_at = COALESCE(excluded.started_at, sessions.started_at),"
        " ended_at = COALESCE(excluded.ended_at, sessions.ended_at),"
        " duration_s = COALESCE(excluded.duration_s, sessions.duration_s),"
        " tokens_input = excluded.tokens_input,"
        " tokens_output = excluded.tokens_output,"
        " tokens_reasoning = excluded.tokens_reasoning,"
        " tokens_cache_read = excluded.tokens_cache_read,"
        " tokens_cache_write = excluded.tokens_cache_write,"
        " cost_usd = COALESCE(excluded.cost_usd, sessions.cost_usd),"
        " turns = COALESCE(excluded.turns, sessions.turns),"
        " meta = excluded.meta,"
        " content_key = excluded.content_key,"
        " harvested_at = excluded.harvested_at"
        " WHERE sessions.content_key IS NOT excluded.content_key",
        [_session_values(row, stamp) for row in rows],
    )
    con.commit()
    return con.total_changes - before


def upsert_per_model(
    con: sqlite3.Connection,
    rows: Iterable[PerModelRow],
    *,
    at: datetime | None = None,
) -> int:
    """Insert or update cycle-level per-model rows. Returns rows written."""
    stamp = _stamp(at)
    before = con.total_changes
    con.executemany(
        "INSERT INTO per_model (provider, model, cycle_key, tokens_input,"
        " tokens_output, tokens_cache_read, tokens_cache_write, cost_usd,"
        " content_key, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(provider, model, cycle_key) DO UPDATE SET"
        " tokens_input = excluded.tokens_input,"
        " tokens_output = excluded.tokens_output,"
        " tokens_cache_read = excluded.tokens_cache_read,"
        " tokens_cache_write = excluded.tokens_cache_write,"
        " cost_usd = COALESCE(excluded.cost_usd, per_model.cost_usd),"
        " content_key = excluded.content_key,"
        " updated_at = excluded.updated_at"
        " WHERE per_model.content_key IS NOT excluded.content_key",
        [_per_model_values(row, stamp) for row in rows],
    )
    con.commit()
    return con.total_changes - before


def ingest_transcript_messages(con: sqlite3.Connection, rows: Iterable[TranscriptMessage]) -> int:
    """Store transcript messages, ignoring ones already seen. Returns new rows.

    `INSERT OR IGNORE` on the message id is what makes re-reading a transcript
    harmless: a repeated record, or a file read again after a rotation, cannot
    double-count a session.
    """
    before = con.total_changes
    con.executemany(
        "INSERT OR IGNORE INTO transcript_messages (provider, message_id,"
        " session_id, model, cwd, entrypoint, ts, tokens_input,"
        " tokens_cache_write, tokens_cache_read, tokens_output,"
        " tokens_reasoning) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                row.provider,
                row.message_id,
                row.session_id,
                row.model,
                row.cwd,
                row.entrypoint,
                _as_optional_int(row.ts),
                _as_int(row.tokens_input),
                _as_int(row.tokens_cache_write),
                _as_int(row.tokens_cache_read),
                _as_int(row.tokens_output),
                _as_int(row.tokens_reasoning),
            )
            for row in rows
        ],
    )
    con.commit()
    return con.total_changes - before


def recompute_transcript_sessions(
    con: sqlite3.Connection,
    *,
    provider: str,
    session_ids: Iterable[str],
    source: str = "local-transcript",
) -> int:
    """Rebuild session rows for transcripts from the deduped message table.

    Summing the messages is what makes the totals absolute: a reader can append
    to a file in pieces without ever needing to remember what it read before,
    and recomputing is idempotent however often it runs.

    Returns how many session rows actually changed, so a harvest that re-read a
    transcript and found nothing new reports zero rather than phantom work.
    """
    rebuilt = 0
    for session_id in sorted({s for s in session_ids if s}):
        agg = con.execute(
            "SELECT MIN(ts), MAX(ts), COUNT(*),"
            " COALESCE(SUM(tokens_input), 0),"
            " COALESCE(SUM(tokens_cache_write), 0),"
            " COALESCE(SUM(tokens_cache_read), 0),"
            " COALESCE(SUM(tokens_output), 0),"
            " COALESCE(SUM(tokens_reasoning), 0)"
            " FROM transcript_messages WHERE provider = ? AND session_id = ?",
            (provider, session_id),
        ).fetchone()
        if agg is None or not _as_int(agg[2]):
            continue
        latest = con.execute(
            "SELECT model, cwd, entrypoint FROM transcript_messages"
            " WHERE provider = ? AND session_id = ? AND ts IS NOT NULL"
            " ORDER BY ts DESC LIMIT 1",
            (provider, session_id),
        ).fetchone()
        started = _as_optional_int(agg[0])
        ended = _as_optional_int(agg[1])
        directory = latest[1] if latest is not None else None
        entrypoint = latest[2] if latest is not None else None
        meta = {"entrypoint": entrypoint} if entrypoint else None
        rebuilt += upsert_sessions(
            con,
            [
                SessionRow(
                    provider=provider,
                    source=source,
                    external_id=session_id,
                    model=latest[0] if latest is not None else None,
                    project=project_of(directory),
                    directory=directory,
                    started_at=started,
                    ended_at=ended,
                    duration_s=(
                        ended - started if started is not None and ended is not None else None
                    ),
                    tokens_input=_as_int(agg[3]),
                    tokens_output=_as_int(agg[6]),
                    tokens_reasoning=_as_int(agg[7]),
                    tokens_cache_read=_as_int(agg[5]),
                    tokens_cache_write=_as_int(agg[4]),
                    turns=_as_int(agg[2]),
                    meta=meta,
                )
            ],
        )
    return rebuilt


def record_check(
    con: sqlite3.Connection,
    row: CheckRow,
    *,
    at: datetime | None = None,
) -> None:
    """Record a cross-check outcome. A disagreement is kept, not corrected."""
    con.execute(
        "INSERT INTO checks (checked_at, provider, kind, detail, ok) VALUES (?, ?, ?, ?, ?)",
        (_stamp(at), row.provider, row.kind, row.detail, 1 if row.ok else 0),
    )
    con.commit()


def set_watermark(
    con: sqlite3.Connection,
    harvester: str,
    watermark: str | None,
    *,
    note: str = "",
    at: datetime | None = None,
) -> None:
    con.execute(
        "INSERT INTO harvest_state (harvester, watermark, note, updated_at)"
        " VALUES (?, ?, ?, ?)"
        " ON CONFLICT(harvester) DO UPDATE SET"
        " watermark = excluded.watermark, note = excluded.note,"
        " updated_at = excluded.updated_at",
        (harvester, watermark, note or None, _stamp(at)),
    )
    con.commit()


def watermark(con: sqlite3.Connection, harvester: str) -> tuple[str | None, str]:
    row = con.execute(
        "SELECT watermark, note FROM harvest_state WHERE harvester = ?",
        (harvester,),
    ).fetchone()
    if row is None:
        return None, ""
    return row[0], row[1] or ""


# -- folding -----------------------------------------------------------------


def utc_day_of(epoch_seconds: float) -> str:
    """The UTC day an epoch lands on, or '' when it cannot be read."""
    moment = _utc_from_epoch(epoch_seconds)
    return moment.strftime("%Y-%m-%d") if moment else ""


def affected_days(rows: Iterable[SessionRow]) -> set[str]:
    """The UTC days a batch of rows lands on, for folding."""
    days: set[str] = set()
    for row in rows:
        stamp = row.started_at if row.started_at is not None else row.ended_at
        day = utc_day_of(stamp) if stamp else ""
        if day:
            days.add(day)
    return days


def _local_days_for(con: sqlite3.Connection, utc_days: Sequence[str]) -> set[str]:
    """Local days that UTC days spill into, so `hourly` can be rebuilt."""
    found: set[str] = set()
    for day in utc_days:
        rows = con.execute(
            "SELECT DISTINCT strftime('%Y-%m-%d', started_at, 'unixepoch', 'localtime')"
            " FROM sessions WHERE started_at IS NOT NULL"
            " AND date(started_at, 'unixepoch') = ?",
            (day,),
        ).fetchall()
        for row in rows:
            if row[0]:
                found.add(row[0])
    return found


def fold_days(con: sqlite3.Connection, days: Iterable[str]) -> int:
    """Rebuild `daily` and `hourly` for the given UTC days. Returns days folded.

    Recompute rather than accumulate, because a session still running changes
    its totals between harvests; deleting the day first makes this idempotent.
    """
    utc_days = sorted({day for day in days if day})
    if not utc_days:
        return 0
    local_days = sorted(_local_days_for(con, utc_days))

    for day in utc_days:
        con.execute("DELETE FROM daily WHERE day = ?", (day,))
    for day in local_days:
        con.execute("DELETE FROM hourly WHERE day = ?", (day,))

    for day in utc_days:
        con.execute(
            "INSERT INTO daily (day, provider, project, model, sessions, minutes,"
            " tokens, cache_read_tokens, cost_usd, estimated_sessions)"
            " SELECT date(started_at, 'unixepoch'), provider,"
            " COALESCE(project, ''), COALESCE(model, ''),"
            " COUNT(*),"
            " COALESCE(SUM(CASE WHEN duration_s > 0 THEN duration_s / 60 ELSE 0 END), 0),"
            " COALESCE(SUM(tokens_input + tokens_output + tokens_reasoning"
            "              + tokens_cache_read + tokens_cache_write), 0),"
            " COALESCE(SUM(tokens_cache_read), 0),"
            " COALESCE(SUM(cost_usd), 0),"
            " COALESCE(SUM(CASE WHEN source = 'estimate' THEN 1 ELSE 0 END), 0)"
            " FROM sessions"
            " WHERE started_at IS NOT NULL"
            " AND date(started_at, 'unixepoch') = ?"
            " GROUP BY date(started_at, 'unixepoch'), provider,"
            " COALESCE(project, ''), COALESCE(model, '')",
            (day,),
        )

    for day in local_days:
        con.execute(
            "INSERT INTO hourly (day, hour, provider, model, minutes, tokens,"
            " cost_usd, session_count)"
            " SELECT strftime('%Y-%m-%d', started_at, 'unixepoch', 'localtime'),"
            " CAST(strftime('%H', started_at, 'unixepoch', 'localtime') AS INTEGER),"
            " provider, COALESCE(model, ''),"
            " COALESCE(SUM(CASE WHEN duration_s > 0 THEN duration_s / 60 ELSE 0 END), 0),"
            " COALESCE(SUM(tokens_input + tokens_output + tokens_reasoning"
            "              + tokens_cache_read + tokens_cache_write), 0),"
            " COALESCE(SUM(cost_usd), 0), COUNT(*)"
            " FROM sessions"
            " WHERE started_at IS NOT NULL"
            " AND strftime('%Y-%m-%d', started_at, 'unixepoch', 'localtime') = ?"
            " GROUP BY 1, 2, 3, 4",
            (day,),
        )

    con.commit()
    return len(utc_days)


def fold_all(con: sqlite3.Connection) -> int:
    """Wipe the rollups and rebuild every day from raw sessions."""
    con.execute("DELETE FROM daily")
    con.execute("DELETE FROM hourly")
    con.commit()
    days = {
        row[0]
        for row in con.execute(
            "SELECT DISTINCT date(started_at, 'unixepoch') FROM sessions"
            " WHERE started_at IS NOT NULL"
        )
        if row[0]
    }
    return fold_days(con, days)


def prune(
    con: sqlite3.Connection,
    *,
    keep_days: int = 90,
    keep_messages_days: int | None = None,
) -> dict[str, int]:
    """Drop raw sessions past retention. Rollups are tiny and stay.

    `daily`/`hourly` outlive the rows they came from so "this month vs last
    month" keeps working long after the underneath sessions are gone.
    """
    removed = {"sessions": 0, "messages": 0, "transcript_messages": 0}
    if keep_days <= 0:
        return removed
    now = _epoch_now()
    cutoff = now - keep_days * 86400
    # A session with no start time cannot be placed in time, so it is kept
    # rather than deleted by a comparison that treats NULL as old.
    cur = con.execute(
        "DELETE FROM sessions WHERE started_at IS NOT NULL AND started_at < ?",
        (cutoff,),
    )
    removed["sessions"] = cur.rowcount or 0

    message_days = keep_days if keep_messages_days is None else keep_messages_days
    cur = con.execute(
        "DELETE FROM messages WHERE created_at < ?",
        (now - message_days * 86400,),
    )
    removed["messages"] = cur.rowcount or 0
    # Whole sessions are dropped together, because a session's totals are summed
    # from its messages: pruning half of one would silently understate it.
    cur = con.execute(
        "DELETE FROM transcript_messages WHERE session_id IN ("
        " SELECT session_id FROM transcript_messages GROUP BY session_id"
        " HAVING MAX(ts) < ?)",
        (cutoff,),
    )
    removed["transcript_messages"] = cur.rowcount or 0
    con.commit()
    return removed


# -- reads -------------------------------------------------------------------


def period_totals(
    con: sqlite3.Connection,
    *,
    start_day: str,
    end_day: str,
    group_by: str = "provider",
    provider: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Totals over a day range, grouped.

    `start_day`/`end_day` are inclusive `YYYY-MM-DD`. Every grouping except
    `hour` keys on UTC days; `hour` keys on local days, matching the `hourly`
    table. Rows come back largest-token-first so callers do not each have to
    sort. `provider=''` means every provider; `limit=None` means no limit.
    """
    if group_by not in GROUPINGS:
        known = ", ".join(sorted(GROUPINGS))
        raise ValueError(f"Unknown grouping {group_by!r}. Known: {known}")
    wanted = provider or ""
    row_limit = _as_int(limit) if limit else -1

    if group_by == "provider":
        cur = con.execute(
            "SELECT provider, SUM(sessions) AS sessions, SUM(minutes) AS minutes,"
            " SUM(tokens) AS tokens, SUM(cache_read_tokens) AS cache_read_tokens,"
            " SUM(cost_usd) AS cost_usd,"
            " SUM(estimated_sessions) AS estimated_sessions"
            " FROM daily WHERE day BETWEEN ? AND ?"
            " AND provider = COALESCE(NULLIF(?, ''), provider)"
            " GROUP BY provider ORDER BY tokens DESC, provider ASC LIMIT ?",
            (start_day, end_day, wanted, row_limit),
        )
    elif group_by == "project":
        cur = con.execute(
            "SELECT project, SUM(sessions) AS sessions, SUM(minutes) AS minutes,"
            " SUM(tokens) AS tokens, SUM(cache_read_tokens) AS cache_read_tokens,"
            " SUM(cost_usd) AS cost_usd,"
            " SUM(estimated_sessions) AS estimated_sessions"
            " FROM daily WHERE day BETWEEN ? AND ?"
            " AND provider = COALESCE(NULLIF(?, ''), provider)"
            " GROUP BY project ORDER BY tokens DESC, project ASC LIMIT ?",
            (start_day, end_day, wanted, row_limit),
        )
    elif group_by == "model":
        cur = con.execute(
            "SELECT model, SUM(sessions) AS sessions, SUM(minutes) AS minutes,"
            " SUM(tokens) AS tokens, SUM(cache_read_tokens) AS cache_read_tokens,"
            " SUM(cost_usd) AS cost_usd,"
            " SUM(estimated_sessions) AS estimated_sessions"
            " FROM daily WHERE day BETWEEN ? AND ?"
            " AND provider = COALESCE(NULLIF(?, ''), provider)"
            " GROUP BY model ORDER BY tokens DESC, model ASC LIMIT ?",
            (start_day, end_day, wanted, row_limit),
        )
    elif group_by == "provider_model":
        cur = con.execute(
            "SELECT provider, model, SUM(sessions) AS sessions,"
            " SUM(minutes) AS minutes, SUM(tokens) AS tokens,"
            " SUM(cache_read_tokens) AS cache_read_tokens,"
            " SUM(cost_usd) AS cost_usd,"
            " SUM(estimated_sessions) AS estimated_sessions"
            " FROM daily WHERE day BETWEEN ? AND ?"
            " AND provider = COALESCE(NULLIF(?, ''), provider)"
            " GROUP BY provider, model"
            " ORDER BY tokens DESC, provider ASC, model ASC LIMIT ?",
            (start_day, end_day, wanted, row_limit),
        )
    elif group_by == "project_model":
        cur = con.execute(
            "SELECT project, model, SUM(sessions) AS sessions,"
            " SUM(minutes) AS minutes, SUM(tokens) AS tokens,"
            " SUM(cache_read_tokens) AS cache_read_tokens,"
            " SUM(cost_usd) AS cost_usd,"
            " SUM(estimated_sessions) AS estimated_sessions"
            " FROM daily WHERE day BETWEEN ? AND ?"
            " AND provider = COALESCE(NULLIF(?, ''), provider)"
            " GROUP BY project, model"
            " ORDER BY tokens DESC, project ASC, model ASC LIMIT ?",
            (start_day, end_day, wanted, row_limit),
        )
    elif group_by == "day":
        cur = con.execute(
            "SELECT day, SUM(sessions) AS sessions, SUM(minutes) AS minutes,"
            " SUM(tokens) AS tokens, SUM(cache_read_tokens) AS cache_read_tokens,"
            " SUM(cost_usd) AS cost_usd,"
            " SUM(estimated_sessions) AS estimated_sessions"
            " FROM daily WHERE day BETWEEN ? AND ?"
            " AND provider = COALESCE(NULLIF(?, ''), provider)"
            " GROUP BY day ORDER BY tokens DESC, day ASC LIMIT ?",
            (start_day, end_day, wanted, row_limit),
        )
    else:  # hour
        cur = con.execute(
            "SELECT day, hour, SUM(session_count) AS sessions,"
            " SUM(minutes) AS minutes, SUM(tokens) AS tokens,"
            " 0 AS cache_read_tokens, SUM(cost_usd) AS cost_usd,"
            " 0 AS estimated_sessions"
            " FROM hourly WHERE day BETWEEN ? AND ?"
            " AND provider = COALESCE(NULLIF(?, ''), provider)"
            " GROUP BY day, hour"
            " ORDER BY tokens DESC, day ASC, hour ASC LIMIT ?",
            (start_day, end_day, wanted, row_limit),
        )
    return [dict(row) for row in cur]


def totals(con: sqlite3.Connection, *, start_day: str, end_day: str) -> dict[str, Any]:
    """One line for the whole period."""
    rows = period_totals(con, start_day=start_day, end_day=end_day, group_by="provider")
    return {
        "start_day": start_day,
        "end_day": end_day,
        "sessions": sum(r["sessions"] for r in rows),
        "minutes": sum(r["minutes"] for r in rows),
        "tokens": sum(r["tokens"] for r in rows),
        "cache_read_tokens": sum(r["cache_read_tokens"] for r in rows),
        "cost_usd": sum(r["cost_usd"] or 0 for r in rows),
        "estimated_sessions": sum(r["estimated_sessions"] for r in rows),
    }


ROLLING_GROUPINGS = frozenset({"provider", "project", "model"})


def rolling_period_totals(
    con: sqlite3.Connection,
    *,
    since: int,
    until: int,
    group_by: str = "provider",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Totals over an epoch-second window, grouped, largest first.

    The day-range queries cannot answer "the last 24 hours": a day is the
    smallest unit they know, so work done at 17:00 is "yesterday" by 08:00 and
    reads as old news. This reads `sessions` directly and places each session by
    when it last had activity (`ended_at`, else `started_at`). A session is
    counted whole in the window it ended in; it is not apportioned across the
    boundary. Cursor reports per billing cycle rather than per session, so it
    has no rows here -- a rolling figure is a statement about sessions.
    """
    if group_by not in ROLLING_GROUPINGS:
        known = ", ".join(sorted(ROLLING_GROUPINGS))
        raise ValueError(f"Unknown rolling grouping {group_by!r}. Known: {known}")
    column = {"provider": "provider", "project": "project", "model": "model"}[group_by]
    row_limit = _as_int(limit) if limit else -1
    cur = con.execute(
        f"SELECT COALESCE({column}, '') AS {column}, COUNT(*) AS sessions,"
        " COALESCE(SUM(duration_s), 0) / 60 AS minutes,"
        " SUM(tokens_input + tokens_output + tokens_reasoning"
        " + tokens_cache_read + tokens_cache_write) AS tokens,"
        " SUM(tokens_cache_read) AS cache_read_tokens,"
        " COALESCE(SUM(cost_usd), 0) AS cost_usd,"
        " SUM(CASE WHEN source = 'estimate' THEN 1 ELSE 0 END)"
        " AS estimated_sessions"
        " FROM sessions"
        " WHERE COALESCE(ended_at, started_at) IS NOT NULL"
        " AND COALESCE(ended_at, started_at) BETWEEN ? AND ?"
        f" GROUP BY {column} ORDER BY tokens DESC, {column} ASC LIMIT ?",
        (since, until, row_limit),
    )
    return [dict(row) for row in cur]


def rolling_totals(con: sqlite3.Connection, *, since: int, until: int) -> dict[str, Any]:
    """One line for a rolling window, shaped like `totals`."""
    rows = rolling_period_totals(con, since=since, until=until, group_by="provider")
    return {
        "since": since,
        "until": until,
        "sessions": sum(r["sessions"] for r in rows),
        "minutes": sum(r["minutes"] for r in rows),
        "tokens": sum(r["tokens"] for r in rows),
        "cache_read_tokens": sum(r["cache_read_tokens"] for r in rows),
        "cost_usd": sum(r["cost_usd"] or 0 for r in rows),
        "estimated_sessions": sum(r["estimated_sessions"] for r in rows),
    }


def sources_in(con: sqlite3.Connection, *, start_day: str, end_day: str) -> list[str]:
    """Which provenance labels contributed to a period.

    Every aggregate can therefore say "includes an estimate" rather than
    presenting a guess with the same face as a measured number.
    """
    rows = con.execute(
        "SELECT DISTINCT source FROM sessions"
        " WHERE started_at IS NOT NULL"
        " AND date(started_at, 'unixepoch') BETWEEN ? AND ?"
        " ORDER BY source",
        (start_day, end_day),
    ).fetchall()
    return [row[0] for row in rows]


def streaks(con: sqlite3.Connection, *, now: datetime | None = None) -> dict[str, Any]:
    """Consecutive days with at least one session, current and longest."""
    today = (now or datetime.now(UTC)).date()
    days: list[date] = []
    for row in con.execute(
        "SELECT DISTINCT date(started_at, 'unixepoch') AS day FROM sessions"
        " WHERE started_at IS NOT NULL ORDER BY day"
    ):
        found = _as_date(row[0])
        if found is not None:
            days.append(found)
    if not days:
        return {"current": 0, "longest": 0, "last_day": None}

    longest = 1
    run = 1
    for previous, current in pairwise(days):
        run = run + 1 if (current - previous).days == 1 else 1
        longest = max(longest, run)

    # The current streak ends today or yesterday; a day not yet finished still
    # counts, but a gap of two days means the streak is over.
    current_streak = 0
    cursor = today
    present = set(days)
    if cursor not in present and (cursor - timedelta(days=1)) in present:
        cursor -= timedelta(days=1)
    while cursor in present:
        current_streak += 1
        cursor -= timedelta(days=1)

    return {
        "current": current_streak,
        "longest": longest,
        "last_day": days[-1].isoformat(),
    }


def records(con: sqlite3.Connection, *, start_day: str, end_day: str) -> dict[str, Any]:
    """The extremes a digest likes to quote: day, session length, session cost."""
    day_row = con.execute(
        "SELECT day, SUM(tokens) AS tokens FROM daily"
        " WHERE day BETWEEN ? AND ? GROUP BY day"
        " ORDER BY tokens DESC LIMIT 1",
        (start_day, end_day),
    ).fetchone()
    long_row = con.execute(
        "SELECT provider, project, model, started_at, duration_s FROM sessions"
        " WHERE started_at IS NOT NULL AND duration_s IS NOT NULL"
        " AND date(started_at, 'unixepoch') BETWEEN ? AND ?"
        " ORDER BY duration_s DESC LIMIT 1",
        (start_day, end_day),
    ).fetchone()
    cost_row = con.execute(
        "SELECT provider, project, model, started_at, cost_usd FROM sessions"
        " WHERE started_at IS NOT NULL AND cost_usd IS NOT NULL"
        " AND date(started_at, 'unixepoch') BETWEEN ? AND ?"
        " ORDER BY cost_usd DESC LIMIT 1",
        (start_day, end_day),
    ).fetchone()
    return {
        "max_tokens_day": dict(day_row) if day_row else None,
        "longest_session": dict(long_row) if long_row else None,
        "costliest_session": dict(cost_row) if cost_row else None,
    }


def cache_share(con: sqlite3.Connection, *, start_day: str, end_day: str) -> dict[str, Any]:
    """How much of the period's token movement came from cache reads."""
    row = con.execute(
        "SELECT COALESCE(SUM(tokens), 0) AS total,"
        " COALESCE(SUM(cache_read_tokens), 0) AS cached FROM daily"
        " WHERE day BETWEEN ? AND ?",
        (start_day, end_day),
    ).fetchone()
    total = _as_int(row["total"]) if row is not None else 0
    cached = _as_int(row["cached"]) if row is not None else 0
    return {
        "tokens": total,
        "cache_read_tokens": cached,
        "share": (cached / total) if total else 0.0,
    }


_DURATION_BUCKETS = (
    ("under 15m", 0, 15 * 60),
    ("15m to 1h", 15 * 60, 3600),
    ("1h to 3h", 3600, 3 * 3600),
    ("over 3h", 3 * 3600, None),
)


def session_shape(con: sqlite3.Connection, *, start_day: str, end_day: str) -> dict[str, Any]:
    """Duration buckets, hour-of-day counts, and the 8-5 weekday share.

    The hour buckets are local, because the question this answers — "when do I
    actually work" — is about the user's clock, not UTC.
    """
    rows = con.execute(
        "SELECT started_at, duration_s FROM sessions"
        " WHERE started_at IS NOT NULL"
        " AND date(started_at, 'unixepoch') BETWEEN ? AND ?",
        (start_day, end_day),
    ).fetchall()

    buckets = {name: 0 for name, _, _ in _DURATION_BUCKETS}
    hours = [0] * 24
    work_hours = 0
    total = 0
    for row in rows:
        total += 1
        local = _local_from_epoch(row["started_at"])
        if local is not None:
            hours[local.hour] += 1
            if local.weekday() < 5 and 8 <= local.hour < 18:
                work_hours += 1
        duration = _as_int(row["duration_s"])
        for name, low, high in _DURATION_BUCKETS:
            if duration >= low and (high is None or duration < high):
                buckets[name] += 1
                break

    return {
        "sessions": total,
        "duration_buckets": buckets,
        "hours": hours,
        "work_hours_sessions": work_hours,
        "work_hours_share": (work_hours / total) if total else 0.0,
    }


def recent_checks(con: sqlite3.Connection, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = con.execute(
        "SELECT checked_at, provider, kind, detail, ok FROM checks"
        " ORDER BY checked_at DESC LIMIT ?",
        (_as_int(limit),),
    ).fetchall()
    return [dict(row) for row in rows]


# -- messages ----------------------------------------------------------------


def latest_message(con: sqlite3.Connection) -> dict[str, Any] | None:
    row = con.execute(
        "SELECT id, kind, key, created_at, provider, body, share, meta, seen_at"
        " FROM messages ORDER BY created_at DESC, id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def recent_messages(con: sqlite3.Connection, *, limit: int = 8) -> list[dict[str, Any]]:
    """The newest messages regardless of acknowledgement, for "Earlier insights"."""
    rows = con.execute(
        "SELECT id, kind, key, created_at, provider, body, share, meta, seen_at"
        " FROM messages ORDER BY created_at DESC, id DESC LIMIT ?",
        (_as_int(limit),),
    ).fetchall()
    return [dict(row) for row in rows]


def pending_messages(con: sqlite3.Connection, *, limit: int = 20) -> list[dict[str, Any]]:
    """Unacknowledged messages, newest first, for the landing page to choose from.

    Freshness is deliberately not applied here: how long a message stays worth
    interrupting for depends on its kind, which is a wording-layer concern. This
    returns everything unread and lets `notify_engine.choose_billboard` decide.
    """
    rows = con.execute(
        "SELECT id, kind, key, created_at, provider, body, share, meta"
        " FROM messages WHERE seen_at IS NULL"
        " ORDER BY created_at DESC, id DESC LIMIT ?",
        (_as_int(limit),),
    ).fetchall()
    return [dict(row) for row in rows]


def mark_message_seen(
    con: sqlite3.Connection, message_id: int, *, at: datetime | None = None
) -> int:
    """Mark a message read so the panel stops offering it. Rows changed.

    Only ever sets the column, never clears it, so a dismissal survives a logout
    and an extension reload.
    """
    cur = con.execute(
        "UPDATE messages SET seen_at = ? WHERE id = ? AND seen_at IS NULL",
        (_stamp(at), _as_int(message_id)),
    )
    con.commit()
    return cur.rowcount or 0


def store_message(
    con: sqlite3.Connection,
    *,
    kind: str,
    key: str,
    body: str,
    provider: str | None = None,
    share: str | None = None,
    meta: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> int:
    """Cache a generated message and return its id.

    One row per `(kind, key)`, so re-stating a message updates it in place. It
    used to insert a second row whenever the same message was generated in a
    different second, and because acknowledgement is recorded per row, dismissing
    the one on screen left the rest for the panel to offer again.

    `seen_at` is deliberately not in the update: an acknowledgement is a
    statement about the message, not about that moment's wording.
    """
    stamp = _stamp(at)
    con.execute(
        "INSERT INTO messages (kind, key, created_at, provider, body, share, meta)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(kind, key) DO UPDATE SET"
        " created_at = excluded.created_at,"
        " provider = excluded.provider,"
        " body = excluded.body,"
        " share = excluded.share,"
        " meta = excluded.meta",
        (kind, key, stamp, provider, body, share, _as_json(meta)),
    )
    con.commit()
    row = con.execute(
        "SELECT id FROM messages WHERE kind = ? AND key = ?",
        (kind, key),
    ).fetchone()
    return _as_int(row[0]) if row is not None else 0


def last_generated_at(con: sqlite3.Connection, *, kind: str, key_prefix: str) -> int | None:
    """When any message of this kind whose key starts with `key_prefix` was made.

    A prefix, not a key: rotating messages carry the day in their key so that a
    fresh one is a new row (acknowledging an old row would otherwise hide it for
    good), and "when did this one last speak" has to look across those days.
    """
    row = con.execute(
        "SELECT MAX(created_at) FROM messages WHERE kind = ? AND substr(key, 1, ?) = ?",
        (kind, len(key_prefix), key_prefix),
    ).fetchone()
    return _as_optional_int(row[0]) if row is not None else None


def weekday_counts(con: sqlite3.Connection, *, start_day: str, end_day: str) -> list[int]:
    """Sessions per local weekday, Monday first, over a UTC day range."""
    counts = [0] * 7
    for row in con.execute(
        "SELECT started_at FROM sessions WHERE started_at IS NOT NULL"
        " AND date(started_at, 'unixepoch') BETWEEN ? AND ?",
        (start_day, end_day),
    ):
        local = _local_from_epoch(row["started_at"])
        if local is not None:
            counts[local.weekday()] += 1
    return counts


def last_message_age(con: sqlite3.Connection, *, kind: str, key: str) -> int | None:
    """Seconds since this `(kind, key)` was last generated, or None."""
    row = con.execute(
        "SELECT MAX(created_at) FROM messages WHERE kind = ? AND key = ?",
        (kind, key),
    ).fetchone()
    if row is None:
        return None
    stamp = _as_optional_int(row[0])
    if stamp is None:
        return None
    return _epoch_now() - stamp


# -- presentation helpers ----------------------------------------------------


def format_tokens(value: float | None) -> str:
    number = _as_float(value) or 0.0
    if not number:
        return "0"
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(number) >= limit:
            scaled = number / limit
            return f"{scaled:.1f}{suffix}".replace(".0" + suffix, suffix)
    return str(_as_int(number))


def format_cost(value: float | None) -> str:
    number = _as_float(value)
    if number is None:
        return "—"
    return f"${number:,.2f}"


def _ledger_api():
    """The public ``tokens_go_brrr.ledger`` package (patchable in tests)."""
    from tokens_go_brrr import ledger as api

    return api


class LedgerRecorder:
    """Daemon-side wrapper that never lets a storage problem stop monitoring.

    Mirrors `history.Recorder`: the panel is the product, so a locked or
    unwritable database disables the ledger for the session and says so once.
    """

    def __init__(self, path: Path | None = None, *, keep_days: int = 90) -> None:
        self.keep_days = keep_days
        # Kept so a worker thread can open its own connection to the same store.
        api = _ledger_api()
        self._path = path or api.default_path()
        self._con: sqlite3.Connection | None = None
        self._failed = False
        try:
            self._con = api.connect(self._path)
            api.assert_writable(self._con)
            api.prune(self._con, keep_days=keep_days)
        except LedgerTooNewError as exc:
            self._disable(str(exc))
        except (sqlite3.Error, OSError) as exc:
            self._disable(f"Could not open the usage ledger: {exc}")

    @property
    def active(self) -> bool:
        return self._con is not None and not self._failed

    @property
    def connection(self) -> sqlite3.Connection | None:
        return self._con

    @contextlib.contextmanager
    def worker(self) -> Iterator[sqlite3.Connection | None]:
        """A connection for a worker thread, closed when the block ends.

        A `sqlite3.Connection` belongs to the thread that created it, so a worker
        must not borrow the main loop's. Doing that made every harvest fail with
        "SQLite objects created in a thread can only be used in that same
        thread", and the ledger quietly stopped filling while the panel still
        looked perfectly healthy. A second connection is the supported model, and
        WAL lets it read and write alongside the first -- which is what the busy
        timeout is for.

        Opened unprepared, because the main connection has already created the
        schema and run the migrations, and two connections racing the same
        `ALTER TABLE` is an error rather than a no-op.
        """
        if not self.active:
            yield None
            return
        api = _ledger_api()
        con: sqlite3.Connection | None = None
        try:
            con = api.connect(self._path, prepare=False)
        except LedgerTooNewError as exc:
            self._disable(str(exc))
        except (sqlite3.Error, OSError) as exc:
            self._disable(f"Could not open the usage ledger: {exc}")
        try:
            yield con
        finally:
            if con is not None:
                con.close()

    def _disable(self, message: str) -> None:
        if not self._failed:
            print(message, file=sys.stderr, flush=True)
        self._failed = True
        self._con = None

    def _guard(self, action, fallback):
        if not self.active:
            return fallback
        try:
            return action(self._con)
        except (sqlite3.Error, OSError, TypeError, ValueError) as exc:
            self._disable(f"Usage ledger disabled: {exc}")
            return fallback

    def upsert_sessions(self, rows: Iterable[SessionRow], **kwargs) -> int:
        api = _ledger_api()
        return self._guard(lambda con: api.upsert_sessions(con, rows, **kwargs), 0)

    def upsert_per_model(self, rows: Iterable[PerModelRow], **kwargs) -> int:
        api = _ledger_api()
        return self._guard(lambda con: api.upsert_per_model(con, rows, **kwargs), 0)

    def fold_days(self, days: Iterable[str]) -> int:
        api = _ledger_api()
        return self._guard(lambda con: api.fold_days(con, days), 0)

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None
