from __future__ import annotations

import json
import time

import gi

gi.require_version("Notify", "0.7")
from gi.repository import Notify

from .config import CONFIG_DIR, MonitorConfig
from .providers.base import ProviderSnapshot

ALERT_STATE_FILE = CONFIG_DIR / "alert-state.json"


def init_notifications() -> None:
    if not Notify.is_initted():
        Notify.init("cursor-spend-monitor")


def send(title: str, body: str, *, urgency: str = "normal") -> None:
    init_notifications()
    notification = Notify.Notification.new(title, body, "dialog-warning")
    urgency_map = {
        "low": Notify.Urgency.LOW,
        "normal": Notify.Urgency.NORMAL,
        "critical": Notify.Urgency.CRITICAL,
    }
    notification.set_urgency(urgency_map.get(urgency, Notify.Urgency.NORMAL))
    notification.show()


class AlertManager:
    def __init__(self, config: MonitorConfig) -> None:
        self.config = config
        self._state = self._load_state()

    def _load_state(self) -> dict[str, float]:
        if not ALERT_STATE_FILE.exists():
            return {}
        try:
            return json.loads(ALERT_STATE_FILE.read_text())
        except json.JSONDecodeError:
            return {}

    def _save_state(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        ALERT_STATE_FILE.write_text(json.dumps(self._state, indent=2) + "\n")

    def check(self, snapshot: ProviderSnapshot) -> None:
        if snapshot.status != "ok":
            return
        cooldown = self.config.alert_cooldown_hours * 3600
        now = time.time()
        value = snapshot.primary.percent
        label = snapshot.primary.label

        for threshold in sorted(self.config.primary_alerts):
            if value < threshold:
                continue
            key = f"{snapshot.provider_id}:primary:{threshold}"
            last = self._state.get(key, 0)
            if now - last < cooldown:
                continue
            self._state[key] = now
            urgency = "critical" if threshold >= 100 or value >= 95 else "normal"
            send(
                f"{snapshot.display_name} · {label} {threshold}%",
                f"{label} is at {value:.0f}% (threshold {threshold}%).",
                urgency=urgency,
            )
        self._save_state()
