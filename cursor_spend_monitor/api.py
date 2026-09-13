from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .local_auth import LocalCursorAuth, resolve_access_token

API2_BASE = "https://api2.cursor.sh"
USAGE_PATH = "/aiserver.v1.DashboardService/GetCurrentPeriodUsage"
PLAN_PATH = "/aiserver.v1.DashboardService/GetPlanInfo"
HARD_LIMIT_PATH = "/aiserver.v1.DashboardService/GetHardLimit"


@dataclass
class UsageSummary:
    raw: dict[str, Any]
    membership_type: str
    billing_cycle_start: datetime | None
    billing_cycle_end: datetime | None
    auto_percent: float
    api_percent: float
    total_percent: float
    auto_message: str
    api_message: str
    plan_used: int
    plan_limit: int
    on_demand_enabled: bool
    on_demand_used: int

    @classmethod
    def from_dashboard(cls, data: dict[str, Any], *, membership_type: str = "") -> UsageSummary:
        plan = data.get("planUsage") or {}
        spend_limit = data.get("spendLimitUsage") or {}
        # Spend figures from api2 are in USD cents
        included = int(plan.get("includedSpend") or 0)
        limit = int(plan.get("limit") or 0)
        on_demand_used = int(spend_limit.get("totalSpend") or spend_limit.get("used") or 0)
        on_demand_enabled = bool(
            spend_limit.get("enabled")
            if "enabled" in spend_limit
            else spend_limit.get("limitType") not in (None, "", "none")
            and not spend_limit.get("noUsageBasedAllowed", False)
        )
        # Better signal from hard-limit endpoint if merged into raw
        if "noUsageBasedAllowed" in data:
            on_demand_enabled = not bool(data.get("noUsageBasedAllowed"))

        return cls(
            raw=data,
            membership_type=membership_type or str(data.get("membershipType") or "unknown"),
            billing_cycle_start=_parse_ms_or_iso(data.get("billingCycleStart")),
            billing_cycle_end=_parse_ms_or_iso(data.get("billingCycleEnd")),
            auto_percent=float(plan.get("autoPercentUsed") or 0),
            api_percent=float(plan.get("apiPercentUsed") or 0),
            total_percent=float(plan.get("totalPercentUsed") or 0),
            auto_message=str(data.get("autoModelSelectedDisplayMessage") or ""),
            api_message=str(data.get("namedModelSelectedDisplayMessage") or ""),
            plan_used=included,
            plan_limit=limit,
            on_demand_enabled=on_demand_enabled,
            on_demand_used=on_demand_used,
        )

    def metric(self, name: str) -> float:
        return {
            "auto_percent": self.auto_percent,
            "api_percent": self.api_percent,
            "total_percent": self.total_percent,
        }.get(name, self.total_percent)

    def reset_label(self) -> str:
        if not self.billing_cycle_end:
            return "Unknown"
        now = datetime.now(timezone.utc)
        delta = self.billing_cycle_end - now
        if delta.total_seconds() <= 0:
            return "Resets soon"
        hours, rem = divmod(int(delta.total_seconds()), 3600)
        if hours >= 48:
            days = hours // 24
            return f"Resets in {days}d"
        if hours >= 1:
            return f"Resets in {hours}h {rem // 60}m"
        return f"Resets in {rem // 60}m"


def _parse_ms_or_iso(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        # api2 returns unix ms as strings
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            ms = int(value)
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, OSError, OverflowError):
        return None


class CursorUsageClient:
    """Fetch usage via api2.cursor.sh using the local Cursor IDE login."""

    def __init__(self, session_token: str = "") -> None:
        # session_token kept for backward compatibility with older configs; unused.
        self.session_token = (session_token or "").strip()

    def fetch(self) -> UsageSummary:
        auth = resolve_access_token()
        try:
            usage = self._connect_json(USAGE_PATH, auth.access_token)
        except PermissionError:
            # One refresh+retry if the local access token was revoked early
            auth = resolve_access_token()
            if not auth.refresh_token:
                raise
            from .local_auth import refresh_access_token, write_tokens

            access, refresh = refresh_access_token(auth.refresh_token)
            write_tokens(access, refresh)
            auth.access_token = access
            usage = self._connect_json(USAGE_PATH, auth.access_token)

        membership = auth.membership_type
        try:
            plan = self._connect_json(PLAN_PATH, auth.access_token)
            membership = (
                ((plan.get("planInfo") or {}).get("planName") or membership or "unknown")
            )
            usage["_planInfo"] = plan
        except Exception:
            pass

        try:
            hard = self._connect_json(HARD_LIMIT_PATH, auth.access_token)
            usage.update(hard)
        except Exception:
            pass

        return UsageSummary.from_dashboard(usage, membership_type=str(membership).lower())

    def _connect_json(self, path: str, access_token: str) -> dict[str, Any]:
        req = urllib.request.Request(
            f"{API2_BASE}{path}",
            data=b"{}",
            method="POST",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Connect-Protocol-Version": "1",
                "User-Agent": "cursor-spend-monitor/0.1",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            if exc.code in {401, 403}:
                raise PermissionError(
                    "Cursor API rejected the IDE token. Open Cursor and sign in again."
                ) from exc
            raise RuntimeError(f"HTTP {exc.code} from {path}: {detail}") from exc
