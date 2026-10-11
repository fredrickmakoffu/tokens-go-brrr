"""A daily log of every call made to a language model.

Transparency, not analytics: the person can open a day and see what was sent,
to whom, what it cost and what came back. See design/LIVE_NOTES_AND_LLM_LOG.md.

One file per local day, `llm-calls/YYYY-MM-DD.jsonl`, one JSON object per line
in time order, each leading with its own timestamp. JSONL keeps an append
atomic and cheap, needs no migrations and is trivially greppable. A write that
fails must never fail the call or the note it belongs to, so every public
method swallows its own errors after one line on stderr.

What is logged is what was already sent: `build_prompt` only ever contains
aggregate figures, so the log gains no field the prompt does not have. Auth
headers and tokens are never an input here, and error text is scrubbed anyway.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_KEEP_DAYS = 30

# Outcomes an entry may carry.
OK = "ok"
RATE_LIMITED = "rate_limited"
ERROR = "error"
TIMEOUT = "timeout"
SKIPPED = "skipped"

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Anything that looks like a credential is cut out of free text before it is
# written. The recorder is never handed a header, so this is a second lock on a
# door that should already be shut.
_SECRETS = re.compile(
    r"(?i)(bearer\s+[A-Za-z0-9._~+/=-]+"
    r"|sk-[A-Za-z0-9_-]{8,}"
    r"|(?:api[_-]?key|token|authorization)[\"'=:\s]+[A-Za-z0-9._~+/=-]{8,})"
)


def default_dir() -> Path:
    """Next to `usage.db`, which is where the rest of the user's data lives."""
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return base / "tokens-go-brrr" / "llm-calls"


def scrub(text: Any, *, limit: int = 400) -> str:
    """Free text with anything credential-shaped removed, and a length cap."""
    cleaned = _SECRETS.sub("[redacted]", str(text or ""))
    return cleaned[:limit]


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def _warn(message: str) -> None:
    print(f"LLM log: {message}", file=sys.stderr, flush=True)


