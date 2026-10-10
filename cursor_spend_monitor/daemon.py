from __future__ import annotations

import os
import signal
import sqlite3
import sys
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from gi.repository import GLib  # type: ignore  # gi has no stubs

from . import (
    __version__,
    burn,
    harvesters,
    history,
    ledger,
    notify_engine,
)
from . import llm_composer as llm
from . import llm_log
from .config import MonitorConfig, write_state
from .dbus_service import UsageService
from .instances import InstanceReport, scan, signature
from .notify import AlertManager, send
from .providers import build_providers, pi_backend
from .providers.base import Provider, ProviderSnapshot
from .state import build_payload

# How often the notification clock is consulted. The schedule it serves is
# hourly at most, so this only decides how late a digest can be, not how often
# one is sent.
NOTIFY_CHECK_SECONDS = 300


def _as_int(value: Any, default: int = 0) -> int:
    """A config value as an int; a typo is not worth taking the daemon down."""
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _now_ts() -> int:
    try:
        return int(datetime.now(timezone.utc).timestamp())
    except (OSError, OverflowError, ValueError):
        return 0


# Shortest gap between two rounds of provider requests. Matches the floor the
# daemon already clamps its own timer to, so a refresh on open can never make
# more requests than the scheduled polling would.
REFRESH_COOLDOWN_SECONDS = 60


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
        self._harvesting = False
        # When the panel was last opened (monotonic seconds), for the cold tier,
        # and whether a cold note is already being made.
        self._last_open: float | None = None
        self._cold_running = False
        # The first harvest of a run may backfill (Cursor's previous cycle);
        # later ones are strictly incremental.
        self._harvest_full = True
        self._last_slot: dict[str, str] = {}
        self._billboard: dict[str, Any] | None = None
        self._latest_message: dict[str, Any] | None = None
        self._recent_messages: list[dict[str, Any]] = []
        self.snapshots: list[ProviderSnapshot] = []
        self.last_error: str | None = None
        self.last_fetch: datetime | None = None
        self._polling = False
        self._specs = {
            provider.id: list(getattr(provider, "process_specs", []))
            for provider in self.providers
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
            on_acknowledge=self.acknowledge,
            on_llm_log=self.llm_log_payload,
            on_llm_log_clear=self.llm_log_clear,
            on_quit=self.quit,
            on_name_lost=self._name_lost,
        )

        interval = max(60, self.config.poll_interval_seconds)
        GLib.timeout_add_seconds(interval, self._tick)
        # Sessions come and go far faster than quota does, and a scan is local and
        # cheap, so it runs on its own much shorter timer.
        GLib.timeout_add_seconds(
            max(1, self.config.instance_poll_seconds), self._scan_instances
        )
        # The ledger fills itself, on its own slow clock: a harvest reads
        # databases and transcripts that quota polling has no business touching.
        GLib.timeout_add_seconds(
            max(60, self.config.harvest_deep_seconds), self._harvest_tick
        )
        if self.config.notify_enabled:
            GLib.timeout_add_seconds(NOTIFY_CHECK_SECONDS, self._notify_tick)
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
        if self.config.live_notes and (
            notify_engine.tier_for(idle, cold_hours=self.config.live_cold_hours)
            == notify_engine.COLD
        ):
            self._start_cold_note()
        return self.poll(*args)

    def _start_cold_note(self) -> None:
        """Make a cold insight off the main loop, if the person wants one."""
        if self._cold_running or self.ledger.connection is None:
            return
        if not self._wanted(notify_engine.INFORMATIVE):
            return
        self._cold_running = True
        threading.Thread(
            target=self._cold_worker, name="ai-usage-cold", daemon=True
        ).start()

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
            age = (datetime.now(timezone.utc) - self.last_fetch).total_seconds()
            if age < REFRESH_COOLDOWN_SECONDS:
                return False
        self._polling = True
        threading.Thread(
            target=self._poll_worker, name="ai-usage-poll", daemon=True
        ).start()
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
        """Give a harness the meters of the account its sessions are spending on.

        A harness such as Pi holds no subscription. Its live sessions each name
        the account they bill to, so the account most of them are on decides
        which provider's meters the row shows. Nothing is fetched twice: the
        meters are the ones that provider already polled this cycle.

        Three outcomes, all of which the panel has to render:
          - backend metered by an enabled provider that is signed in → borrowed
            meters, marked so they are not counted twice in the status dot
          - backend known but unmeterable (xAI, Cline) → named, no meters
          - no sessions running → no backend, no meters
        """
        by_id = {snap.provider_id: snap for snap in self.snapshots}
        for snap in self.snapshots:
            if not self._is_harness(snap.provider_id):
                continue

            backends = [i.backend for i in snap.instances.all if i.backend is not None]
            backend = pi_backend.dominant(backends)
            snap.backend = backend
            snap.borrowed_from = None
            snap.metrics = []
            snap.primary_key = ""
            snap.plan = backend.model if backend else None

            if backend is None:
                snap.status = "ok"
                snap.error = None
                continue

            source = by_id.get(backend.provider_id) if backend.metered else None
            if source is None or source.status != "ok":
                # Nothing to show a limit from. Say why rather than showing 0%.
                snap.status = "ok"
                snap.error = (
                    f"{backend.name} reports no limits"
                    if not backend.metered
                    else f"Sign in to {backend.name} to show limits"
                )
                continue

            snap.metrics = list(source.metrics)
            snap.primary_key = source.primary_key
            snap.borrowed_from = source.provider_id
            snap.status = "ok"
            snap.error = None
            # Borrowing rewrites primary_key every cycle, so a chip swap the user
            # made on the harness row has to be put back.
            override = self.config.primary_overrides.get(snap.provider_id)
            if override and override in {m.key for m in snap.metrics}:
                snap.primary_key = override

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
        self.snapshots = applied
        self.last_fetch = datetime.now(timezone.utc)
        self.history.record(applied, at=self.last_fetch)
        self._attach_forecasts()
        self.last_error = (
            "; ".join(errors)
            if errors and not any(s.status == "ok" for s in applied)
            else None
        )
        self._attach_instances()
        self._notify_events()
        self._publish()
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
            target=self._harvest_worker, name="ai-usage-harvest", daemon=True
        ).start()
        return True

    def _harvest_worker(self) -> None:
        try:
            # A worker thread needs its own connection: the ledger's belongs to
            # the main loop, and SQLite refuses to let another thread use it.
            with self.ledger.worker() as con:
                if con is None:
                    return
                for reader in harvesters.build():
                    if not reader.available():
                        continue
                    reader.harvest(con, full=self._harvest_full)
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
            name="ai-usage-digest",
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
            print(
                f"Could not build the {slot} digest: {exc}", file=sys.stderr, flush=True
            )
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
    ) -> list[Any]:
        """The templates, reworded by a model when one has capacity to spare.

        Every failure -- no generator with enough headroom, a missing
        credential, a refusal -- leaves the template in place. The LLM is an
        upgrade, and an upgrade that can break the notification path is not one.
        """
        if not (self.config.llm_notifications and messages):
            return messages
        generator = llm.choose(
            self.snapshots,
            trigger=trigger,
            floor=self.config.llm_min_headroom,
            model=self.config.llm_generator_model,
            provider=self.config.llm_generator_provider,
        )
        if generator is None:
            # Worth a line in the log: a person wondering why nothing was
            # reworded can see that no provider had the room.
            self.llm_log.record(
                {
                    "trigger": origin,
                    "outcome": llm_log.SKIPPED,
                    "reason": "no_generator",
                    "message_kind": messages[0].kind,
                    "message_key": messages[0].key,
                }
            )
            return messages
        improved: list[Any] = []
        for message in messages:
            rewritten = llm.rewrite(
                message,
                generator=generator,
                facts=self._facts_for(con, message),
                max_tokens=self.config.llm_max_output_tokens,
                recorder=self.llm_log.record,
                context={"trigger": origin},
            )
            improved.append(rewritten or message)
        return improved

    def llm_log_payload(self, day: str = "") -> dict[str, Any]:
        """One day of the LLM log for the Settings screen; newest day if none."""
        return self.llm_log.payload(day or None)

    def llm_log_clear(self) -> None:
        self.llm_log.clear()

    def _facts_for(self, con: sqlite3.Connection, message: Any) -> dict[str, Any]:
        """The ranked providers the model may choose the featured AI from.

        A trailing month, so the list is stable and always has ids in it; the
        message keeps its own period's numbers, which are already in the draft.
        """
        start, end = notify_engine.day_range(30)
        return {
            "period": str((message.meta or {}).get("period") or "last 30 days"),
            "ranked": ledger.period_totals(
                con, start_day=start, end_day=end, group_by="provider"
            ),
        }

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
            spent = (
                isinstance(percent, (int, float)) and percent >= notify_engine.SPENT_AT
            )
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
            target=self._events_worker, name="ai-usage-event", daemon=True
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
                if not row.get("created_at")
                or now_ts - _as_int(row.get("created_at")) <= ceiling
            ]
        self._billboard = notify_engine.choose_billboard(pending)

        latest = ledger.latest_message(con)
        # `latest_message` is deliberately unfiltered by acknowledgement or
        # freshness: "show me the most recent one" should work months later.
        self._latest_message = (
            notify_engine.billboard_payload(latest) if latest else None
        )
        self._recent_messages = [
            notify_engine.billboard_payload(row)
            for row in ledger.recent_messages(con)
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
        until_reset = (meter.resets_at - datetime.now(timezone.utc)).total_seconds()
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
        payload["latestMessage"] = (
            dict(self._latest_message) if self._latest_message else None
        )
        payload["recentMessages"] = [dict(m) for m in self._recent_messages]
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
            "Open Cursor and sign in, then run: cursor-spend-monitor setup",
            file=sys.stderr,
        )
        return 1
    return UsageDaemon(config).run()
