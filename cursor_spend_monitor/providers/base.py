from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from ..instances import InstanceReport, ProcessSpec


@dataclass(frozen=True)
class Meter:
    key: str
    label: str
    percent: float
    resets_at: datetime | None = None

    def resets_label(self) -> str:
        if self.resets_at is None:
            return "—"
        now = datetime.now(timezone.utc)
        delta = self.resets_at - now
        secs = int(delta.total_seconds())
        if secs <= 0:
            return "Resets soon"
        hours, rem = divmod(secs, 3600)
        if hours >= 48:
            return f"Resets in {hours // 24} days"
        if hours >= 1:
            mins = rem // 60
            if mins:
                return f"Resets in {hours}h {mins}m"
            return f"Resets in {hours}h"
        return f"Resets in {rem // 60}m"


@dataclass
class ProviderSnapshot:
    provider_id: str
    display_name: str
    icon: str
    plan: str | None
    metrics: list[Meter]
    primary_key: str
    dashboard_url: str | None = None
    status: str = "ok"  # ok | error | auth_needed | soon
    error: str | None = None
    fetched_at: datetime | None = None
    instances: InstanceReport = field(default_factory=InstanceReport)

    @property
    def primary(self) -> Meter:
        for meter in self.metrics:
            if meter.key == self.primary_key:
                return meter
        return self.metrics[0] if self.metrics else Meter("—", "—", 0.0)

    @property
    def secondary(self) -> Meter | None:
        for meter in self.metrics:
            if meter.key != self.primary_key:
                return meter
        return None

    def header(self) -> str:
        if self.plan:
            return f"{self.display_name} · {self.plan}"
        return self.display_name

    def reset_display(self) -> str:
        return self.primary.resets_label().replace("Resets in ", "")

    def with_primary(self, key: str) -> ProviderSnapshot:
        keys = {m.key for m in self.metrics}
        if key not in keys:
            return self
        return ProviderSnapshot(
            provider_id=self.provider_id,
            display_name=self.display_name,
            icon=self.icon,
            plan=self.plan,
            metrics=list(self.metrics),
            primary_key=key,
            dashboard_url=self.dashboard_url,
            status=self.status,
            error=self.error,
            fetched_at=self.fetched_at,
            instances=self.instances,
        )

    def to_panel_dict(self) -> dict[str, Any]:
        return {
            "id": self.provider_id,
            "name": self.display_name,
            "icon": self.icon,
            "plan": self.plan,
            "primary": self.primary_key,
            "status": self.status,
            "error": self.error,
            "dashboardUrl": self.dashboard_url,
            "instances": self.instances.to_dict(),
            "metrics": [
                {
                    "key": m.key,
                    "label": m.label,
                    "value": int(round(m.percent)),
                    "resets": m.resets_label(),
                }
                for m in self.metrics
            ],
        }

    @classmethod
    def error_snapshot(
        cls,
        *,
        provider_id: str,
        display_name: str,
        message: str,
        icon: str = "cursor",
        auth_needed: bool = False,
        dashboard_url: str | None = None,
    ) -> ProviderSnapshot:
        return cls(
            provider_id=provider_id,
            display_name=display_name,
            icon=icon,
            plan=None,
            metrics=[Meter("—", "—", 0.0)],
            primary_key="—",
            dashboard_url=dashboard_url,
            status="auth_needed" if auth_needed else "error",
            error=message,
            fetched_at=datetime.now(timezone.utc),
        )


class Provider(Protocol):
    id: str
    display_name: str
    # How to recognise this tool's running sessions. Empty means it reports none.
    process_specs: list[ProcessSpec]

    def available(self) -> bool:
        """True when credentials/local state suggest this provider can be polled."""

    def fetch(self) -> ProviderSnapshot:
        ...
