from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cursor-spend-monitor"
CONFIG_FILE = CONFIG_DIR / "config.json"
STATE_FILE = Path(f"/run/user/{os.getuid()}/cursor-spend-monitor/state.json")

DEFAULT_PRIMARY_ALERTS = [75, 90, 100]


@dataclass
class MonitorConfig:
    poll_interval_seconds: int = 300
    alert_cooldown_hours: int = 6
    primary_alerts: list[int] = field(default_factory=lambda: list(DEFAULT_PRIMARY_ALERTS))
    enabled_providers: list[str] = field(default_factory=lambda: ["cursor"])
    # provider_id → preferred primary metric key (chip swap)
    primary_overrides: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls) -> MonitorConfig:
        if not CONFIG_FILE.exists():
            return cls()
        data = json.loads(CONFIG_FILE.read_text())
        alerts = data.get("primary_alerts")
        if alerts is None and isinstance(data.get("alerts"), dict):
            alerts = data["alerts"].get("auto_percent") or DEFAULT_PRIMARY_ALERTS
        return cls(
            poll_interval_seconds=int(data.get("poll_interval_seconds", 300)),
            alert_cooldown_hours=int(data.get("alert_cooldown_hours", 6)),
            primary_alerts=[int(x) for x in (alerts or DEFAULT_PRIMARY_ALERTS)],
            enabled_providers=list(data.get("enabled_providers") or ["cursor"]),
            primary_overrides=dict(data.get("primary_overrides") or {}),
        )

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "poll_interval_seconds": self.poll_interval_seconds,
            "alert_cooldown_hours": self.alert_cooldown_hours,
            "primary_alerts": self.primary_alerts,
            "enabled_providers": self.enabled_providers,
            "primary_overrides": self.primary_overrides,
        }
        CONFIG_FILE.write_text(json.dumps(payload, indent=2) + "\n")
        CONFIG_FILE.chmod(0o600)

    def set_primary(self, provider_id: str, metric_key: str) -> None:
        self.primary_overrides[provider_id] = metric_key
        self.save()


def write_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")
