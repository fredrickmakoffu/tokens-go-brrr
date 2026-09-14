"""Detect running sessions of each AI coding tool.

A session is one process the user started: a terminal agent, or a desktop app.
Providers describe what to look for with ProcessSpec; nothing here knows about
any particular tool.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROC = Path("/proc")
_CLOCK_TICKS = os.sysconf("SC_CLK_TCK")

# /proc/<pid>/stat field 3, as documented in proc(5). "T" covers a session
# suspended with Ctrl+Z, which is running in no meaningful sense.
SUSPENDED_STATES = {"T", "t"}
DEAD_STATES = {"Z", "X", "x"}


@dataclass(frozen=True)
class ProcessSpec:
    """How to recognise one kind of session.

    names:         accepted basenames of the executable
    require_args:  every entry must appear somewhere in the command line
    exclude_args:  any entry appearing disqualifies the process
    """

    names: frozenset[str]
    require_args: tuple[str, ...] = ()
    exclude_args: tuple[str, ...] = ()
    label: str = ""

    def matches(self, executable: str, command_line: str) -> bool:
        if os.path.basename(executable) not in self.names:
            return False
        if any(bad in command_line for bad in self.exclude_args):
            return False
        return all(good in command_line for good in self.require_args)


@dataclass(frozen=True)
class Instance:
    provider_id: str
    pid: int
    project: str
    directory: str
    started_at: datetime | None
    suspended: bool
    kind: str = ""

    def signature(self) -> tuple:
        """Identity for change detection. Deliberately excludes start time."""
        return (self.provider_id, self.pid, self.project, self.suspended)


@dataclass
class InstanceReport:
    active: list[Instance] = field(default_factory=list)
    suspended: list[Instance] = field(default_factory=list)

    @property
    def all(self) -> list[Instance]:
        return self.active + self.suspended

    def to_dict(self) -> dict:
        # Panel shows the count; the menu shows folder names. Full paths stay
        # out of both, since the panel is visible to anyone near the screen.
        return {
            "active": len(self.active),
            "suspended": len(self.suspended),
            "projects": _unique([i.project for i in self.active]),
            "suspendedProjects": _unique([i.project for i in self.suspended]),
        }


def _unique(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        if value:
            seen.setdefault(value, None)
    return list(seen)


def _boot_time() -> float:
    try:
        for line in (PROC / "stat").read_text().splitlines():
            if line.startswith("btime "):
                return float(line.split()[1])
    except OSError:
        pass
    return 0.0


def _read_process(pid: str) -> tuple[str, str, list[str]] | None:
    """Return (executable, whole command line, argv) or None if it vanished."""
    try:
        raw = (PROC / pid / "cmdline").read_bytes()
    except (OSError, ValueError):
        return None
    if not raw:
        return None  # kernel thread
    argv = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
    if not argv:
        return None
    return argv[0], " ".join(argv), argv


def _stat_fields(pid: str) -> tuple[str, int, float] | None:
    """Return (state, parent pid, start time in clock ticks)."""
    try:
        raw = (PROC / pid / "stat").read_text()
    except OSError:
        return None
    # The second field is the command in parentheses and may itself contain
    # spaces or parentheses, so split on the last ")" rather than on spaces.
    close = raw.rfind(")")
    if close < 0:
        return None
    rest = raw[close + 2 :].split()
    if len(rest) < 20:
        return None
    try:
        return rest[0], int(rest[1]), float(rest[19])
    except (ValueError, IndexError):
        return None


def _project_of(pid: str) -> tuple[str, str]:
    try:
        directory = os.readlink(PROC / pid / "cwd")
    except OSError:
        return "", ""
    return os.path.basename(directory.rstrip("/")) or directory, directory


def scan(specs: dict[str, list[ProcessSpec]], *, ignore_pids: set[int] | None = None) -> dict[str, InstanceReport]:
    """Find sessions for every provider in one pass over /proc."""
    ignore = ignore_pids or set()
    boot = _boot_time()
    reports = {provider_id: InstanceReport() for provider_id in specs}

    matched: dict[int, tuple[str, ProcessSpec]] = {}
    parents: dict[int, int] = {}
    details: dict[int, tuple[str, float]] = {}

    for entry in PROC.iterdir():
        pid_text = entry.name
        if not pid_text.isdigit():
            continue
        pid = int(pid_text)
        if pid in ignore:
            continue

        process = _read_process(pid_text)
        if process is None:
            continue
        executable, command_line, _argv = process

        hit = None
        for provider_id, provider_specs in specs.items():
            for spec in provider_specs:
                if spec.matches(executable, command_line):
                    hit = (provider_id, spec)
                    break
            if hit:
                break
        if hit is None:
            continue

        stat = _stat_fields(pid_text)
        if stat is None:
            continue
        state, parent, start_ticks = stat
        if state in DEAD_STATES:
            continue

        matched[pid] = hit
        parents[pid] = parent
        details[pid] = (state, start_ticks)

    for pid, (provider_id, spec) in matched.items():
        if _has_matching_ancestor(pid, provider_id, parents, matched):
            continue  # a helper the session spawned, not a session of its own
        state, start_ticks = details[pid]
        project, directory = _project_of(str(pid))
        started_at = None
        if boot and _CLOCK_TICKS:
            started_at = datetime.fromtimestamp(boot, timezone.utc) + timedelta(
                seconds=start_ticks / _CLOCK_TICKS
            )
        instance = Instance(
            provider_id=provider_id,
            pid=pid,
            project=project,
            directory=directory,
            started_at=started_at,
            suspended=state in SUSPENDED_STATES,
            kind=spec.label,
        )
        report = reports[provider_id]
        (report.suspended if instance.suspended else report.active).append(instance)

    return reports


def _has_matching_ancestor(
    pid: int, provider_id: str, parents: dict[int, int], matched: dict[int, tuple[str, ProcessSpec]]
) -> bool:
    """True when an ancestor belongs to the same provider.

    An agent that re-executes itself, or spawns a worker copy, would otherwise be
    counted once per process instead of once per session.
    """
    seen = {pid}
    current = parents.get(pid, 0)
    while current and current not in seen:
        seen.add(current)
        owner = matched.get(current)
        if owner and owner[0] == provider_id:
            return True
        current = parents.get(current, 0)
    return False


def signature(reports: dict[str, InstanceReport]) -> tuple:
    """Stable value that changes only when the visible set of sessions changes."""
    return tuple(
        (provider_id, tuple(sorted(i.signature() for i in reports[provider_id].all)))
        for provider_id in sorted(reports)
    )
