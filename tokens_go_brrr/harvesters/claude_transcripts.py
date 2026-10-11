"""Read Claude Code's transcripts into the ledger.

`~/.claude/projects/<slug>/<sessionId>.jsonl` is the richest local source the
ledger has: every assistant record carries the full usage block — including the
cache split and thinking tokens — plus the model, the working directory and a
timestamp. The claude.ai usage page is a strict subset of these files.

Two shapes of that store make a naive reader wrong, and this one is built around
both:

* **One response, several records.** A streamed message is written as more than
  one line sharing a `message.id` — in the largest file here, 1 296 usage
  records stand for 691 responses. Summing lines inflates a session by ~1.9x.
  The reader dedupes by message id *in the ledger* rather than in memory,
  because the key has to outlive a byte offset for a re-read to stay harmless.

* **Subagent transcripts are separate files.** Work done by a subagent is
  written to `<sessionId>/subagents/agent-*.jsonl` and billed to the same
  session, so the reader walks the whole tree and attributes those messages to
  the parent session rather than inventing a session per agent.

Because session totals are summed from the deduped messages, the byte offset is
only an optimisation: if a file is rotated and read again, `INSERT OR IGNORE`
absorbs it and the recomputed totals are identical.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import ledger
from ..coerce import as_int as _as_int
from .base import HarvestResult

HARVESTER_ID = "claude_jsonl"
PROVIDER = "claude"

# The shape of a transcript record this reader understands. Bumped when a field
# it depends on moves, so the movement is recorded rather than misread.
READER_VERSION = 1
STATE_VERSION = 1


def default_root() -> Path:
    return Path.home() / ".claude" / "projects"


def _parse_ts(value: Any) -> int | None:
    """An ISO-8601 transcript timestamp as epoch seconds, or None."""
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    try:
        return int(moment.timestamp())
    except (OSError, OverflowError, ValueError):
        return None


def _session_id(record: dict[str, Any], path: Path, root: Path) -> str:
    """The session a transcript belongs to.

    Records normally name it outright. When they do not, the layout does: a
    top-level file is named for its session, and a subagent file sits under the
    session directory it was spawned from.
    """
    named = record.get("sessionId") or record.get("session_id")
    if named:
        return str(named)
    try:
        relative = path.relative_to(root)
    except ValueError:
        return path.stem
    if relative.parent.name == "subagents":
        return relative.parent.parent.name
    return path.stem


def _message_of(
    record: dict[str, Any], session_id: str, provider: str
) -> ledger.TranscriptMessage | None:
    """The usage one transcript record describes, or None if it has none."""
    if record.get("type") != "assistant":
        return None
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    message_id = message.get("id") or record.get("requestId")
    if not message_id:
        return None
    details = usage.get("output_tokens_details")
    thinking = details.get("thinking_tokens") if isinstance(details, dict) else 0
    return ledger.TranscriptMessage(
        provider=provider,
        message_id=str(message_id),
        session_id=session_id,
        model=message.get("model"),
        cwd=record.get("cwd"),
        entrypoint=record.get("entrypoint"),
        ts=_parse_ts(record.get("timestamp")),
        tokens_input=usage.get("input_tokens") or 0,
        tokens_cache_write=usage.get("cache_creation_input_tokens") or 0,
        tokens_cache_read=usage.get("cache_read_input_tokens") or 0,
        tokens_output=usage.get("output_tokens") or 0,
        tokens_reasoning=thinking or 0,
    )


class ClaudeTranscriptHarvester:
    id = HARVESTER_ID
    provider = PROVIDER

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_root()

    def available(self) -> bool:
        return self.root.is_dir()

    def harvest(self, con: sqlite3.Connection, *, full: bool = False) -> HarvestResult:
        result = HarvestResult(harvester=self.id, provider=self.provider)
        if not self.available():
            result.note = "no transcripts"
            return result

        previous = {} if full else self._load_offsets(con)
        offsets: dict[str, dict[str, int]] = {}
        messages: list[ledger.TranscriptMessage] = []
        skipped = 0

        for path in sorted(self.root.glob("**/*.jsonl")):
            key = str(path)
            size = self._size_of(path)
            if size is None:
                skipped += 1
                continue
            start = self._start_offset(previous.get(key), size)
            if start >= size:
                # Unchanged since last time. Its offset is carried forward so a
                # later append is still read from the right place.
                offsets[key] = {"size": size, "offset": start}
                continue
            try:
                records, consumed = self._read_new(path, start)
            except OSError:
                skipped += 1
                offsets[key] = {"size": size, "offset": start}
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                session_id = _session_id(record, path, self.root)
                message = _message_of(record, session_id, self.provider)
                if message is not None:
                    messages.append(message)
            offsets[key] = {"size": size, "offset": consumed}

        result.scanned = len(messages)
        ledger.ingest_transcript_messages(con, messages)
        sessions = {message.session_id for message in messages}
        result.sessions = ledger.recompute_transcript_sessions(
            con, provider=self.provider, session_ids=sessions
        )
        result.folded_days = ledger.fold_days(
            con,
            {ledger.utc_day_of(message.ts) for message in messages if message.ts},
        )
        result.watermark = str(len(offsets))
        ledger.set_watermark(
            con,
            self.id,
            json.dumps({"v": STATE_VERSION, "files": offsets}),
            note=f"read {result.scanned} message(s) from {len(offsets)} file(s)",
        )
        ledger.set_reader_format(con, self.id, READER_VERSION)
        if skipped and not messages:
            result.note = f"{skipped} transcript(s) unreadable"
        return result

    # -- transcript files ----------------------------------------------------

    @staticmethod
    def _size_of(path: Path) -> int | None:
        try:
            return path.stat().st_size
        except OSError:
            return None

    @staticmethod
    def _start_offset(stored: dict[str, int] | None, size: int) -> int:
        """Where to resume a file.

        A file smaller than the offset we hold was rotated or rewritten, so it
        is read from the start — which is safe, because the ledger dedupes by
        message id and the totals are recomputed rather than added to.
        """
        if not stored:
            return 0
        start = _as_int(stored.get("offset", 0))
        return start if start <= size else 0

    @staticmethod
    def _read_new(path: Path, start: int) -> tuple[list[Any], int]:
        """Complete records from `start` on, and the offset past the last one.

        A partial trailing line is left unconsumed so the next read sees it
        whole; taking the file's end instead would drop a record written while
        this was running.
        """
        with path.open("rb") as handle:
            handle.seek(start)
            data = handle.read()
        if not data:
            return [], start
        lines = data.split(b"\n")
        consumed = len(data)
        if not data.endswith(b"\n"):
            partial = lines.pop()
            consumed = len(data) - len(partial)
        records = []
        for line in lines:
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except (TypeError, ValueError, UnicodeDecodeError):
                continue
        return records, start + consumed

    def _load_offsets(self, con: sqlite3.Connection) -> dict[str, dict[str, int]]:
        raw, _note = ledger.watermark(con, self.id)
        if not raw:
            return {}
        try:
            state = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        if not isinstance(state, dict):
            return {}
        files = state.get("files")
        return files if isinstance(files, dict) else {}
