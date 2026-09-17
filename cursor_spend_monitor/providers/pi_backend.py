"""Work out which LLM account a running Pi session is spending against.

Pi is a harness: it holds no subscription of its own and points at whichever
backend the session selected. That backend is recorded in the session log, so
resolving it is a local file read rather than a network call.

Layout, all under ~/.pi/agent:
    settings.json                 defaultProvider / defaultModel
    sessions/<cwd-slug>/*.jsonl   one log per session, newest last
    auth.json                     the accounts Pi can reach (names only are used)

A log line of {"type": "model_change", "provider": ..., "modelId": ...} is
written every time the model is switched, so the last one is what the session
is on now.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

AGENT_DIR = Path.home() / ".pi" / "agent"
SETTINGS_FILE = AGENT_DIR / "settings.json"
SESSIONS_DIR = AGENT_DIR / "sessions"
AUTH_FILE = AGENT_DIR / "auth.json"

# Session logs reach several MB and are re-read on every instance scan, so only
# the tail is parsed. A model change appears near the end of any log whose
# session is still running; if it does not, the settings default is a safe
# answer because that is what Pi itself would have started with.
TAIL_BYTES = 256 * 1024

# Pi's account name → the provider id in this daemon that meters that account.
# An account with no entry here is real and worth naming in the UI, but its
# limits are not reachable, so Pi shows sessions without meters.
METERED_BY = {
    "opencode-go": "opencode",
    "codex": "codex",
    "chatgpt": "codex",
    "chatgpt-codex": "codex",
    "openai-codex": "codex",
}

# Display names for accounts we can name but not always meter.
BACKEND_NAMES = {
    "opencode-go": "OpenCode Go",
    "xai": "xAI",
    "cline": "Cline",
    "codex": "Codex",
    "chatgpt": "Codex",
    "chatgpt-codex": "Codex",
    "openai-codex": "Codex",
}


@dataclass(frozen=True)
class Backend:
    """The account and model one Pi session is spending against."""

    account: str  # Pi's own name for it, e.g. "opencode-go"
    model: str = ""  # e.g. "deepseek-v4-flash"
    provider_id: str = ""  # our provider that meters it, "" when none does

    @property
    def name(self) -> str:
        return BACKEND_NAMES.get(self.account, self.account)

    @property
    def metered(self) -> bool:
        return bool(self.provider_id)

    def to_dict(self) -> dict:
        return {
            "account": self.account,
            "name": self.name,
            "model": self.model,
            "providerId": self.provider_id,
            "metered": self.metered,
        }


def installed() -> bool:
    return AGENT_DIR.is_dir()


def _slug(directory: str) -> str:
    """Pi names a session directory after the cwd, with every "/" as "-".

    /home/me/work  ->  --home-me-work--
    The leading and trailing separators come from wrapping the path in slashes
    before the replacement, which is why both ends carry two dashes.
    """
    return "-" + (directory.rstrip("/") + "/").replace("/", "-") + "-"


def _defaults() -> tuple[str, str]:
    try:
        settings = json.loads(SETTINGS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return "", ""
    return str(settings.get("defaultProvider") or ""), str(
        settings.get("defaultModel") or ""
    )


def accounts() -> list[str]:
    """Account names Pi is signed in to. Values are never read."""
    try:
        auth = json.loads(AUTH_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return [str(key) for key in auth] if isinstance(auth, dict) else []


def _newest_log(directory: str) -> Path | None:
    session_dir = SESSIONS_DIR / _slug(directory)
    newest: Path | None = None
    newest_mtime = -1.0
    try:
        entries = list(session_dir.iterdir())
    except OSError:
        return None
    for entry in entries:
        if entry.suffix != ".jsonl":
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        if mtime > newest_mtime:
            newest, newest_mtime = entry, mtime
    return newest


def _last_model_change(path: Path) -> tuple[str, str] | None:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > TAIL_BYTES:
                handle.seek(size - TAIL_BYTES)
                handle.readline()  # discard the partial line the seek landed in
            tail = handle.read()
    except OSError:
        return None

    for raw in reversed(tail.split(b"\n")):
        if b'"model_change"' not in raw:
            continue
        try:
            record = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if record.get("type") != "model_change":
            continue
        provider = str(record.get("provider") or "")
        if provider:
            return provider, str(record.get("modelId") or "")
    return None


class BackendResolver:
    """Resolves a session's backend, caching on the log's size and mtime.

    The instance scan runs every few seconds and session logs reach several MB,
    so an unchanged log must not be re-read. A log only grows, so (size, mtime)
    is enough to know the cached answer still holds.
    """

    def __init__(self) -> None:
        self._cache: dict[str, tuple[tuple[str, float], Backend]] = {}

    def __call__(self, directory: str) -> Backend | None:
        return self.resolve(directory)

    def resolve(self, directory: str) -> Backend | None:
        if not directory:
            return self._default()

        log = _newest_log(directory)
        if log is None:
            return self._default()

        try:
            stamp = (str(log), log.stat().st_mtime)
        except OSError:
            return self._default()

        cached = self._cache.get(directory)
        if cached is not None and cached[0] == stamp:
            return cached[1]

        found = _last_model_change(log)
        backend = self._backend(*found) if found else self._default()
        if backend is not None:
            self._cache[directory] = (stamp, backend)
        return backend

    def _default(self) -> Backend | None:
        account, model = _defaults()
        if not account:
            return None
        return self._backend(account, model)

    @staticmethod
    def _backend(account: str, model: str) -> Backend:
        return Backend(
            account=account, model=model, provider_id=METERED_BY.get(account, "")
        )


def dominant(backends: list[Backend]) -> Backend | None:
    """The backend that most of the running sessions are on.

    Sessions can sit on different accounts at once. The provider row can only
    show one set of meters, so it shows the account the most sessions are
    spending against; the detail screen still names each session's own.
    """
    if not backends:
        return None
    tally: dict[tuple[str, str], int] = {}
    for backend in backends:
        key = (backend.account, backend.model)
        tally[key] = tally.get(key, 0) + 1
    # Metered accounts win ties: they are the ones that can show a limit.
    best = max(
        tally,
        key=lambda key: (tally[key], bool(METERED_BY.get(key[0]))),
    )
    return Backend(
        account=best[0], model=best[1], provider_id=METERED_BY.get(best[0], "")
    )


__all__ = [
    "AGENT_DIR",
    "Backend",
    "BackendResolver",
    "accounts",
    "dominant",
    "installed",
]
