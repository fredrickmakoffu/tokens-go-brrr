from __future__ import annotations

import os
import random
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from gi.repository import GLib  # type: ignore  # gi has no stubs

from . import (
    __version__,
    burn,
    harvesters,
    history,
    ledger,
    llm_budget,
    llm_log,
    notify_engine,
    update_install,
    updates,
)
from . import llm_composer as llm
from .borrowing import apply_borrowing
from .coerce import as_int as _as_int
from .config import MonitorConfig
from .dbus_service import UsageService
from .instances import InstanceReport, scan, signature
from .notify import AlertManager, send
from .providers import DEFAULT_PROVIDERS, PROVIDERS, build_providers
from .providers.base import Provider, ProviderSnapshot
from .state import build_payload, write_state

# How often the notification clock is consulted. The schedule it serves is
# hourly at most, so this only decides how late a digest can be, not how often
# one is sent.
NOTIFY_CHECK_SECONDS = 300


def _now_ts() -> int:
    try:
        return int(datetime.now(UTC).timestamp())
    except (OSError, OverflowError, ValueError):
        return 0


# Shortest gap between two rounds of provider requests. Matches the floor the
# daemon already clamps its own timer to, so a refresh on open can never make
# more requests than the scheduled polling would.
REFRESH_COOLDOWN_SECONDS = 60

# The warm tier: how long the "catching up" line may stay up, and how soon after
# a harvest another is not worth running.
WARM_BUDGET_SECONDS = 4
WARM_HARVEST_SPACING_SECONDS = 60
# A warm note's model call has to fit the same budget as the line that says it is
# coming; past it the template note stands.
WARM_LLM_TIMEOUT_SECONDS = 4
# After a 429 a provider is left alone this long, whatever it is asked for.
LLM_BACKOFF_SECONDS = 15 * 60


