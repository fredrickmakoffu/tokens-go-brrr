from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cursor-spend-monitor"
CONFIG_FILE = CONFIG_DIR / "config.json"
STATE_FILE = Path(f"/run/user/{os.getuid()}/cursor-spend-monitor/state.json")

DEFAULT_ALERTS = {
    "total_percent": [75, 90, 100],
    "api_percent": [80, 100],
    "auto_percent": [80, 100],
}


@dataclass
class MonitorConfig:
    session_token: str = ""
    poll_interval_seconds: int = 300
    alerts: dict[str, list[int]] = field(default_factory=lambda: dict(DEFAULT_ALERTS))
    alert_cooldown_hours: int = 6
    primary_metric: str = "total_percent"  # total_percent | api_percent | auto_percent

    @classmethod
    def load(cls) -> MonitorConfig:
        if not CONFIG_FILE.exists():
            return cls()
        data = json.loads(CONFIG_FILE.read_text())
        alerts = dict(DEFAULT_ALERTS)
        alerts.update(data.get("alerts") or {})
        return cls(
            session_token=str(data.get("session_token", "") or ""),
            poll_interval_seconds=int(data.get("poll_interval_seconds", 300)),
            alerts=alerts,
            alert_cooldown_hours=int(data.get("alert_cooldown_hours", 6)),
            primary_metric=data.get("primary_metric", "total_percent"),
        )

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "session_token": self.session_token,
            "poll_interval_seconds": self.poll_interval_seconds,
            "alerts": self.alerts,
            "alert_cooldown_hours": self.alert_cooldown_hours,
            "primary_metric": self.primary_metric,
        }
        CONFIG_FILE.write_text(json.dumps(payload, indent=2) + "\n")
        CONFIG_FILE.chmod(0o600)

    def metric_thresholds(self) -> list[tuple[str, list[int]]]:
        return [(name, self.alerts.get(name, [])) for name in DEFAULT_ALERTS]


def write_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")
