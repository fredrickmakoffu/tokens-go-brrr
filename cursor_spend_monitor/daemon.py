from __future__ import annotations

import signal
import sys
import threading
from datetime import datetime, timezone
from typing import Any

from gi.repository import GLib

from . import __version__
from .config import MonitorConfig, write_state
from .dbus_service import UsageService
from .notify import AlertManager
from .providers import build_providers
from .providers.base import Provider, ProviderSnapshot


class UsageDaemon:
    """Polls providers, raises alerts, and publishes state over D-Bus for the shell extension."""

    def __init__(self, config: MonitorConfig) -> None:
        self.config = config
        self.providers: list[Provider] = build_providers(config.enabled_providers)
        self.alerts = AlertManager(config)
        self.snapshots: list[ProviderSnapshot] = []
        self.last_error: str | None = None
        self.last_fetch: datetime | None = None
        self._polling = False
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
        GLib.idle_add(self.poll)
        for sig in (signal.SIGINT, signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self._on_signal)

    # -- lifecycle -----------------------------------------------------------

    def run(self) -> int:
        self.loop.run()
        self.service.close()
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

    def _apply_snapshots(self, snapshots: list[ProviderSnapshot]) -> bool:
        self._polling = False
        applied: list[ProviderSnapshot] = []
        errors: list[str] = []
        for snap in snapshots:
            snap = self._apply_override(snap)
            applied.append(snap)
            if snap.status != "ok":
                errors.append(snap.error or snap.status)
            else:
                self.alerts.check(snap)
        self.snapshots = applied
        self.last_fetch = datetime.now(timezone.utc)
        self.last_error = (
            "; ".join(errors) if errors and not any(s.status == "ok" for s in applied) else None
        )
        self._publish()
        return False

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
        return {
            "version": __version__,
            "updated_at": self.last_fetch.isoformat() if self.last_fetch else None,
            "error": self.last_error,
            "tools": [s.to_panel_dict() for s in self.snapshots],
        }

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