class LlmLog:
    """Append-only daily log. `keep_days` of 0 turns the log off entirely."""

    def __init__(
        self, directory: Path | None = None, *, keep_days: int = DEFAULT_KEEP_DAYS
    ) -> None:
        self.directory = directory or default_dir()
        self.keep_days = max(0, _as_int(keep_days))
        # Worker threads compose notes concurrently; one lock keeps a line whole.
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.keep_days > 0

    # -- writing ---------------------------------------------------------------

    def record(self, entry: dict[str, Any], *, at: datetime | None = None) -> None:
        """Append one call. Never raises."""
        if not self.enabled:
            return
        try:
            moment = (at or datetime.now()).astimezone()
            line = {"ts": moment.isoformat(timespec="seconds"), **entry}
            if "error" in line:
                line["error"] = scrub(line["error"])
            payload = json.dumps(line, ensure_ascii=False, separators=(",", ":"))
            with self._lock:
                self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                path = self.directory / f"{moment.date().isoformat()}.jsonl"
                # The prompts are the user's own figures; keep the file theirs.
                fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                with os.fdopen(fd, "a", encoding="utf-8") as handle:
                    handle.write(payload + "\n")
        except (OSError, TypeError, ValueError) as exc:
            _warn(f"could not write an entry: {exc}")

    # -- reading ---------------------------------------------------------------

    def days(self) -> list[str]:
        """Days that have a file, newest first."""
        try:
            names = [p.stem for p in self.directory.glob("*.jsonl")]
        except OSError:
            return []
        return sorted((n for n in names if _DAY.match(n)), reverse=True)

    def read(self, day: str) -> list[dict[str, Any]]:
        """One day's entries in time order. A bad day or file reads as empty."""
        if not _DAY.match(str(day or "")):
            return []
        path = self.directory / f"{day}.jsonl"
        entries: list[dict[str, Any]] = []
        try:
            with open(path, encoding="utf-8") as handle:
                for raw in handle:
                    try:
                        parsed = json.loads(raw)
                    except ValueError:
                        continue  # a torn last line from a crash
                    if isinstance(parsed, dict):
                        entries.append(parsed)
        except OSError:
            return []
        return entries

    def summary(self, day: str) -> dict[str, Any]:
        """The header line for a day: calls, tokens and failures."""
        entries = self.read(day)
        made = [e for e in entries if e.get("outcome") != SKIPPED]
        return {
            "day": day,
            "calls": len(made),
            "skipped": len(entries) - len(made),
            "failures": sum(1 for e in made if e.get("outcome") != OK),
            "tokens_in": sum(_as_int(e.get("tokens_in")) for e in made),
            "tokens_out": sum(_as_int(e.get("tokens_out")) for e in made),
        }

    # -- upkeep ----------------------------------------------------------------

    def prune(self, *, today: datetime | None = None) -> int:
        """Delete day files older than `keep_days`. Returns how many went."""
        if not self.enabled:
            return 0
        cutoff = (today or datetime.now()).astimezone().date().toordinal() - (
            self.keep_days - 1
        )
        removed = 0
        for day in self.days():
            try:
                if datetime.strptime(day, "%Y-%m-%d").date().toordinal() < cutoff:
                    (self.directory / f"{day}.jsonl").unlink()
                    removed += 1
            except (OSError, ValueError) as exc:
                _warn(f"could not prune {day}: {exc}")
        return removed

    def clear(self) -> int:
        """Delete every day file. Returns how many went."""
        removed = 0
        with self._lock:
            for day in self.days():
                try:
                    (self.directory / f"{day}.jsonl").unlink()
                    removed += 1
                except OSError as exc:
                    _warn(f"could not delete {day}: {exc}")
        return removed

    def report(self) -> str:
        """Every kept day as one readable document, newest day first."""
        days = self.days()
        out = [
            "LLM ACTIVITY LOG",
            "Every call this app has made to a language model.",
            f"Kept for {self.keep_days} days. Raw files: {self.directory}",
            f"Generated {datetime.now().astimezone().isoformat(timespec='seconds')}",
        ]
        if not self.enabled:
            out += ["", "The log is switched off (llm_log_days is 0 in the config)."]
        elif not days:
            out += ["", "No model calls have been made yet."]
        for day in days:
            s = self.summary(day)
            out += [
                "",
                "=" * 72,
                f"{day}   {s['calls']} calls, {s['failures']} failed, "
                f"{s['skipped']} skipped, {_fmt_tokens(s['tokens_in'])} tokens in, "
                f"{_fmt_tokens(s['tokens_out'])} out",
                "=" * 72,
            ]
            for entry in reversed(self.read(day)):
                out += ["", render_entry(entry)]
        return "\n".join(out) + "\n"

    def write_report(self, path: Path | None = None) -> Path:
        """Write `report()` to a text file (private) and return its path."""
        target = path or self.directory.parent / "llm-activity.txt"
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._lock:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(self.report())
        return target

    def payload(self, day: str | None = None) -> dict[str, Any]:
        """Everything the Settings screen needs for one day, as JSON-able data."""
        days = self.days()
        chosen = day if day and _DAY.match(day) else (days[0] if days else "")
        return {
            "enabled": self.enabled,
            "keep_days": self.keep_days,
            "directory": str(self.directory),
            "days": days,
            "day": chosen,
            "summary": self.summary(chosen) if chosen else None,
            "entries": self.read(chosen) if chosen else [],
        }


def _fmt_tokens(value: Any) -> str:
    return f"{_as_int(value):,}"


def _indent(text: Any, pad: str = "      ") -> str:
    return "\n".join(pad + line for line in str(text).splitlines() or [""])


def render_entry(entry: dict[str, Any]) -> str:
    """One call as a block of plain text: who, which model, what it cost."""
    time = str(entry.get("ts", ""))[11:19] or "--:--:--"
    outcome = str(entry.get("outcome", "?"))
    head = f"{time}  {outcome.upper()}"
    if entry.get("trigger"):
        head += f"  (trigger: {entry['trigger']})"
    lines = [head]
    fields = [
        ("Provider", entry.get("provider")),
        ("Model", entry.get("model")),
        ("Reason", entry.get("reason")),
        ("Message", entry.get("message_kind")),
        ("Message key", entry.get("message_key")),
    ]
    if entry.get("latency_ms") is not None:
        fields.append(("Latency", f"{_as_int(entry['latency_ms']):,} ms"))
    if entry.get("tokens_in") is not None:
        fields.append(("Tokens in", _fmt_tokens(entry["tokens_in"])))
    if entry.get("tokens_out") is not None:
        fields.append(("Tokens out", _fmt_tokens(entry["tokens_out"])))
    lines += [f"    {name + ':':<13}{value}" for name, value in fields if value]
    for title, key in (("Prompt", "prompt"), ("Reply", "reply"), ("Error", "error")):
        if entry.get(key):
            lines += [f"    {title}:", _indent(entry[key])]
    return "\n".join(lines)


__all__ = [
    "DEFAULT_KEEP_DAYS",
    "ERROR",
    "LlmLog",
    "OK",
    "RATE_LIMITED",
    "SKIPPED",
    "TIMEOUT",
    "default_dir",
    "scrub",
]
