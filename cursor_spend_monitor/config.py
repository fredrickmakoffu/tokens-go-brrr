from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .providers import DEFAULT_PROVIDERS

CONFIG_DIR = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "cursor-spend-monitor"
)
CONFIG_FILE = CONFIG_DIR / "config.json"
STATE_FILE = Path(f"/run/user/{os.getuid()}/cursor-spend-monitor/state.json")

DEFAULT_PRIMARY_ALERTS = [75, 90, 100]
DEFAULT_NOTIFY_TYPES = ["informative", "fun", "actionable", "shareable"]
# Local hours during which nothing is delivered: 22:00 through 07:00.
DEFAULT_SILENT_HOURS = [22, 7]


def _as_int(value: Any, default: int) -> int:
    """A config value as an int, falling back rather than raising.

    The config is a file a person can edit, so a typo in it must not stop the
    daemon starting or make every command exit on a traceback.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class MonitorConfig:
    poll_interval_seconds: int = 300
    instance_poll_seconds: int = 3
    alert_cooldown_hours: int = 6
    # Days of samples kept for burn-rate forecasting. 0 disables recording.
    history_days: int = 90
    # Days of raw sessions kept in the usage ledger. The daily/hourly rollups
    # are kept longer, so month-over-month comparisons keep working after the
    # events underneath them are gone.
    ledger_days: int = 90
    # How often the daemon re-reads the heavy stores. `harvest` on the command
    # line is on demand and ignores this.
    harvest_deep_seconds: int = 3600
    # Event trigger: a burn-rate ETA inside this many hours is worth a message.
    wind_down_hours: float = 2.0
    # The notification engine. See `notifications.py` for what each family is.
    notify_enabled: bool = True
    notify_daily_hour: int = 18
    notify_weekly_day: str = "monday"
    notify_types: list[str] = field(default_factory=lambda: list(DEFAULT_NOTIFY_TYPES))
    notify_shareable_share: float = 0.25
    # [start, end] local hours during which nothing is delivered.
    notify_silent_hours: list[int] = field(
        default_factory=lambda: list(DEFAULT_SILENT_HOURS)
    )
    # The LLM is off until a generator is configured: templates are the whole
    # wording layer, and every trigger works without it.
    llm_notifications: bool = False
    llm_generator_provider: str = ""
    llm_generator_model: str = ""
    llm_max_output_tokens: int = 200
    llm_min_headroom: int = 15
    # Live notes (design/LIVE_NOTES_AND_LLM_LOG.md). `live_notes` is the master
    # switch; an open after `live_cold_hours` idle (or a fresh daemon) is "cold"
    # and earns a trend or insight note.
    live_notes: bool = True
    live_cold_hours: float = 4.0
    # A warm note made this recently is served again instead of rebuilt.
    live_hot_minutes: float = 10.0
    # Days of the per-call LLM log to keep; 0 turns the log off.
    llm_log_days: int = 30
    # The landing page: one notification shown as a quote when the popover
    # opens. `billboard_auto_advance_seconds` of 0 means Continue is the only
    # way out; `billboard_freshness_hours` is a ceiling over the per-kind
    # windows in `notify_engine`.
    billboard_enabled: bool = True
    billboard_auto_advance_seconds: int = 0
    billboard_freshness_hours: int = 24
    primary_alerts: list[int] = field(
        default_factory=lambda: list(DEFAULT_PRIMARY_ALERTS)
    )
    enabled_providers: list[str] = field(
        default_factory=lambda: list(DEFAULT_PROVIDERS)
    )
    # provider_id → preferred primary metric key (chip swap)
    primary_overrides: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls) -> MonitorConfig:
        if not CONFIG_FILE.exists():
            return cls()
        try:
            data = json.loads(CONFIG_FILE.read_text())
        except (OSError, ValueError) as exc:
            print(
                f"Could not read {CONFIG_FILE}: {exc}. Using defaults.",
                file=sys.stderr,
                flush=True,
            )
            return cls()
        if not isinstance(data, dict):
            print(
                f"{CONFIG_FILE} is not a JSON object. Using defaults.",
                file=sys.stderr,
                flush=True,
            )
            return cls()
        alerts = data.get("primary_alerts")
        if alerts is None and isinstance(data.get("alerts"), dict):
            alerts = data["alerts"].get("auto_percent") or DEFAULT_PRIMARY_ALERTS
        return cls(
            poll_interval_seconds=_as_int(data.get("poll_interval_seconds"), 300),
            instance_poll_seconds=_as_int(data.get("instance_poll_seconds"), 3),
            alert_cooldown_hours=_as_int(data.get("alert_cooldown_hours"), 6),
            history_days=_as_int(data.get("history_days"), 90),
            ledger_days=_as_int(data.get("ledger_days"), 90),
            harvest_deep_seconds=_as_int(data.get("harvest_deep_seconds"), 3600),
            wind_down_hours=_as_float(data.get("wind_down_hours"), 2.0),
            notify_enabled=bool(data.get("notify_enabled", True)),
            notify_daily_hour=_as_int(data.get("notify_daily_hour"), 18),
            notify_weekly_day=str(data.get("notify_weekly_day") or "monday"),
            notify_types=list(data.get("notify_types") or DEFAULT_NOTIFY_TYPES),
            notify_shareable_share=_as_float(data.get("notify_shareable_share"), 0.25),
            notify_silent_hours=[
                _as_int(x, 0)
                for x in (data.get("notify_silent_hours") or DEFAULT_SILENT_HOURS)
            ],
            llm_notifications=bool(data.get("llm_notifications", False)),
            llm_generator_provider=str(data.get("llm_generator_provider") or ""),
            llm_generator_model=str(data.get("llm_generator_model") or ""),
            llm_max_output_tokens=_as_int(data.get("llm_max_output_tokens"), 200),
            llm_min_headroom=_as_int(data.get("llm_min_headroom"), 15),
            live_notes=bool(data.get("live_notes", True)),
            live_cold_hours=max(0.0, _as_float(data.get("live_cold_hours"), 4.0)),
            live_hot_minutes=max(0.0, _as_float(data.get("live_hot_minutes"), 10.0)),
            llm_log_days=max(0, _as_int(data.get("llm_log_days"), 30)),
            billboard_enabled=bool(
                data.get("billboard_enabled", data.get("quote_panel", True))
            ),
            billboard_auto_advance_seconds=_as_int(
                data.get("billboard_auto_advance_seconds"), 0
            ),
            billboard_freshness_hours=_as_int(
                data.get("billboard_freshness_hours"), 24
            ),
            primary_alerts=[_as_int(x, 0) for x in (alerts or DEFAULT_PRIMARY_ALERTS)],
            enabled_providers=list(data.get("enabled_providers") or DEFAULT_PROVIDERS),
            primary_overrides=dict(data.get("primary_overrides") or {}),
        )

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "poll_interval_seconds": self.poll_interval_seconds,
            "instance_poll_seconds": self.instance_poll_seconds,
            "alert_cooldown_hours": self.alert_cooldown_hours,
            "history_days": self.history_days,
            "ledger_days": self.ledger_days,
            "harvest_deep_seconds": self.harvest_deep_seconds,
            "wind_down_hours": self.wind_down_hours,
            "notify_enabled": self.notify_enabled,
            "notify_daily_hour": self.notify_daily_hour,
            "notify_weekly_day": self.notify_weekly_day,
            "notify_types": self.notify_types,
            "notify_shareable_share": self.notify_shareable_share,
            "notify_silent_hours": self.notify_silent_hours,
            "llm_notifications": self.llm_notifications,
            "llm_generator_provider": self.llm_generator_provider,
            "llm_generator_model": self.llm_generator_model,
            "llm_max_output_tokens": self.llm_max_output_tokens,
            "llm_min_headroom": self.llm_min_headroom,
            "live_notes": self.live_notes,
            "live_cold_hours": self.live_cold_hours,
            "live_hot_minutes": self.live_hot_minutes,
            "llm_log_days": self.llm_log_days,
            "billboard_enabled": self.billboard_enabled,
            "billboard_auto_advance_seconds": self.billboard_auto_advance_seconds,
            "billboard_freshness_hours": self.billboard_freshness_hours,
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
