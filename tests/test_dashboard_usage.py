"""Tests for the Cursor API reader.

The reader talks to a live dashboard endpoint, so the tests drive a fake client
with payloads copied from what the endpoint actually returned. That matters more
than usual here: the response shape was probed rather than documented, and the
unit of `totalCents` is not yet confirmed, so the cross-check it records is part
of the contract these tests pin.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tokens_go_brrr import ledger
from tokens_go_brrr.api import AGGREGATED_PATH, POLICY_PATH, USAGE_PATH
from tokens_go_brrr.harvesters.dashboard_usage import CursorApiHarvester

CYCLE_END_MS = int(datetime(2026, 11, 1, tzinfo=UTC).timestamp() * 1000)
CYCLE_START_MS = int(datetime(2026, 10, 1, tzinfo=UTC).timestamp() * 1000)

# A stub session value for the fake auth. Held in a name rather than written at
# the call site so it does not read as a credential.
SESSION_VALUE = "stub-session"


def period(*, limit: int = 2000, percent: int = 0) -> dict:
    return {
        "billingCycleStart": CYCLE_START_MS,
        "billingCycleEnd": CYCLE_END_MS,
        "planUsage": {
            "includedSpend": None,
            "limit": limit,
            "autoPercentUsed": 0,
            "apiPercentUsed": 0,
            "totalPercentUsed": percent,
        },
        "spendLimitUsage": {"totalSpend": None, "limit": None, "limitType": "user"},
    }


def aggregated(rows: list[dict] | None = None) -> dict:
    rows = (
        rows
        if rows is not None
        else [
            {
                "modelIntent": "claude-opus-5-thinking-high",
                "inputTokens": "1000",
                "outputTokens": "200",
                "cacheReadTokens": "5000",
                "totalCents": 1163.848525,
                "tier": 1,
            },
            {
                "modelIntent": "default",
                "inputTokens": "6880277",
                "outputTokens": "590431",
                "cacheReadTokens": "86083712",
                "totalCents": 6046.7692,
                "tier": 2,
            },
        ]
    )
    return {
        "aggregations": rows,
        "totalInputTokens": "6881277",
        "totalOutputTokens": "590631",
        "totalCacheReadTokens": "86088712",
        "totalCostCents": sum(r.get("totalCents") or 0 for r in rows),
    }


def cents(total: float) -> dict:
    """One model, one figure: the shape the cost cross-check compares."""
    return aggregated(
        [
            {
                "modelIntent": "default",
                "inputTokens": "1",
                "outputTokens": "1",
                "cacheReadTokens": "0",
                "totalCents": total,
                "tier": 1,
            }
        ]
    )


class FakeClient:
    """Answers each endpoint from a fixture, so no test touches the network."""

    def __init__(
        self,
        *,
        period_payload=None,
        aggregated_payload=None,
        earlier_payload=None,
        policy_payload=None,
        fail_path=None,
    ):
        self.period_payload = period_payload if period_payload is not None else period()
        self.aggregated_payload = (
            aggregated_payload if aggregated_payload is not None else aggregated()
        )
        # What the window before this cycle answers with. None means the same
        # payload as the current cycle, which is the common case.
        self.earlier_payload = earlier_payload
        self.aggregations = 0
        self.policy_payload = policy_payload if policy_payload is not None else {}
        self.fail_path = fail_path
        self.calls: list[str] = []
        self.call_args: list[tuple] = []

    def post_json(self, path: str, body: dict, access_token: str) -> dict:
        self.calls.append(path)
        self.call_args.append((path, body))
        if self.fail_path == path:
            raise RuntimeError(f"HTTP 500 from {path}")
        if path == USAGE_PATH:
            return self.period_payload
        if path == AGGREGATED_PATH:
            self.aggregations += 1
            if self.aggregations > 1 and self.earlier_payload is not None:
                return self.earlier_payload
            return self.aggregated_payload
        if path == POLICY_PATH:
            return self.policy_payload
        return {}


class CursorCase(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.con = ledger.connect(Path(self._dir.name) / "usage.db")
        self.addCleanup(self.con.close)
        self.auth = mock.patch(
            "tokens_go_brrr.harvesters.dashboard_usage.read_local_auth",
            return_value=SimpleNamespace(access_token=SESSION_VALUE),
        )
        self.auth.start()
        self.addCleanup(self.auth.stop)
        token = mock.patch(
            "tokens_go_brrr.local_auth.resolve_access_token",
            return_value=SimpleNamespace(access_token=SESSION_VALUE),
        )
        token.start()
        self.addCleanup(token.stop)

    def harvester(self, client: FakeClient) -> CursorApiHarvester:
        return CursorApiHarvester(client=client)

    def per_model(self) -> list[tuple]:
        return self.con.execute(
            "SELECT model, cycle_key, tokens_input, tokens_output,"
            " tokens_cache_read, cost_usd FROM per_model ORDER BY model"
        ).fetchall()

    def checks(self) -> list[tuple]:
        return self.con.execute("SELECT kind, detail, ok FROM checks ORDER BY id").fetchall()


class ReadingTest(CursorCase):
    def test_rows_are_written_per_model_intent(self):
        result = self.harvester(FakeClient()).harvest(self.con)
        # Two intents for the current cycle plus the same two backfilled from the
        # previous one.
        self.assertEqual(result.per_model, 4)
        rows = {row[0]: row for row in self.per_model()}
        self.assertIn("claude-opus-5-thinking-high", rows)
        self.assertIn("default", rows)

    def test_string_token_counts_are_parsed(self):
        self.harvester(FakeClient()).harvest(self.con)
        row = {r[0]: r for r in self.per_model()}["default"]
        self.assertEqual(row[2], 6880277)
        self.assertEqual(row[3], 590431)
        self.assertEqual(row[4], 86083712)

    def test_cost_is_taken_as_cents(self):
        self.harvester(FakeClient()).harvest(self.con)
        row = {r[0]: r for r in self.per_model()}["default"]
        self.assertAlmostEqual(row[5], 60.467692)

    def test_the_cycle_key_is_the_billing_cycle_end(self):
        self.harvester(FakeClient()).harvest(self.con)
        keys = {r[1] for r in self.per_model()}
        self.assertIn("2026-11-01", keys)  # the cycle in progress
        self.assertIn("2026-10-01", keys)  # the one backfilled behind it

    def test_a_null_cost_stays_null_rather_than_becoming_zero(self):
        payload = aggregated(
            [
                {
                    "modelIntent": "gemini-3.1-pro",
                    "inputTokens": "5",
                    "outputTokens": "1",
                    "cacheReadTokens": "0",
                    "totalCents": None,
                    "tier": 1,
                }
            ]
        )
        self.harvester(FakeClient(aggregated_payload=payload)).harvest(self.con)
        self.assertIsNone(self.per_model()[0][5])

    def test_a_second_harvest_of_the_same_cycle_writes_nothing(self):
        harvester = self.harvester(FakeClient())
        self.assertEqual(harvester.harvest(self.con).per_model, 4)
        self.assertEqual(harvester.harvest(self.con).per_model, 0)

    def test_a_first_run_also_asks_for_the_previous_cycle(self):
        # The current cycle is often empty right after it opens; the window
        # before it is the previous cycle when cycles are equal length.
        client = FakeClient()
        self.harvester(client).harvest(self.con)
        ranges = [call for call in client.call_args if call[0] == AGGREGATED_PATH]
        self.assertEqual(len(ranges), 2)
        self.assertLess(ranges[1][1]["endDate"], ranges[0][1]["startDate"] + 1)

    def test_a_second_run_does_not_re_ask_for_history(self):
        client = FakeClient()
        harvester = self.harvester(client)
        harvester.harvest(self.con)
        client.call_args.clear()
        harvester.harvest(self.con)
        # No second window this time: history is asked for once, not every run.
        aggregations = [c for c in client.call_args if c[0] == AGGREGATED_PATH]
        self.assertEqual(len(aggregations), 1)

    def test_full_asks_for_history_again(self):
        client = FakeClient()
        harvester = self.harvester(client)
        harvester.harvest(self.con)
        client.call_args.clear()
        harvester.harvest(self.con, full=True)
        self.assertEqual(len([c for c in client.call_args if c[0] == AGGREGATED_PATH]), 2)


class CrossCheckTest(CursorCase):
    def test_the_cost_unit_relationship_is_recorded_every_run(self):
        self.harvester(FakeClient()).harvest(self.con)
        kinds = [row[0] for row in self.checks()]
        self.assertIn("cost_unit", kinds)

    def test_an_implausible_sum_against_the_plan_is_flagged(self):
        # A plan limit of 2000 with 0% used while the rows sum far above it: the
        # two figures cannot be the same unit, and that must be visible.
        client = FakeClient(
            aggregated_payload=cents(5000.0),
            period_payload=period(limit=2000, percent=0),
        )
        self.harvester(client).harvest(self.con)
        flagged = [row for row in self.checks() if row[0] == "cost_unit"]
        self.assertEqual(flagged[0][2], 0)

    def test_the_previous_cycle_is_not_summed_into_this_one(self):
        # A first harvest asks for the window before this cycle too. Those rows
        # are history: folding them into the comparison against this cycle's
        # total is what produced a ~30x "unit" mismatch that did not exist.
        client = FakeClient(
            aggregated_payload=cents(100.0),
            earlier_payload=cents(4000.0),
            period_payload=period(limit=2000, percent=0),
        )
        self.harvester(client).harvest(self.con)
        flagged = [row for row in self.checks() if row[0] == "cost_unit"]
        self.assertEqual(flagged[0][2], 1)
        # The detail has to name this cycle's sum, not the history's.
        self.assertIn("rows sum to 100.00 cents", flagged[0][1])
        # ...while both cycles are still written to the ledger.
        self.assertEqual(len(self.per_model()), 2)

    def test_a_plan_left_untouched_does_not_flag_a_small_sum(self):
        payload = aggregated(
            [
                {
                    "modelIntent": "default",
                    "inputTokens": "1",
                    "outputTokens": "1",
                    "cacheReadTokens": "0",
                    "totalCents": 10.0,
                    "tier": 1,
                }
            ]
        )
        client = FakeClient(aggregated_payload=payload, period_payload=period(limit=2000))
        self.harvester(client).harvest(self.con)
        flagged = [row for row in self.checks() if row[0] == "cost_unit"]
        self.assertEqual(flagged[0][2], 1)

    def test_the_slow_pool_probe_records_what_the_endpoint_really_returns(self):
        client = FakeClient(
            policy_payload={
                "canConfigureSpendLimit": True,
                "creditRequestButtonHidden": False,
            }
        )
        self.harvester(client).harvest(self.con)
        probes = [row for row in self.checks() if row[0] == "slow_pool_probe"]
        self.assertEqual(len(probes), 1)
        self.assertIn("no slow-pool flag", probes[0][1])
        self.assertEqual(json.loads(json.dumps(probes[0][1])), probes[0][1])


class FailureTest(CursorCase):
    def test_not_being_signed_in_is_a_note(self):
        with mock.patch(
            "tokens_go_brrr.harvesters.dashboard_usage.read_local_auth",
            return_value=None,
        ):
            result = CursorApiHarvester(client=FakeClient()).harvest(self.con)
        self.assertFalse(result.failed)
        self.assertEqual(result.note, "not signed in")

    def test_a_failed_aggregation_is_reported_not_raised(self):
        client = FakeClient(fail_path=AGGREGATED_PATH)
        result = self.harvester(client).harvest(self.con)
        self.assertTrue(result.failed)
        self.assertIn("aggregation unavailable", result.note)

    def test_a_missing_billing_cycle_is_reported(self):
        client = FakeClient(period_payload={"planUsage": {}})
        result = self.harvester(client).harvest(self.con)
        self.assertTrue(result.failed)
        self.assertIn("no billing cycle", result.note)

    def test_an_empty_aggregation_is_an_answer_not_a_failure(self):
        client = FakeClient(aggregated_payload={"aggregations": []})
        result = self.harvester(client).harvest(self.con)
        self.assertFalse(result.failed)
        self.assertEqual(result.per_model, 0)
        self.assertIn("no per-model rows", result.note)

    def test_a_policy_refusal_does_not_fail_the_harvest(self):
        client = FakeClient(fail_path=POLICY_PATH)
        result = self.harvester(client).harvest(self.con)
        self.assertFalse(result.failed)
        self.assertEqual(result.per_model, 4)


if __name__ == "__main__":
    unittest.main()