class UsageDaemon:
    """Polls providers, raises alerts, and publishes state over D-Bus for the shell extension."""

    def __init__(self, config: MonitorConfig) -> None:
        self.config = config
        self.providers: list[Provider] = build_providers(config.enabled_providers)
        self.alerts = AlertManager(config)
        self.history = history.Recorder(keep_days=config.history_days)
        # The ledger is the long-term store; history is the sample series the
        # burn-rate fit needs. They fail independently and neither stops the
        # other, or the panel.
        self.ledger = ledger.LedgerRecorder(keep_days=config.ledger_days)
        # Every call made to a language model, one file per day, readable from
        # the panel. Independent of the stores above and just as fail-soft.
        self.llm_log = llm_log.LlmLog(keep_days=config.llm_log_days)
        # Ceiling on calls made because the panel was opened, and the providers
        # that said 429 recently (monotonic deadline per provider id).
        self.llm_budget = llm_budget.CallBudget(config.live_llm_per_hour, config.live_llm_per_day)
        self._llm_backoff: dict[str, float] = {}
        # Meter history for the warm note, read on the main loop (the history
        # store's connection belongs to it) and handed to the worker.
        self._warm_samples: dict[tuple[str, str], list[tuple[float, float]]] = {}
        self._harvesting = False
        # When the panel was last opened (monotonic seconds), for the cold tier,
        # and whether a cold note is already being made.
        self._last_open: float | None = None
        self._cold_running = False
        # The warm tier: when its note was last made (monotonic), whether one is
        # being made, whether the panel should say so, and when the ledger last
        # finished a harvest, so an open does not re-read what was just read.
        self._last_warm_at: float | None = None
        self._warm_running = False
        self._catching_up = False
        self._last_harvest_at: float | None = None
        # The first harvest of a run may backfill (Cursor's previous cycle);
        # later ones are strictly incremental.
        self._harvest_full = True
        self._last_slot: dict[str, str] = {}
        self._billboard: dict[str, Any] | None = None
        self._latest_message: dict[str, Any] | None = None
        self._recent_messages: list[dict[str, Any]] = []
        # The newer release on offer (updates.offer_from_manifest), if any.
        self._update: dict[str, Any] | None = None
        self._checking_update = False
        # Where the user's Update press has got to: available, downloading,
        # installing, installed or error. Held in memory only: a restart starts
        # from a fresh check against the version that is now running.
        self._update_phase = "available"
        self._update_error: str | None = None
        self.snapshots: list[ProviderSnapshot] = []
        self.last_error: str | None = None
        self.last_fetch: datetime | None = None
        self._polling = False
        # Set when a provider is shown while a poll is already running, so the
        # finishing worker's snapshot list (built without the newcomer) is not
        # the last word — another force poll starts as soon as the lock clears.
        self._poll_again = False
        self._specs = {
            provider.id: list(getattr(provider, "process_specs", [])) for provider in self.providers
        }
        self._instances: dict[str, InstanceReport] = {
            provider_id: InstanceReport() for provider_id in self._specs
        }
        self._published_signature = signature(self._instances)
        self._candidate_signature: tuple | None = None
        self.loop = GLib.MainLoop()

        self.service = UsageService(
            version=__version__,
            get_state=self.state_payload,
            on_refresh=self.panel_opened,
            on_set_primary=self.set_primary,
            on_set_provider_enabled=self.set_provider_enabled,
            on_install_update=self.install_update,
            on_restart=self.restart_daemon,
            on_skip_update=self.skip_update,
            on_acknowledge=self.acknowledge,
            on_llm_log=self.llm_log_payload,
            on_llm_log_clear=self.llm_log_clear,
            on_llm_log_report=self.llm_log_report,
            on_quit=self.quit,
            on_name_lost=self._name_lost,
        )

        interval = max(60, self.config.poll_interval_seconds)
        GLib.timeout_add_seconds(interval, self._tick)
        # Sessions come and go far faster than quota does, and a scan is local and
        # cheap, so it runs on its own much shorter timer.
        GLib.timeout_add_seconds(max(1, self.config.instance_poll_seconds), self._scan_instances)
        # The ledger fills itself, on its own slow clock: a harvest reads
        # databases and transcripts that quota polling has no business touching.
        GLib.timeout_add_seconds(max(60, self.config.harvest_deep_seconds), self._harvest_tick)
        if self.config.notify_enabled:
            GLib.timeout_add_seconds(NOTIFY_CHECK_SECONDS, self._notify_tick)
        if self.config.update_check:
            # A random start spreads installs over the first minutes after a
            # login, so a fleet does not hit the site on the same second.
            GLib.timeout_add_seconds(random.randint(30, 150), self._update_first)
        # The first runs happen at idle, but each must fire exactly once.
        # `GLib.idle_add` re-schedules a callback that returns True, and the
        # timer functions return True to keep their own timers alive — handing
        # them over directly spins the main loop at idle priority forever and
        # pegs a CPU core. `poll` returns False, so it is already one-shot; the
        # other two go through wrappers that remove the source.
        GLib.idle_add(self.poll)
        GLib.idle_add(self._startup_scan)
        GLib.idle_add(self._startup_harvest)
        for sig in (signal.SIGINT, signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self._on_signal)

    # -- lifecycle -----------------------------------------------------------

    def run(self) -> int:
        self.loop.run()
        self.service.close()
        self.history.close()
        self.ledger.close()
        return 0

    def quit(self, *_args) -> bool:
        self.loop.quit()
        return False

    def _on_signal(self, *_args) -> bool:
        self.quit()
        return False

    def _name_lost(self) -> None:
        print(
            "Another tokens-go-brrr daemon owns the bus name; exiting.",
            file=sys.stderr,
            flush=True,
        )
        self.quit()

    # -- polling -------------------------------------------------------------

    def _tick(self) -> bool:
        self.poll(force=True)
        return True

    def panel_opened(self, *args) -> bool:
        """The panel asked for a refresh, which it does each time it opens.

        Besides refreshing, an open after a long absence (or the first since the
        daemon started) is the moment for a cold note: a trend or insight about
        the shape of the person's usage, made while they are not waiting for it.
        """
        now = time.monotonic()
        idle = None if self._last_open is None else now - self._last_open
        self._last_open = now
        tier = None
        if self.config.live_notes:
            warm_age = None if self._last_warm_at is None else now - self._last_warm_at
            tier = notify_engine.tier_for(
                idle,
                cold_hours=self.config.live_cold_hours,
                hot_minutes=self.config.live_hot_minutes,
                last_warm_age=warm_age,
            )
        # Poll first: the warm worker waits for it, so it must already be running.
        result = self.poll(*args)
        if tier == notify_engine.COLD:
            self._start_cold_note()
        elif tier == notify_engine.WARM:
            self._start_warm_note()
        # A hot open does nothing more: the last warm note is still the answer.
        return result

    def _start_cold_note(self) -> None:
        """Make a cold insight off the main loop, if the person wants one."""
        if self._cold_running or self.ledger.connection is None:
            return
        if not self._wanted(notify_engine.INFORMATIVE):
            return
        self._cold_running = True
        threading.Thread(target=self._cold_worker, name="tokens-go-brrr-cold", daemon=True).start()

    def _cold_worker(self) -> None:
        stored = False
        try:
            with self.ledger.worker() as con:
                if con is None:
                    return
                message = notify_engine.cold_note(con)
                if message is not None:
                    # No model and no desktop notification: the note waits on the
                    # landing page for the next look, which is the whole point.
                    stored = bool(
                        notify_engine.keep(
                            con,
                            [message],
                            cooldown_seconds=notify_engine.DEFAULT_COOLDOWN_SECONDS,
                        )
                    )
        except sqlite3.Error as exc:
            print(f"Could not build a cold note: {exc}", file=sys.stderr, flush=True)
        finally:
            self._cold_running = False
        if stored:
            GLib.idle_add(self._publish_cold)

    def _start_warm_note(self) -> None:
        """Catch the note up with the last couple of hours, behind the panel.

        The panel already shows the best cached note. This reads what happened
        since, and a changed picture arrives as a new note a moment later; an
        unchanged one makes no note at all (the key is the fingerprint). The
        "catching up" line is shown for at most WARM_BUDGET_SECONDS, however long
        the harvest takes.
        """
        if self._warm_running or self.ledger.connection is None:
            return
        if not self._wanted(notify_engine.INFORMATIVE):
            return
        now = time.monotonic()
        self._warm_running = True
        self._last_warm_at = now
        # The hourly harvest may be running; if not, and nothing was read in the
        # last minute, read the tools' stores now. Claimed on the main loop so
        # two harvests can never overlap.
        recent = (
            self._last_harvest_at is not None
            and now - self._last_harvest_at < WARM_HARVEST_SPACING_SECONDS
        )
        harvest_here = self.ledger.active and not self._harvesting and not recent
        if harvest_here:
            self._harvesting = True
        self._catching_up = True
        self._warm_samples = self._collect_samples()
        self._publish()
        GLib.timeout_add_seconds(WARM_BUDGET_SECONDS, self._stop_catching_up)
        threading.Thread(
            target=self._warm_worker,
            args=(harvest_here,),
            name="tokens-go-brrr-warm",
            daemon=True,
        ).start()

    def _collect_samples(self) -> dict[tuple[str, str], list[tuple[float, float]]]:
        """The meter history for each rolling meter, for the "ran elsewhere" check."""
        found: dict[tuple[str, str], list[tuple[float, float]]] = {}
        for snap in self.snapshots:
            for meter in snap.metrics:
                if meter.kind == "rolling":
                    found[(snap.provider_id, meter.key)] = self.history.window_samples(
                        snap.provider_id, meter.key
                    )
        return found

    def _warm_worker(self, harvest_here: bool) -> None:
        deadline = time.monotonic() + WARM_BUDGET_SECONDS
        stored = False
        try:
            with self.ledger.worker() as con:
                if con is None:
                    return
                if harvest_here:
                    try:
                        self._run_readers(con, full=False)
                    except Exception as exc:  # noqa: BLE001 - see _harvest_worker
                        print(f"Warm harvest failed: {exc}", file=sys.stderr, flush=True)
                # A poll started by this same open is the freshest meter there is.
                while self._polling and time.monotonic() < deadline:
                    time.sleep(0.1)
                message = notify_engine.warm_note(
                    con, list(self.snapshots), samples=self._warm_samples
                )
                if message is not None:
                    message = self._warm_wording(con, message)
                    stored = bool(
                        notify_engine.keep(
                            con,
                            [message],
                            cooldown_seconds=notify_engine.DEFAULT_COOLDOWN_SECONDS,
                        )
                    )
        except sqlite3.Error as exc:
            print(f"Could not build a warm note: {exc}", file=sys.stderr, flush=True)
        finally:
            if harvest_here:
                self._last_harvest_at = time.monotonic()
                self._harvesting = False
            self._warm_running = False
            GLib.idle_add(self._finish_warm, stored)

    def _warm_wording(self, con: sqlite3.Connection, message: Any) -> Any:
        """The warm note in a quick model's words, when that is allowed and new.

        Only a note that would actually be stored is worth a call: an unchanged
        picture has a stored note already. The call is capped (per hour and per
        day), skips a provider that just said 429, and has the warm budget as its
        timeout; every refusal leaves the template, which is a complete note.
        """
        if not self.config.llm_notifications:
            return message
        if not notify_engine.due(
            con, message, cooldown_seconds=notify_engine.DEFAULT_COOLDOWN_SECONDS
        ):
            return message
        composed = self._compose(
            con,
            [message],
            trigger="open",
            origin="open",
            timeout=WARM_LLM_TIMEOUT_SECONDS,
            budget=self.llm_budget,
        )
        return composed[0]

    def _finish_warm(self, stored: bool) -> bool:
        self._catching_up = False
        con = self.ledger.connection
        if con is not None and stored:
            self._refresh_billboard(con)
        self._publish()
        return False

    def _stop_catching_up(self) -> bool:
        """Take the line down when the budget runs out, whatever is still running."""
        if self._catching_up:
            self._catching_up = False
            self._publish()
        return False

    def _publish_cold(self) -> bool:
        con = self.ledger.connection
        if con is not None:
            self._refresh_billboard(con)
            self._publish()
        return False

    def poll(self, *_args, force: bool = False) -> bool:
        """Fetch every provider, unless we just did.

        The panel asks for a refresh each time it opens, which is the right
        instinct — you open it to see the current number — but the only guard
        used to be against two polls overlapping, not against many in a row.
        Opening the popover twenty times made twenty rounds of requests to
        every vendor, and the endpoints that answer fastest are the ones that
        start refusing: Anthropic returns 429 on its usage route long before a
        quota is spent.

        Quota does not move fast enough for that to cost anything. Inside the
        cooldown the panel is served the state already published, which is at
        most a minute old, so nothing on screen is wrong — it is the same
        number a successful poll would have returned.

        The About screen's manual button shares this path and is throttled the
        same way. That is deliberate: it is the control most likely to be
        pressed repeatedly when a provider looks wrong, which is exactly when
        the provider is least able to answer. force is for the scheduled tick,
        which is already spaced by the poll interval.
        """
        # An out-of-band message -- the `quote` command writes straight to the
        # ledger from another process, and the scheduler ticks on its own clock --
        # should reach the panel on the next open rather than at the next slow
        # timer. Two indexed reads, and a republish only when something changed.
        self._publish_billboard_change()
        if self._polling:
            return False
        if not force and self.last_fetch is not None:
            age = (datetime.now(UTC) - self.last_fetch).total_seconds()
            if age < REFRESH_COOLDOWN_SECONDS:
                return False
        self._polling = True
        threading.Thread(target=self._poll_worker, name="tokens-go-brrr-poll", daemon=True).start()
        return False

    def _poll_worker(self) -> None:
        snapshots: list[ProviderSnapshot] = []
        for provider in self.providers:
            try:
                snap = provider.fetch()
            except Exception as exc:  # noqa: BLE001
                snap = ProviderSnapshot.error_snapshot(
                    provider_id=getattr(provider, "id", "unknown"),
                    display_name=getattr(provider, "display_name", "Provider"),
                    icon=getattr(provider, "id", "cursor"),
                    message=str(exc),
                )
            snapshots.append(snap)
        GLib.idle_add(self._apply_snapshots, snapshots)

    # -- sessions -------------------------------------------------------------

    def _startup_scan(self) -> bool:
        """One initial scan, then remove the idle source.

        `_scan_instances` is written to be driven by a timer, so it returns
        True to stay scheduled. As an idle callback that same True would
        re-queue it immediately.
        """
        self._scan_instances()
        return GLib.SOURCE_REMOVE

    def _scan_instances(self, *_args) -> bool:
        try:
            reports = scan(self._specs, ignore_pids={os.getpid()})
        except OSError as exc:
            print(f"Instance scan failed: {exc}", file=sys.stderr, flush=True)
            return True

        current = signature(reports)
        if current == self._published_signature:
            self._candidate_signature = None
            return True

        # A change has to survive two consecutive scans before it reaches the
        # panel, so a session that starts and exits between ticks cannot make the
        # top bar flicker.
        if current != self._candidate_signature:
            self._candidate_signature = current
            return True

        self._candidate_signature = None
        self._published_signature = current
        self._instances = reports
        self._attach_instances()
        self._publish()
        return True

    def _attach_instances(self) -> None:
        for snap in self.snapshots:
            snap.instances = self._instances.get(snap.provider_id, InstanceReport())
        self._apply_borrowing()

    def _apply_borrowing(self) -> None:
        """Give a harness the meters of the account its sessions are spending on."""
        apply_borrowing(
            self.snapshots,
            is_harness=self._is_harness,
            primary_overrides=self.config.primary_overrides,
        )

    def _is_harness(self, provider_id: str) -> bool:
        """A provider whose meters come from whichever account its sessions use."""
        specs = self._specs.get(provider_id) or []
        return any(spec.resolve_backend is not None for spec in specs)

    def _apply_snapshots(self, snapshots: list[ProviderSnapshot]) -> bool:
        self._polling = False
        applied: list[ProviderSnapshot] = []
        errors: list[str] = []
        for snap in snapshots:
            snap = self._apply_override(snap)
            applied.append(snap)
            if snap.status != "ok":
                errors.append(snap.error or snap.status)
            elif not self._is_harness(snap.provider_id):
                # A harness shows meters it borrowed from another provider, and
                # that provider alerts on them already. Alerting here too would
                # notify twice for one limit.
                self.alerts.check(snap)
        # A worker that started before SetProviderEnabled finished would omit
        # the newcomer. Keep prior rows for anyone still enabled but missing,
        # and schedule another force poll so the gap is temporary.
        want = {provider.id for provider in self.providers}
        have = {snap.provider_id for snap in applied}
        missing = want - have
        if missing:
            kept = [s for s in self.snapshots if s.provider_id in missing]
            applied.extend(kept)
            order = {pid: i for i, pid in enumerate(self.config.enabled_providers)}
            applied.sort(key=lambda s: order.get(s.provider_id, len(order)))
            self._poll_again = True
        # Drop anyone who was hidden while this worker was still running.
        applied = [s for s in applied if s.provider_id in want]
        self.snapshots = applied
        self.last_fetch = datetime.now(UTC)
        self.history.record(applied, at=self.last_fetch)
        self._attach_forecasts()
        self.last_error = (
            "; ".join(errors) if errors and not any(s.status == "ok" for s in applied) else None
        )
        self._attach_instances()
        self._notify_events()
        self._publish()
        if self._poll_again:
            self._poll_again = False
            self.poll(force=True)
        return False

    # -- ledger --------------------------------------------------------------

    def _startup_harvest(self) -> bool:
        """One initial harvest, then remove the idle source. See `_startup_scan`."""
        self._harvest_tick()
        return GLib.SOURCE_REMOVE

    def _harvest_tick(self) -> bool:
        """Re-read the tools' own stores into the ledger, off the main loop."""
        if not self.ledger.active or self._harvesting:
            return True
        self._harvesting = True
        threading.Thread(
            target=self._harvest_worker, name="tokens-go-brrr-harvest", daemon=True
        ).start()
        return True

    def _run_readers(self, con: sqlite3.Connection, *, full: bool) -> None:
        for reader in harvesters.build():
            if not reader.available():
                continue
            reader.harvest(con, full=full)

    def _harvest_worker(self) -> None:
        try:
            # A worker thread needs its own connection: the ledger's belongs to
            # the main loop, and SQLite refuses to let another thread use it.
            with self.ledger.worker() as con:
                if con is None:
                    return
                self._run_readers(con, full=self._harvest_full)
                ledger.prune(con, keep_days=self.config.ledger_days)
                self.llm_log.prune()
            # Back to the main loop before touching D-Bus: this runs on a
            # worker thread, and the state signal is GLib's to emit.
            GLib.idle_add(self._publish_billboard_change)
        except Exception as exc:  # noqa: BLE001 - a reader must not stop the daemon
            print(f"Ledger harvest failed: {exc}", file=sys.stderr, flush=True)
        finally:
            self._harvest_full = False
            self._harvesting = False
            self._last_harvest_at = time.monotonic()

    # -- notifications -------------------------------------------------------

    def _quiet_now(self) -> bool:
        """True during the configured quiet hours, in local time."""
        hours = self.config.notify_silent_hours
        if not hours or len(hours) != 2:
            return False
        start, end = _as_int(hours[0], 22), _as_int(hours[1], 7)
        if start == end:
            return False
        hour = datetime.now().hour
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end

    def _due_slot(self) -> str | None:
        """The scheduled digest that is due now, if any.

        At most one slot fires per check, most specific first, so a monthly
        digest on the 1st does not also drag the daily one out on the same tick.
        """
        local = datetime.now()
        if local.hour < max(0, min(23, self.config.notify_daily_hour)):
            return None
        day = local.date().isoformat()
        iso = local.isocalendar()
        week = f"{iso.year}-W{iso.week:02d}"
        month = local.date().strftime("%Y-%m")
        names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        wanted = self.config.notify_weekly_day.lower()
        weekly = names.index(wanted) if wanted in names else 0
        if local.day == 1 and self._last_slot.get("monthly") != month:
            self._last_slot["monthly"] = month
            return "monthly"
        if local.weekday() == weekly and self._last_slot.get("weekly") != week:
            self._last_slot["weekly"] = week
            return "weekly"
        if self._last_slot.get("daily") != day:
            self._last_slot["daily"] = day
            return "daily"
        return None

    def _notify_tick(self) -> bool:
        """Send the scheduled digest when its clock comes round."""
        if not self.config.notify_enabled or self._quiet_now():
            return True
        if self.ledger.connection is None:
            return True
        slot = self._due_slot()
        if slot is None:
            return True
        # Composing can reach a network, so it never runs on the main loop.
        threading.Thread(
            target=self._digest_worker,
            args=(slot,),
            name="tokens-go-brrr-digest",
            daemon=True,
        ).start()
        return True

    def _digest_worker(self, slot: str) -> None:
        try:
            with self.ledger.worker() as con:
                if con is None:
                    # Nothing to read. The ledger explains itself once, but hand
                    # the slot back so a ledger that recovers before the next
                    # check still gets its digest out.
                    self._last_slot.pop(slot, None)
                    return
                messages = self._compose(
                    con,
                    notify_engine.scheduled_messages(con, slot=slot),
                    origin=f"scheduled:{slot}",
                )
                fresh = notify_engine.keep(
                    con,
                    messages,
                    cooldown_seconds=notify_engine.DEFAULT_COOLDOWN_SECONDS,
                )
        except sqlite3.Error as exc:
            print(f"Could not build the {slot} digest: {exc}", file=sys.stderr, flush=True)
            # A failure must not burn the slot. The digest of 2026-10-07 18:03
            # died on a connection error, had already marked itself sent, and so
            # never tried again: one exception cost a whole day of digests, and
            # the only trace was a single line in the journal.
            self._last_slot.pop(slot, None)
            return
        GLib.idle_add(self._deliver, fresh, False)

    def _compose(
        self,
        con: sqlite3.Connection,
        messages: list[Any],
        *,
        trigger: str = "",
        origin: str = "",
        timeout: int | None = None,
        budget: llm_budget.CallBudget | None = None,
    ) -> list[Any]:
        """The templates, reworded by a model when one has capacity to spare.

        Every failure -- no generator with enough headroom, a missing
        credential, a refusal, a spent budget -- leaves the template in place.
        The LLM is an upgrade, and an upgrade that can break the notification
        path is not one. A `budget` is spent per call, for the callers (an open
        of the panel) that are not bounded by a schedule.
        """
        if not (self.config.llm_notifications and messages):
            return messages
        now = time.monotonic()
        resting = {p for p, until in self._llm_backoff.items() if until > now}
        generator = llm.choose(
            [s for s in self.snapshots if s.provider_id not in resting],
            trigger=trigger,
            floor=self.config.llm_min_headroom,
            model=self.config.llm_generator_model,
            provider=self.config.llm_generator_provider,
        )
        if generator is None:
            # Worth a line in the log: a person wondering why nothing was
            # reworded can see that no provider had the room.
            self._log_skipped(origin, messages[0], "no_generator")
            return messages
        extra = {} if timeout is None else {"timeout": timeout}
        improved: list[Any] = []
        for message in messages:
            if budget is not None:
                refusal = budget.refusal()
                if refusal:
                    self._log_skipped(origin, message, refusal)
                    improved.append(message)
                    continue
                budget.spend()
            rewritten = llm.rewrite(
                message,
                generator=generator,
                facts=self._facts_for(con, message),
                max_tokens=self.config.llm_max_output_tokens,
                recorder=self._record_llm,
                context={"trigger": origin},
                **extra,
            )
            improved.append(rewritten or message)
        return improved

    def _log_skipped(self, origin: str, message: Any, reason: str) -> None:
        self.llm_log.record(
            {
                "trigger": origin,
                "outcome": llm_log.SKIPPED,
                "reason": reason,
                "message_kind": message.kind,
                "message_key": message.key,
            }
        )

    def _record_llm(self, entry: dict[str, Any]) -> None:
        """Log a call, and leave a provider alone for a while after a 429."""
        self.llm_log.record(entry)
        if entry.get("outcome") == llm_log.RATE_LIMITED and entry.get("provider"):
            self._llm_backoff[str(entry["provider"])] = time.monotonic() + LLM_BACKOFF_SECONDS

    def llm_log_payload(self, day: str = "") -> dict[str, Any]:
        """One day of the LLM log for the Settings screen; newest day if none."""
        return self.llm_log.payload(day or None)

    def llm_log_report(self) -> str:
        """Write the whole log as a text document and return where it is."""
        try:
            return str(self.llm_log.write_report())
        except OSError as exc:
            print(f"LLM log: could not write the report: {exc}", file=sys.stderr)
            return ""

    def llm_log_clear(self) -> None:
        self.llm_log.clear()

    def _facts_for(self, con: sqlite3.Connection, message: Any) -> dict[str, Any]:
        """The ranked providers the model may choose the featured AI from.

        A trailing month, so the list is stable and always has ids in it; the
        message keeps its own period's numbers, which are already in the draft.
        """
        start, end = notify_engine.day_range(30)
        meta = message.meta or {}
        facts: dict[str, Any] = {
            "period": str(meta.get("period") or "last 30 days"),
            "ranked": ledger.period_totals(con, start_day=start, end_day=end, group_by="provider"),
        }
        if meta.get("period") == "warm":
            # The fresh figures behind a warm note, so a rewording can use them
            # and the rule "only the numbers in FACTS" has something to cite.
            facts["now"] = dict((meta.get("tpl") or {}).get("p") or {})
        return facts

    def _deliver(self, messages: list[Any], actionable: bool) -> bool:
        """Send what was composed and republish, back on the main loop."""
        for message in messages:
            if not self._wanted(message.kind):
                continue
            if not actionable:
                send("tokens-go-brrr", message.body)
                continue
            # Urgency comes from the recorded percentage rather than from
            # reading the sentence back, which would make prose load-bearing.
            percent = (message.meta or {}).get("percent")
            spent = isinstance(percent, (int, float)) and percent >= notify_engine.SPENT_AT
            send("tokens-go-brrr", message.body, urgency="critical" if spent else "normal")
        con = self.ledger.connection
        if messages and con is not None:
            self._refresh_billboard(con)
            self._publish()
        return False

    def _notify_events(self) -> None:
        """Speak up when a meter is about to run out."""
        if not self.config.notify_enabled or self._quiet_now():
            return
        if not self._wanted(notify_engine.ACTIONABLE):
            return
        if self.ledger.connection is None:
            return
        threading.Thread(
            target=self._events_worker, name="tokens-go-brrr-event", daemon=True
        ).start()

    def _events_worker(self) -> None:
        try:
            with self.ledger.worker() as con:
                if con is None:
                    return
                messages = notify_engine.event_messages(
                    self.snapshots, wind_down_hours=self.config.wind_down_hours
                )
                trigger = messages[0].meta.get("trigger", "") if messages else ""
                messages = self._compose(
                    con, messages, trigger=trigger, origin=f"event:{trigger or 'meter'}"
                )
                fresh = notify_engine.keep(
                    con,
                    messages,
                    cooldown_seconds=notify_engine.DEFAULT_COOLDOWN_SECONDS,
                )
        except sqlite3.Error as exc:
            print(
                f"Could not build an actionable message: {exc}",
                file=sys.stderr,
                flush=True,
            )
            return
        GLib.idle_add(self._deliver, fresh, True)

    def _wanted(self, kind: str) -> bool:
        return kind in (self.config.notify_types or [])

    # -- the landing page ----------------------------------------------------

    def acknowledge(self, message_id: int) -> None:
        """The panel has shown a message; stop offering it.

        Recorded in the database on purpose. The extension cannot remember a
        dismissal across a reload or a login, and a message that keeps coming
        back is worse than one that never appears.
        """
        con = self.ledger.connection
        if con is None or not message_id:
            return
        try:
            ledger.mark_message_seen(con, message_id)
        except sqlite3.Error as exc:
            print(
                f"Could not acknowledge message {message_id}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            return
        self._refresh_billboard(con)
        self._publish()

    def _billboard_ids(self) -> tuple[Any, Any]:
        return (
            (self._billboard or {}).get("id"),
            (self._latest_message or {}).get("id"),
        )

    def _publish_billboard_change(self) -> bool:
        """Re-read the landing page, republishing only if it changed.

        Messages reach the ledger from several places -- the scheduler, an event,
        and the `quote` command in a different process -- so the billboard can
        move without a poll having happened. Comparing ids first keeps the check
        cheap enough to run on every open, which is what makes an out-of-band
        message show up on the next click instead of minutes later.
        """
        con = self.ledger.connection
        if con is None:
            return False
        before = self._billboard_ids()
        self._refresh_billboard(con)
        if self._billboard_ids() == before:
            return False
        self._publish()
        return True

    def _refresh_billboard(self, con: sqlite3.Connection) -> None:
        """Choose the one message the panel should open on, if any.

        The daemon decides, not the extension: acknowledgement has to outlive a
        login, and priority and freshness are rules worth testing in Python. The
        configured `billboard_freshness_hours` is a ceiling over the per-kind
        windows; zero disables the ceiling.
        """
        if not self.config.billboard_enabled:
            self._billboard = None
            self._latest_message = None
            self._recent_messages = []
            return

        pending = ledger.pending_messages(con)
        ceiling = max(0, self.config.billboard_freshness_hours) * 3600
        if ceiling:
            now_ts = _now_ts()
            pending = [
                row
                for row in pending
                if not row.get("created_at") or now_ts - _as_int(row.get("created_at")) <= ceiling
            ]
        self._billboard = notify_engine.choose_billboard(pending)

        latest = ledger.latest_message(con)
        # `latest_message` is deliberately unfiltered by acknowledgement or
        # freshness: "show me the most recent one" should work months later.
        self._latest_message = notify_engine.billboard_payload(latest) if latest else None
        self._recent_messages = [
            notify_engine.billboard_payload(row) for row in ledger.recent_messages(con)
        ]

    def _attach_forecasts(self) -> None:
        """Give each meter a time-to-exhaustion from its recorded samples.

        Only rows that own their meters are forecast; a harness gets its ETA
        along with the meters it borrows, from the provider that recorded them.
        """
        for snap in self.snapshots:
            if snap.status != "ok" or snap.borrowed_from is not None:
                continue
            snap.metrics = [
                replace(meter, eta_seconds=self._forecast(snap.provider_id, meter))
                for meter in snap.metrics
            ]

    def _forecast(self, provider_id: str, meter) -> float | None:
        samples = self.history.window_samples(provider_id, meter.key)
        eta = burn.eta_seconds(samples)
        if eta is None or meter.resets_at is None:
            return eta
        until_reset = (meter.resets_at - datetime.now(UTC)).total_seconds()
        if until_reset > 0 and eta > until_reset:
            # The window rolls over before the limit is reached, so there is no
            # exhaustion to warn about — saying "in 9h" under a 3h window reads
            # as a threat that cannot happen.
            return None
        return eta

    def _apply_override(self, snap: ProviderSnapshot) -> ProviderSnapshot:
        key = self.config.primary_overrides.get(snap.provider_id)
        if key and snap.status == "ok":
            return snap.with_primary(key)
        return snap

    # -- commands ------------------------------------------------------------

    def set_primary(self, provider_id: str, metric_key: str) -> None:
        target = next((s for s in self.snapshots if s.provider_id == provider_id), None)
        if target is None or target.status != "ok":
            return
        if metric_key not in {m.key for m in target.metrics}:
            return
        self.config.set_primary(provider_id, metric_key)
        self.snapshots = [
            s.with_primary(metric_key) if s.provider_id == provider_id else s
            for s in self.snapshots
        ]
        self._publish()

    def set_provider_enabled(self, provider_id: str, enabled: bool) -> None:
        """Show or hide a provider on the panel without restarting the daemon."""
        if not self.config.set_provider_enabled(provider_id, enabled):
            return
        self._rebuild_providers()
        if enabled:
            # Fetch the newcomer immediately so Settings → Show does not leave
            # an empty gap until the next timed poll. If a poll is already in
            # flight, ask for another once it finishes — that worker's list was
            # built without this provider.
            if self._polling:
                self._poll_again = True
            else:
                self.poll(force=True)
            return
        self.snapshots = [s for s in self.snapshots if s.provider_id != provider_id]
        self._publish()

    def _rebuild_providers(self) -> None:
        self.providers = build_providers(self.config.enabled_providers)
        self._specs = {
            provider.id: list(getattr(provider, "process_specs", [])) for provider in self.providers
        }
        kept = {pid: report for pid, report in self._instances.items() if pid in self._specs}
        for provider_id in self._specs:
            kept.setdefault(provider_id, InstanceReport())
        self._instances = kept
        self._published_signature = signature(self._instances)

    # -- updates -------------------------------------------------------------

    def _update_first(self) -> bool:
        """First check after start-up, which then repeats on its own clock."""
        self._update_tick()
        hours = max(1, self.config.update_check_hours)
        GLib.timeout_add_seconds(hours * 3600, self._update_tick)
        return False

    def _update_tick(self) -> bool:
        if self._checking_update:
            return True
        self._checking_update = True
        # A network fetch never runs on the main loop.
        threading.Thread(
            target=self._update_worker, name="tokens-go-brrr-update", daemon=True
        ).start()
        return True

    def _update_worker(self) -> None:
        try:
            url = self.config.update_manifest_url or updates.MANIFEST_URL
            manifest = updates.fetch_manifest(url)
            # A failed fetch keeps whatever offer is showing; only a manifest
            # that arrived and has nothing newer clears it.
            if manifest is not None:
                GLib.idle_add(self._apply_update, updates.offer_from_manifest(manifest))
        finally:
            self._checking_update = False

    def _apply_update(self, offer: dict[str, Any] | None) -> bool:
        if offer != self._update:
            if (offer or {}).get("version") != (self._update or {}).get("version"):
                self._update_phase, self._update_error = "available", None
            self._update = offer
            self._publish()
        if offer is not None:
            self._notify_update(offer)
        return False

    def _notify_update(self, offer: dict[str, Any]) -> None:
        """Tell the user once per version; the panel keeps showing it after."""
        state = updates.load_state()
        if not updates.should_notify(offer, state) or self._quiet_now():
            return
        relogin = offer["requires"] == "relogin"
        tail = "Log out afterwards to finish." if relogin else "Restart to apply."
        try:
            send("tokens-go-brrr update", f"Version {offer['version']} is ready. {tail}")
        except Exception as exc:  # noqa: BLE001 - a missing notification daemon must not stop the check
            print(f"update notification failed: {exc}", file=sys.stderr, flush=True)
            return
        updates.save_state({**state, "notified_version": offer["version"]})

    def _visible_update(self) -> dict[str, Any] | None:
        """The offer as the panel sees it, or None if there is nothing to show."""
        offer = self._update
        if not offer or offer["version"] == updates.load_state().get("skipped_version"):
            return None
        return {
            "version": offer["version"],
            "requires": offer["requires"],
            "released": offer["released"],
            "changes": list(offer["changes"]),
            "status": self._update_phase,
            "error": self._update_error,
            # A source install is not changed by a package, so no button for it.
            "installable": updates.installed_from_package(),
        }

    def _set_update_phase(self, phase: str, error: str | None = None) -> bool:
        self._update_phase, self._update_error = phase, error
        self._publish()
        return False

    def install_update(self) -> bool:
        """Download and install the offered release; progress shows in the state."""
        visible = self._visible_update()
        if (
            visible is None
            or not visible["installable"]
            or self._update_phase in ("downloading", "installing", "installed")
        ):
            return False
        self._set_update_phase("downloading")
        threading.Thread(
            target=self._install_worker,
            args=(dict(self._update or {}),),
            name="tokens-go-brrr-install",
            daemon=True,
        ).start()
        return False

    def _install_worker(self, offer: dict[str, Any]) -> None:
        family = updates.distro_family()
        try:
            package = update_install.download(offer)
            GLib.idle_add(self._set_update_phase, "installing")
            update_install.install(package, offer, family)
        except update_install.UpdateError as exc:
            GLib.idle_add(self._set_update_phase, "error", str(exc))
        except Exception as exc:  # noqa: BLE001 - an install failure is reported, never fatal
            GLib.idle_add(self._set_update_phase, "error", f"update failed: {exc}")
        else:
            GLib.idle_add(self._set_update_phase, "installed")

    def restart_daemon(self) -> bool:
        """Start the daemon again so it runs the installed code."""
        if self._update_phase != "installed":
            return False
        try:
            # Detached: systemd stops this process as part of the restart.
            subprocess.Popen(  # noqa: S603 - fixed argv, no user input
                ["systemctl", "--user", "restart", "tokens-go-brrr.service"],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self._set_update_phase("error", f"could not restart: {exc}")
        return False

    def skip_update(self, version: str) -> None:
        """Stop showing this version; the next release shows again."""
        updates.save_state({**updates.load_state(), "skipped_version": version})
        self._publish()

    # -- state ---------------------------------------------------------------

    def state_payload(self) -> dict[str, Any]:
        payload = build_payload(
            self.snapshots,
            version=__version__,
            updated_at=self.last_fetch,
            error=self.last_error,
        )
        # Additive: both fields are new, an older extension ignores them, and
        # nothing that already exists changes meaning, so the state schema
        # version stays as it is. `billboard` is null far more often than not —
        # that is what keeps the landing page from appearing on every open.
        payload["billboard"] = dict(self._billboard) if self._billboard else None
        payload["latestMessage"] = dict(self._latest_message) if self._latest_message else None
        payload["recentMessages"] = [dict(m) for m in self._recent_messages]
        # Additive, like the fields above: true while a warm note is being made.
        payload["live"] = {"catchingUp": bool(self._catching_up)}
        # Additive: null unless a newer release is published for this install.
        payload["update"] = self._visible_update()
        # The five known providers, with who is currently on the panel. The
        # Settings screen uses this to offer Show again for anyone hidden.
        enabled = set(self.config.enabled_providers)
        payload["catalog"] = [
            {
                "id": pid,
                "name": PROVIDERS[pid].display_name,
                "enabled": pid in enabled,
            }
            for pid in DEFAULT_PROVIDERS
            if pid in PROVIDERS
        ]
        return payload

    def _publish(self) -> None:
        payload = self.state_payload()
        try:
            write_state(payload)
        except OSError as exc:
            print(f"Could not write state file: {exc}", file=sys.stderr, flush=True)
        self.service.emit_state(payload)


def run_daemon(config: MonitorConfig) -> int:
    providers = build_providers(config.enabled_providers)
    if not providers:
        print("No providers enabled in config.", file=sys.stderr)
        return 1
    if not any(p.available() for p in providers):
        print(
            "No provider credentials found.\n"
            "Open Cursor and sign in, then run: tokens-go-brrr setup",
            file=sys.stderr,
        )
        return 1
    return UsageDaemon(config).run()
