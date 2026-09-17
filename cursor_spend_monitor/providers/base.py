from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from .. import burn
from ..instances import InstanceReport, ProcessSpec


@dataclass(frozen=True)
class Meter:
    key: str
    label: str
    percent: float
    resets_at: datetime | None = None
    # Seconds until this meter is spent at the rate it has been going, or None
    # when the history says nothing trustworthy. Filled in by the daemon, which
    # is the only part that holds the sample series.
    eta_seconds: float | None = None

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
    # Set on a harness that spends against another account: the backend its live
    # sessions are on, and — when one of our providers meters that account — the
    # id whose meters were copied onto this snapshot. `borrowed_from` being set
    # is what marks these metrics as somebody else's, so the status dot does not
    # count the same subscription twice.
    backend: Any = None          # providers.pi_backend.Backend
    borrowed_from: str | None = None

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
        if self.backend is not None:
            return f"{self.display_name} · via {self.backend.name}"
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
            backend=self.backend,
            borrowed_from=self.borrowed_from,
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
            "via": self._via_dict(),
            "metrics": [
                {
                    "key": m.key,
                    "label": m.label,
                    "value": int(round(m.percent)),
                    "resets": m.resets_label(),
                    "eta": burn.eta_label(m.eta_seconds),
                    "etaSeconds": m.eta_seconds,
                }
                for m in self.metrics
            ],
        }

    def _via_dict(self) -> dict[str, Any] | None:
        """What the panel needs to say "running on somebody else's account"."""
        if self.backend is None:
            return None
        via = self.backend.to_dict()
        via["borrowed"] = self.borrowed_from is not None
        via["from"] = self.borrowed_from or ""
        return via

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
