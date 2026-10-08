"""Read Cursor's per-model spend from its dashboard API.

Cursor is the one source with no local usage record worth having: the IDE's
`ai-code-tracking.db` counts suggestions, not tokens, and the spend lives behind
`api2.cursor.sh`. The dashboard's own per-model table is served by
`GetAggregatedUsageEvents`, which takes an epoch-millisecond range and answers
with one row per *model intent*.

What the endpoints were found to actually return (probed against the live
account, because the design's field list was a guess):

* `GetAggregatedUsageEvents` needs `{"startDate": ms, "endDate": ms}`. An empty
  body returns `{}`; an ISO-8601 string is rejected with
  `cannot decode field … start_date`; a range beyond roughly a quarter answers
  HTTP 500. So this reader asks for exactly one billing cycle.
* Each `aggregations[]` row carries `modelIntent` (a real model name —
  `claude-opus-5-thinking-high`, `gpt-5.3-codex`, `default`), `tier`,
  `inputTokens`, `outputTokens`, `cacheReadTokens` (all **strings**) and
  `totalCents` (a float, sometimes null). There is no cache-write figure.
* `GetUsageLimitPolicyStatus` returns only `canConfigureSpendLimit` and
  `creditRequestButtonHidden` — **no slow-pool flag**, contrary to the design.

`totalCents` is taken at face value as USD cents, but the reader does not
*assert* that: it records a cross-check every run comparing the row sum against
the response's own total and the plan's figures, so a wrong unit shows up as a
visible disagreement instead of a silently wrong number.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Protocol

from .. import ledger
from ..api import AGGREGATED_PATH, POLICY_PATH, USAGE_PATH, CursorUsageClient
from ..local_auth import read_local_auth
from .base import HarvestResult

HARVESTER_ID = "cursor_api"
PROVIDER = "cursor"

# The response shape this reader was written against. Bumped when a field it
# depends on moves, so the movement is recorded rather than misread.
READER_VERSION = 1

# Flipped once the collected evidence confirms the cost unit. Until then the
# reader records the relationship rather than trusting it.
COST_UNIT_CONFIRMED = False


def _as_int(value: Any) -> int:
    """Cursor sends token counts as strings; a malformed one becomes 0."""
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _ms(value: Any) -> int | None:
    """A millisecond timestamp from either a number or a numeric string."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _day_of_ms(value: Any) -> str | None:
    stamp = _ms(value)
    if stamp is None:
        return None
    return datetime.fromtimestamp(stamp / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


class _JsonClient(Protocol):
    """The one capability this reader needs, so a test can supply its own."""

    def post_json(
        self, path: str, body: dict[str, Any], access_token: str
    ) -> dict[str, Any]: ...


class CursorApiHarvester:
    id = HARVESTER_ID
    provider = PROVIDER

    def __init__(self, client: _JsonClient | None = None) -> None:
        self._client: _JsonClient = client or CursorUsageClient()

    def available(self) -> bool:
        return read_local_auth() is not None

    def harvest(self, con: sqlite3.Connection, *, full: bool = False) -> HarvestResult:
        result = HarvestResult(harvester=self.id, provider=self.provider)
        if not self.available():
            result.note = "not signed in"
            return result

        try:
            token = self._token()
            period = self._client.post_json(USAGE_PATH, {}, token)
        except (PermissionError, RuntimeError, OSError, ValueError) as exc:
            result.failed = True
            result.note = f"cursor usage unavailable: {exc}"
            return result

        start = _ms(period.get("billingCycleStart"))
        end = _ms(period.get("billingCycleEnd"))
        if start is None or end is None or end <= start:
            result.failed = True
            result.note = "cursor reported no billing cycle"
            return result
        cycle_key = _day_of_ms(end) or ""

        try:
            payload = self._client.post_json(
                AGGREGATED_PATH, {"startDate": start, "endDate": end}, token
            )
        except (PermissionError, RuntimeError, OSError, ValueError) as exc:
            result.failed = True
            result.note = f"cursor aggregation unavailable: {exc}"
            return result

        rows = self._rows(payload, cycle_key)
        # A cycle that has just started is usually empty. On a first run (or a
        # full one) the window immediately before it is asked for as well: when
        # cycles are equal length that window *is* the previous cycle, so the
        # ledger starts with real history instead of waiting a month for it.
        if full or not ledger.watermark(con, self.id)[0]:
            span = end - start
            try:
                earlier = self._client.post_json(
                    AGGREGATED_PATH,
                    {"startDate": start - span, "endDate": start},
                    token,
                )
            except (PermissionError, RuntimeError, OSError, ValueError):
                earlier = {}
            rows += self._rows(earlier, _day_of_ms(start) or "")
        result.scanned = len(rows)
        result.per_model = ledger.upsert_per_model(con, rows)

        self._record_checks(con, period, payload, rows, token, cycle_key)
        ledger.set_reader_format(con, self.id, READER_VERSION)
        ledger.set_watermark(
            con,
            self.id,
            cycle_key,
            note=f"{result.scanned} model row(s) for cycle ending {cycle_key}",
        )
        result.watermark = cycle_key
        if not rows:
            result.note = "cursor returned no per-model rows for this cycle"
        return result

    def _token(self) -> str:
        from ..local_auth import resolve_access_token

        return resolve_access_token().access_token

    def _rows(
        self, payload: dict[str, Any], cycle_key: str
    ) -> list[ledger.PerModelRow]:
        aggregations = payload.get("aggregations")
        if not isinstance(aggregations, list):
            return []
        rows: list[ledger.PerModelRow] = []
        for entry in aggregations:
            if not isinstance(entry, dict):
                continue
            intent = entry.get("modelIntent")
            if not intent:
                continue
            cents = _as_float(entry.get("totalCents"))
            rows.append(
                ledger.PerModelRow(
                    provider=self.provider,
                    model=str(intent),
                    cycle_key=cycle_key,
                    # Cursor reports no cache-write figure at all.
                    tokens_input=_as_int(entry.get("inputTokens")),
                    tokens_output=_as_int(entry.get("outputTokens")),
                    tokens_cache_read=_as_int(entry.get("cacheReadTokens")),
                    cost_usd=(cents / 100) if cents is not None else None,
                )
            )
        return rows

    def _record_checks(
        self,
        con: sqlite3.Connection,
        period: dict[str, Any],
        payload: dict[str, Any],
        rows: list[ledger.PerModelRow],
        token: str,
        cycle_key: str,
    ) -> None:
        """Record what the numbers are, not what we assumed them to be."""
        # Only the rows belonging to the cycle the response total describes. A
        # first or full harvest also fetches the window before this cycle, and
        # summing both against one cycle's total is what made this check report a
        # ~30x "unit" disagreement that was really two cycles added together.
        summed = (
            sum(row.cost_usd or 0 for row in rows if row.cycle_key == cycle_key) * 100
        )
        reported = _as_float(payload.get("totalCostCents"))
        plan = period.get("planUsage") or {}
        limit = _as_int(plan.get("limit"))
        percent_used = _as_int(plan.get("totalPercentUsed"))
        detail = (
            f"rows sum to {summed:.2f} cents, response total "
            f"{'—' if reported is None else format(reported, '.2f')}; "
            f"plan limit {limit}, totalPercentUsed {percent_used}; "
            f"unit {'assumed cents' if not COST_UNIT_CONFIRMED else 'confirmed'}"
        )
        # A sum far above the plan limit while the plan reports no usage means
        # the two figures are not the same unit. That is worth seeing, not
        # silently reconciling.
        implausible = bool(limit and summed > limit * 2 and percent_used == 0)
        ledger.record_check(
            con,
            ledger.CheckRow(
                provider=self.provider,
                kind="cost_unit",
                detail=detail,
                ok=not implausible,
            ),
        )
        policy = self._policy(token)
        if policy:
            ledger.record_check(
                con,
                ledger.CheckRow(
                    provider=self.provider,
                    kind="slow_pool_probe",
                    detail=f"policy endpoint returned {sorted(policy)}; no slow-pool flag",
                    ok=True,
                ),
            )

    def _policy(self, token: str) -> dict[str, Any]:
        """Best-effort policy probe; a refusal is not a harvest failure."""
        try:
            return self._client.post_json(POLICY_PATH, {}, token)
        except (PermissionError, RuntimeError, OSError, ValueError):
            return {}
