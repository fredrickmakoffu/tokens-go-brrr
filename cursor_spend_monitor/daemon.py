from __future__ import annotations

import os
import signal
import sys
import threading
from datetime import datetime, timezone
from typing import Any

from gi.repository import GLib

from dataclasses import replace

from . import __version__, burn, history
from .config import MonitorConfig, write_state
from .dbus_service import UsageService
from .instances import InstanceReport, scan, signature
from .notify import AlertManager
from .providers import build_providers
from .providers import pi_backend
from .providers.base import Provider, ProviderSnapshot
from .state import build_payload


class UsageDaemon:
    """Polls providers, raises alerts, and publishes state over D-Bus for the shell extension."""

    def __init__(self, config: MonitorConfig) -> None:
        self.config = config
        self.providers: list[Provider] = build_providers(config.enabled_providers)
        self.alerts = AlertManager(config)
        self.history = history.Recorder(keep_days=config.history_days)
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
            on_refresh=self.poll,
            on_set_primary=self.set_primary,
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
        GLib.idle_add(self.poll)
        GLib.idle_add(self._scan_instances)
        for sig in (signal.SIGINT, signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self._on_signal)

    # -- lifecycle -----------------------------------------------------------

    def run(self) -> int:
        self.loop.run()
        self.service.close()
        self.history.close()
        return 0

    def quit(self, *_args) -> bool:
        self.loop.quit()
        return False

    def _on_signal(self, *_args) -> bool:
        self.quit()
        return False

    def _name_lost(self) -> None:
        print("Another AI usage daemon owns the bus name; exiting.", file=sys.stderr, flush=True)
        self.quit()

    # -- polling -------------------------------------------------------------

    def _tick(self) -> bool:
        self.poll()
        return True

    def poll(self, *_args) -> bool:
        if not self._polling:
            self._polling = True
            threading.Thread(target=self._poll_worker, name="ai-usage-poll", daemon=True).start()
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

            backends = [
                i.backend for i in snap.instances.all if i.backend is not None
            ]
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
            "; ".join(errors) if errors and not any(s.status == "ok" for s in applied) else None
        )
        self._attach_instances()
        self._publish()
        return False

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
            s.with_primary(metric_key) if s.provider_id == provider_id else s for s in self.snapshots
        ]
        self._publish()

    # -- state ---------------------------------------------------------------

    def state_payload(self) -> dict[str, Any]:
        return build_payload(
            self.snapshots,
            version=__version__,
            updated_at=self.last_fetch,
            error=self.last_error,
        )

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
