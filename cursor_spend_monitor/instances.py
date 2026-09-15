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
    tty_nr: int = 0

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
        # Panel shows the count and (when known) the focused project name.
        # The detail screen lists one row per session. Full paths are included
        # for focus matching in the Shell extension and are not rendered.
        sessions = [
            _session_dict(i, paused=False) for i in self.active
        ] + [
            _session_dict(i, paused=True) for i in self.suspended
        ]
        return {
            "active": len(self.active),
            "suspended": len(self.suspended),
            "projects": _unique([i.project for i in self.active]),
            "suspendedProjects": _unique([i.project for i in self.suspended]),
            "sessions": sessions,
        }


def _session_dict(instance: Instance, *, paused: bool) -> dict:
    return {
        "project": instance.project,
        "directory": instance.directory,
        "paused": paused,
        "kind": instance.kind,
        "tty": _tty_name(instance.tty_nr),
        "pid": instance.pid,
    }


def _tty_name(tty_nr: int) -> str:
    """Decode /proc stat tty_nr into a short pts/N label, or '' if none."""
    if not tty_nr:
        return ""
    # Linux packs major/minor into tty_nr; pts devices use major 136.
    major = (tty_nr >> 8) & 0xFFF
    minor = tty_nr & 0xFF
    if major == 136:
        return f"pts/{minor}"
    return ""


def _unique(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        if value:
            seen.setdefault(value, None)
    return list(seen)


def _boot_time(proc: Path = PROC) -> float:
    try:
        for line in (proc / "stat").read_text().splitlines():
            if line.startswith("btime "):
                return float(line.split()[1])
    except OSError:
        pass
    return 0.0


def _read_process(proc: Path, pid: str) -> tuple[str, str, list[str]] | None:
    """Return (executable, whole command line, argv) or None if it vanished."""
    try:
        raw = (proc / pid / "cmdline").read_bytes()
    except (OSError, ValueError):
        return None
    if not raw:
        return None  # kernel thread
    argv = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
    if not argv:
        return None
    return argv[0], " ".join(argv), argv


def _stat_fields(proc: Path, pid: str) -> tuple[str, int, int, float] | None:
    """Return (state, parent pid, tty_nr, start time in clock ticks)."""
    try:
        raw = (proc / pid / "stat").read_text()
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
        # state, ppid, pgrp, session, tty_nr, ... starttime at index 19
        return rest[0], int(rest[1]), int(rest[4]), float(rest[19])
    except (ValueError, IndexError):
        return None


def _project_of(proc: Path, pid: str) -> tuple[str, str]:
    try:
        directory = os.readlink(proc / pid / "cwd")
    except OSError:
        return "", ""
    return os.path.basename(directory.rstrip("/")) or directory, directory


def _collapse_by_tty(instances: list[Instance]) -> list[Instance]:
    """One controlling terminal is one session.

    Sibling agents under the same shell (backgrounded jobs, Task-spawned
    peers that inherit the pts) would otherwise each inflate the panel count.
    Processes with no controlling terminal (tty_nr == 0) stay one-per-pid —
    that covers the desktop app and headless helpers that survived exclusion.
    """
    groups: dict[int, list[Instance]] = {}
    alone: list[Instance] = []
    for instance in instances:
        if instance.tty_nr:
            groups.setdefault(instance.tty_nr, []).append(instance)
        else:
            alone.append(instance)

    collapsed = list(alone)
    for group in groups.values():
        running = [i for i in group if not i.suspended]
        collapsed.append(min(running or group, key=lambda i: i.pid))
    return collapsed


def scan(
    specs: dict[str, list[ProcessSpec]],
    *,
    ignore_pids: set[int] | None = None,
    proc: Path | None = None,
) -> dict[str, InstanceReport]:
    """Find sessions for every provider in one pass over /proc."""
    ignore = ignore_pids or set()
    proc_root = proc or PROC
    boot = _boot_time(proc_root)
    reports = {provider_id: InstanceReport() for provider_id in specs}

    matched: dict[int, tuple[str, ProcessSpec]] = {}
    # Parent links for every live process we see — not only matches — so the
    # ancestor walk can cross Electron helpers (--type=) that are deliberately
    # unmatched and still reach a matched provider root.
    parents: dict[int, int] = {}
    details: dict[int, tuple[str, float, int]] = {}

    for entry in proc_root.iterdir():
        pid_text = entry.name
        if not pid_text.isdigit():
            continue
        pid = int(pid_text)
        if pid in ignore:
            continue

        process = _read_process(proc_root, pid_text)
        if process is None:
            continue
        executable, command_line, _argv = process

        stat = _stat_fields(proc_root, pid_text)
        if stat is None:
            continue
        state, parent, tty_nr, start_ticks = stat
        if state in DEAD_STATES:
            continue

        parents[pid] = parent

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

        matched[pid] = hit
        details[pid] = (state, start_ticks, tty_nr)

    raw_by_provider: dict[str, list[Instance]] = {provider_id: [] for provider_id in specs}
    for pid, (provider_id, spec) in matched.items():
        if _has_matching_ancestor(pid, provider_id, parents, matched):
            continue  # a helper the session spawned, not a session of its own
        state, start_ticks, tty_nr = details[pid]
        project, directory = _project_of(proc_root, str(pid))
        started_at = None
        if boot and _CLOCK_TICKS:
            started_at = datetime.fromtimestamp(boot, timezone.utc) + timedelta(
                seconds=start_ticks / _CLOCK_TICKS
            )
        raw_by_provider[provider_id].append(
            Instance(
                provider_id=provider_id,
                pid=pid,
                project=project,
                directory=directory,
                started_at=started_at,
                suspended=state in SUSPENDED_STATES,
                kind=spec.label,
                tty_nr=tty_nr,
            )
        )

    for provider_id, instances in raw_by_provider.items():
        report = reports[provider_id]
        for instance in _collapse_by_tty(instances):
            (report.suspended if instance.suspended else report.active).append(instance)

    return reports


def _has_matching_ancestor(
    pid: int, provider_id: str, parents: dict[int, int], matched: dict[int, tuple[str, ProcessSpec]]
) -> bool:
    """True when an ancestor belongs to the same provider.

    An agent that re-executes itself, or spawns a worker copy, would otherwise be
    counted once per process instead of once per session. Walking the full
    parent map (including unmatched intermediates) is required so an IDE-spawned
    agent under an Electron helper still collapses into the desktop session.
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
