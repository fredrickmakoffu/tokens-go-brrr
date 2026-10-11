"""Record Pi sessions, which carry no token figures at all.

Pi persists models, projects, working directories and durations, but no token or
cost data: its footer totals are in-memory and no log line holds them. So this
reader writes rows with zero tokens and does **not** invent an estimate.

The design proposed a residual estimate taken from the account's meters, and the
review approved it. It cannot be built from what exists: the meters are
percentages of a limit, and no provider publishes that limit in tokens, so there
is no absolute quantity to subtract other tools' usage from. A guessed token
count for Pi would be worse than an absent one, so the estimate is dropped and
the reason recorded instead.

A Pi session is a live process, so a row is written while it runs (`started_at`
from `/proc`) and finalised when it disappears (`ended_at` = the last time it was
seen). Nothing here is a percentage or an estimate: `source` is `local-db` for
what was observed and nothing is claimed beyond that.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from typing import Any

from .. import ledger
from ..instances import Instance, scan
from ..providers import pi_backend
from ..providers.pi import PiProvider
from .base import HarvestResult

HARVESTER_ID = "pi_sessions"
PROVIDER = "pi"

READER_VERSION = 1
STATE_VERSION = 1


def _started_at(instance: Instance) -> int | None:
    moment = instance.started_at
    if moment is None:
        return None
    try:
        return int(moment.timestamp())
    except (OSError, OverflowError, ValueError):
        return None


class PiSessionHarvester:
    id = HARVESTER_ID
    provider = PROVIDER

    def available(self) -> bool:
        return pi_backend.installed()

    def harvest(self, con: sqlite3.Connection, *, full: bool = False) -> HarvestResult:
        result = HarvestResult(harvester=self.id, provider=self.provider)
        if not self.available():
            result.note = "Pi is not installed"
            return result

        try:
            reports = scan(
                {PiProvider.id: list(PiProvider().process_specs)},
                ignore_pids={os.getpid()},
            )
        except OSError as exc:
            result.failed = True
            result.note = f"scan failed: {exc}"
            return result

        report = reports.get(PiProvider.id)
        instances = report.all if report is not None else []
        previous = self._load(con)
        now = int(datetime.now(UTC).timestamp())

        rows: list[ledger.SessionRow] = []
        seen: dict[str, dict[str, Any]] = {}
        for instance in instances:
            external_id = self._external_id(instance)
            remembered = previous.get(external_id) or {}
            started = _started_at(instance)
            if started is None:
                started = remembered.get("started_at")
            backend = instance.backend
            model = backend.model if backend is not None else remembered.get("model")
            account = backend.account if backend is not None else remembered.get("account")
            rows.append(
                ledger.SessionRow(
                    provider=self.provider,
                    source="local-db",
                    external_id=external_id,
                    model=model or None,
                    project=instance.project or remembered.get("project") or None,
                    directory=instance.directory or remembered.get("directory") or None,
                    started_at=started,
                    ended_at=now,
                    duration_s=(now - started) if started else None,
                    meta={"account": account} if account else None,
                )
            )
            seen[external_id] = {
                "started_at": started,
                "seen_at": now,
                "model": model or None,
                "project": instance.project or None,
                "directory": instance.directory or None,
                "account": account or None,
            }

        # A session that is no longer running is closed out at the last moment it
        # was seen, which is the most the scanner can honestly say about it.
        for external_id, remembered in previous.items():
            if external_id in seen:
                continue
            started = remembered.get("started_at")
            ended = remembered.get("seen_at")
            duration = None
            if started and ended and ended >= started:
                duration = ended - started
            account = remembered.get("account")
            rows.append(
                ledger.SessionRow(
                    provider=self.provider,
                    source="local-db",
                    external_id=external_id,
                    model=remembered.get("model"),
                    project=remembered.get("project"),
                    directory=remembered.get("directory"),
                    started_at=started,
                    ended_at=ended,
                    duration_s=duration,
                    meta={"account": account} if account else None,
                )
            )

        result.scanned = len(rows)
        result.sessions = ledger.upsert_sessions(con, rows)
        result.folded_days = ledger.fold_days(con, ledger.affected_days(rows))
        ledger.set_watermark(
            con,
            self.id,
            json.dumps({"v": STATE_VERSION, "live": seen}),
            note=f"{len(seen)} live session(s)",
        )
        ledger.set_reader_format(con, self.id, READER_VERSION)
        return result

    @staticmethod
    def _external_id(instance: Instance) -> str:
        """Stable across harvests of one process, unique across pid reuse."""
        started = _started_at(instance) or 0
        return f"pid-{instance.pid}-{started}"

    def _load(self, con: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        raw, _note = ledger.watermark(con, self.id)
        if not raw:
            return {}
        try:
            state = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        if not isinstance(state, dict):
            return {}
        live = state.get("live")
        return live if isinstance(live, dict) else {}
