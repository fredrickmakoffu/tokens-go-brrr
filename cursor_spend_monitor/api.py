from __future__ import annotations

import http.client
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

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


def _as_int(value: Any) -> int:
    """A spend figure as an int. The endpoint returns strings and nulls freely."""
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0


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
            auto_percent=_as_float(plan.get("autoPercentUsed")),
            api_percent=_as_float(plan.get("apiPercentUsed")),
            total_percent=_as_float(plan.get("totalPercentUsed")),
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
        hours, rem = divmod(_as_int(delta.total_seconds()), 3600)
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
        if isinstance(value, (int, float)) or (
            isinstance(value, str) and value.isdigit()
        ):
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
        except (PermissionError, RuntimeError, OSError, ValueError):
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
        # `HTTPSConnection` is TLS by construction — there is no scheme to get
        # wrong and no URL to open, which is why this does not use urllib.
        # Constructed outside the `try` so the `finally` below always has one to
        # close. `HTTPSConnection` does not connect here, so it cannot fail.
        connection = http.client.HTTPSConnection(API2_HOST, timeout=30)
        try:
            connection.request(
                "POST",
                path,
                body=json.dumps(body),
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Connect-Protocol-Version": "1",
                    "User-Agent": "cursor-spend-monitor/0.1",
                },
            )
            response = connection.getresponse()
            status = int(response.status)
            detail = response.read().decode("utf-8", errors="replace")
        except OSError as exc:
            raise RuntimeError(f"Cursor API unreachable: {exc}") from exc
        finally:
            connection.close()

        if status in {401, 403}:
            raise PermissionError(
                "Cursor API rejected the IDE token. Open Cursor and sign in again."
            )
        if status >= 400:
            raise RuntimeError(f"HTTP {status} from {path}: {detail[:200]}")
        try:
            return json.loads(detail)
        except ValueError as exc:
            raise RuntimeError(f"Cursor API returned invalid JSON for {path}") from exc
