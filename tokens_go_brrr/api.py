from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .coerce import as_float_or_none
from .coerce import as_int as _as_int
from .coerce import parse_ms_or_iso as _parse_ms_or_iso
from .http_json import HttpJsonError, request_json
from .local_auth import resolve_access_token

# The API host, kept apart from the scheme: requests below go over an
# `HTTPSConnection`, so https is a property of the code rather than a string
# that has to be validated.
API2_HOST = "api2.cursor.sh"
API2_BASE = f"https://{API2_HOST}"
USAGE_PATH = "/aiserver.v1.DashboardService/GetCurrentPeriodUsage"
PLAN_PATH = "/aiserver.v1.DashboardService/GetPlanInfo"
HARD_LIMIT_PATH = "/aiserver.v1.DashboardService/GetHardLimit"
# Per-model spend for a date range. The range must be epoch milliseconds: the
# server rejects an ISO-8601 string outright (`cannot decode field … start_date`),
# and a range much beyond a quarter answers HTTP 500, so callers pass one
# billing cycle at a time.
AGGREGATED_PATH = "/aiserver.v1.DashboardService/GetAggregatedUsageEvents"
POLICY_PATH = "/aiserver.v1.DashboardService/GetUsageLimitPolicyStatus"


@dataclass
class UsageSummary:
    raw: dict[str, Any]
    membership_type: str
    billing_cycle_start: datetime | None
    billing_cycle_end: datetime | None
    # Utilization fields are None when the dashboard omitted or garbled them —
    # never a healthy 0% invented here (meter policy).
    auto_percent: float | None
    api_percent: float | None
    total_percent: float | None
    auto_message: str
    api_message: str
    plan_used: int
    plan_limit: int
    on_demand_enabled: bool
    on_demand_used: int

    @classmethod
    def from_dashboard(
        cls, data: dict[str, Any], *, membership_type: str = ""
    ) -> UsageSummary:
        plan = data.get("planUsage") or {}
        spend_limit = data.get("spendLimitUsage") or {}
        # Spend figures from api2 are in USD cents
        included = _as_int(plan.get("includedSpend"))
        limit = _as_int(plan.get("limit"))
        on_demand_used = _as_int(
            spend_limit.get("totalSpend") or spend_limit.get("used")
        )
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
            membership_type=membership_type
            or str(data.get("membershipType") or "unknown"),
            billing_cycle_start=_parse_ms_or_iso(data.get("billingCycleStart")),
            billing_cycle_end=_parse_ms_or_iso(data.get("billingCycleEnd")),
            auto_percent=as_float_or_none(plan.get("autoPercentUsed")),
            api_percent=as_float_or_none(plan.get("apiPercentUsed")),
            total_percent=as_float_or_none(plan.get("totalPercentUsed")),
            auto_message=str(data.get("autoModelSelectedDisplayMessage") or ""),
            api_message=str(data.get("namedModelSelectedDisplayMessage") or ""),
            plan_used=included,
            plan_limit=limit,
            on_demand_enabled=on_demand_enabled,
            on_demand_used=on_demand_used,
        )

    def metric(self, name: str) -> float | None:
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
        hours, rem = divmod(_as_int(delta.total_seconds()), 3600)
        if hours >= 48:
            days = hours // 24
            return f"Resets in {days}d"
        if hours >= 1:
            return f"Resets in {hours}h {rem // 60}m"
        return f"Resets in {rem // 60}m"


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
        plan = self._best_effort(PLAN_PATH, auth.access_token)
        if plan:
            plan_name = (plan.get("planInfo") or {}).get("planName")
            membership = plan_name or membership or "unknown"
            usage["_planInfo"] = plan

        hard = self._best_effort(HARD_LIMIT_PATH, auth.access_token)
        if hard:
            usage.update(hard)

        return UsageSummary.from_dashboard(
            usage, membership_type=str(membership).lower()
        )

    def _best_effort(self, path: str, access_token: str) -> dict[str, Any]:
        """An optional endpoint, where a refusal is not a usage failure.

        The plan name and the hard-limit overrides are extras: the usage answer
        stands without them, so a rejection is dropped here instead of taking
        down a poll that succeeded.
        """
        try:
            return self._connect_json(path, access_token)
        except (PermissionError, RuntimeError, OSError, ValueError, HttpJsonError):
            return {}

    def _connect_json(self, path: str, access_token: str) -> dict[str, Any]:
        return self.post_json(path, {}, access_token)

    def post_json(
        self, path: str, body: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        """POST a Connect-RPC body and decode the JSON reply.

        Kept separate from `_connect_json` because some endpoints need a real
        body — the aggregated-usage query takes the range it should sum.
        """
        try:
            return request_json(
                "POST",
                API2_HOST,
                path,
                body=body,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Connect-Protocol-Version": "1",
                },
            )
        except OSError as exc:
            raise RuntimeError(f"Cursor API unreachable: {exc}") from exc
        except HttpJsonError as exc:
            if exc.status in {401, 403}:
                raise PermissionError(
                    "Cursor API rejected the IDE token. Open Cursor and sign in again."
                ) from exc
            raise RuntimeError(
                f"HTTP {exc.status} from {path}: {exc.body[:200]}"
            ) from exc
        except RuntimeError as exc:
            raise RuntimeError(
                f"Cursor API returned invalid JSON for {path}"
            ) from exc
