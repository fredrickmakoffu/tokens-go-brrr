from __future__ import annotations

import sys
import webbrowser
from datetime import datetime, timezone

import gi

gi.require_version("AyatanaAppIndicator3", "0.1")
gi.require_version("Gtk", "3.0")
from gi.repository import AyatanaAppIndicator3 as AppIndicator
from gi.repository import GLib, Gtk

from .api import CursorUsageClient, UsageSummary
from .config import CONFIG_DIR, MonitorConfig, write_state
from .icons import make_icon
from .notify import AlertManager, send


class SpendTray:
    def __init__(self, config: MonitorConfig) -> None:
        self.config = config
        self.client = CursorUsageClient(config.session_token)
        self.alerts = AlertManager(config)
        self.usage: UsageSummary | None = None
        self.last_error: str | None = None
        self.last_fetch: datetime | None = None

        self.indicator = AppIndicator.Indicator.new(
            "cursor-spend-monitor",
            "dialog-information",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Cursor usage")
        # Ensure a concrete icon path early so GNOME paints something immediately
        self.indicator.set_icon_full(str(make_icon(0)), "Cursor usage")

        self.menu = Gtk.Menu()
        self._items: dict[str, Gtk.MenuItem] = {}
        self._build_menu()
        self.indicator.set_menu(self.menu)

        interval_ms = max(60, self.config.poll_interval_seconds) * 1000
        GLib.timeout_add(interval_ms, self._poll)
        GLib.idle_add(self._poll)

    def _build_menu(self) -> None:
        labels = [
            ("header", "Cursor Usage"),
            ("total", "Total: —"),
            ("auto", "Cursor models: —"),
            ("api", "Other models: —"),
            ("reset", "Billing reset: —"),
            ("plan", "Plan quota: —"),
            ("ondemand", "On-demand: —"),
            ("sep1", None),
            ("updated", "Last updated: —"),
            ("sep2", None),
            ("refresh", "Refresh now"),
            ("dashboard", "Open spending dashboard"),
            ("config", "Open config folder"),
            ("sep3", None),
            ("quit", "Quit"),
        ]
        for key, label in labels:
            if label is None:
                self.menu.append(Gtk.SeparatorMenuItem())
                continue
            item = Gtk.MenuItem(label=label)
            item.set_sensitive(key not in {"header", "total", "auto", "api", "reset", "plan", "ondemand", "updated"})
            if key == "refresh":
                item.connect("activate", lambda *_: self._poll())
            elif key == "dashboard":
                item.connect("activate", lambda *_: webbrowser.open("https://cursor.com/dashboard/spending"))
            elif key == "config":
                item.connect("activate", lambda *_: self._open_config())
            elif key == "quit":
                item.connect("activate", lambda *_: Gtk.main_quit())
            self.menu.append(item)
            self._items[key] = item
        self.menu.show_all()

    def _open_config(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        webbrowser.open(f"file://{CONFIG_DIR}")

    def _set_label(self, key: str, text: str) -> None:
        item = self._items.get(key)
        if item:
            item.set_label(text)

    def _poll(self, *_args) -> bool:
        try:
            self.usage = self.client.fetch()
            self.last_error = None
            self.last_fetch = datetime.now(timezone.utc)
            self._update_ui()
            self.alerts.check(self.usage)
            write_state(self._state_payload())
        except Exception as exc:  # noqa: BLE001 — show in tray, keep polling
            self.last_error = str(exc)
            self._update_error(str(exc))
        return True

    def _state_payload(self) -> dict:
        usage = self.usage
        return {
            "updated_at": self.last_fetch.isoformat() if self.last_fetch else None,
            "error": self.last_error,
            "membership_type": usage.membership_type if usage else None,
            "total_percent": usage.total_percent if usage else None,
            "api_percent": usage.api_percent if usage else None,
            "auto_percent": usage.auto_percent if usage else None,
        }

    def _update_error(self, message: str) -> None:
        icon = make_icon(None, error=True)
        self.indicator.set_icon_full(str(icon), f"Cursor usage error: {message}")
        self._set_label("header", "Cursor Usage — error")
        self._set_label("total", message[:80])
        write_state(self._state_payload())

    def _update_ui(self) -> None:
        usage = self.usage
        if not usage:
            return

        primary = usage.metric(self.config.primary_metric)
        icon = make_icon(primary)
        self.indicator.set_icon_full(str(icon), f"Cursor usage {primary:.0f}%")
        self.indicator.set_label(f"{primary:.0f}%", "")

        self._set_label("header", f"Cursor Usage — {usage.membership_type.title()}")
        self._set_label("total", f"Total included: {usage.total_percent:.0f}%")
        self._set_label("auto", f"Cursor models: {usage.auto_percent:.0f}%")
        self._set_label("api", f"Other models: {usage.api_percent:.0f}%")
        self._set_label("reset", f"Billing reset: {usage.reset_label()}")
        self._set_label("plan", f"Plan quota: {usage.plan_used}/{usage.plan_limit}")
        on_demand = "enabled" if usage.on_demand_enabled else "disabled"
        self._set_label("ondemand", f"On-demand: {on_demand} ({usage.on_demand_used} used)")
        if self.last_fetch:
            local = self.last_fetch.astimezone()
            self._set_label("updated", f"Last updated: {local.strftime('%H:%M:%S')}")


def run_tray(config: MonitorConfig) -> int:
    # Auth comes from Cursor IDE local tokens; session_token is optional legacy.
    from .local_auth import read_local_auth

    if not read_local_auth() and not config.session_token:
        print(
            "No Cursor IDE login found.\n"
            "Open Cursor and sign in, then run: cursor-spend-monitor setup",
            file=sys.stderr,
        )
        return 1

    try:
        Gtk.init(sys.argv)
    except Exception:
        pass

    SpendTray(config)
    Gtk.main()
    return 0
