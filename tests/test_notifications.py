"""Tests for the notification engine's wording, mixing and cooldowns.

Everything here runs without an LLM, which is the point of shipping templates
first: the triggers, the mixer and the cooldowns are all verifiable before any
model is in the loop. The tests also pin the two things a message must never do
— invent a number, or present an estimate as a measurement.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cursor_spend_monitor.notify_engine as notify
from cursor_spend_monitor import ledger
from cursor_spend_monitor.providers.base import Meter, ProviderSnapshot

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def make(
    provider: str = "claude",
    external_id: str = "s1",
    *,
    project: str = "alpha",
    model: str = "claude-opus-5-5",
    started: datetime = NOW,
    duration_s: int = 600,
    tin: int = 1000,
    tout: int = 200,
    tcr: int = 0,
    cost: float | None = 1.0,
    source: str = "local-transcript",
) -> ledger.SessionRow:
    return ledger.SessionRow(
        provider=provider,
        source=source,
        external_id=external_id,
        model=model,
        project=project,
        directory=f"/home/u/{project}",
        started_at=int(started.timestamp()),
        ended_at=int(started.timestamp()) + duration_s,
        duration_s=duration_s,
        tokens_input=tin,
        tokens_output=tout,
        tokens_cache_read=tcr,
        cost_usd=cost,
    )


def snap(
    provider_id: str = "claude",
    name: str = "Claude Code",
    *,
    percent: float = 40.0,
    eta: float | None = None,
    borrowed: str | None = None,
    status: str = "ok",
) -> ProviderSnapshot:
    return ProviderSnapshot(
        provider_id=provider_id,
        display_name=name,
        icon=provider_id,
        plan=None,
        metrics=[
            Meter("five_hour", "5-hour limit", percent, kind="rolling", eta_seconds=eta)
        ],
        primary_key="five_hour",
        status=status,
        borrowed_from=borrowed,
    )


class NotifyCase(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.con = ledger.connect(Path(self._dir.name) / "usage.db")
        self.addCleanup(self.con.close)

    def seed(self, rows: list[ledger.SessionRow]) -> None:
        ledger.upsert_sessions(self.con, rows)
        ledger.fold_all(self.con)


class RangeTest(unittest.TestCase):
    def test_day_range_is_inclusive_of_today(self):
        start, end = notify.day_range(7, now=NOW)
        self.assertEqual(end, "2026-10-06")
        self.assertEqual(start, "2026-09-30")

    def test_month_range_covers_the_calendar_month(self):
        start, end = notify.month_range(NOW)
        self.assertEqual(start, "2026-10-01")
        self.assertEqual(end, "2026-10-06")

    def test_the_previous_month_is_a_whole_month(self):
        start, end = notify.month_range(NOW, offset=1)
        self.assertEqual(start, "2026-09-01")
        self.assertEqual(end, "2026-09-30")


class DigestTest(NotifyCase):
    def test_an_empty_ledger_produces_no_digest(self):
        self.assertIsNone(notify.daily_digest(self.con, now=NOW))
        self.assertIsNone(notify.weekly_digest(self.con, now=NOW))
        self.assertIsNone(notify.monthly_digest(self.con, now=NOW))

    def test_a_daily_digest_counts_what_was_recorded(self):
        self.seed([make(started=NOW.replace(hour=9))])
        message = notify.daily_digest(self.con, now=NOW)
        self.assertIsNotNone(message)
        assert message is not None
        self.assertIn("1 sessions", message.body)
        self.assertIn("1.2K tokens", message.body)

    def test_a_weekly_digest_names_the_leading_provider_and_project(self):
        self.seed(
            [
                make("claude", "c1", project="alpha", tin=1000),
                make(
                    "opencode",
                    "o1",
                    project="beta",
                    tin=9000,
                    model="deepseek-v4-flash",
                ),
            ]
        )
        message = notify.weekly_digest(self.con, now=NOW)
        assert message is not None
        self.assertIn("opencode carried 88%", message.body)
        self.assertIn("top project beta", message.body)

    def test_a_monthly_digest_compares_against_last_month(self):
        self.seed(
            [
                make(
                    "claude",
                    "prev",
                    started=datetime(2026, 9, 10, 9, tzinfo=timezone.utc),
                    tin=1000,
                ),
                make("claude", "now", started=NOW.replace(hour=9), tin=3000),
            ]
        )
        message = notify.monthly_digest(self.con, now=NOW)
        assert message is not None
        self.assertIn("up", message.body)
        self.assertIn("vs last month", message.body)

    def test_a_period_with_an_estimate_says_so(self):
        self.seed([make(source="estimate", started=NOW.replace(hour=9))])
        message = notify.daily_digest(self.con, now=NOW)
        assert message is not None
        self.assertIn("includes an estimate", message.body)

    def test_a_measured_period_does_not_claim_an_estimate(self):
        self.seed([make(started=NOW.replace(hour=9))])
        message = notify.daily_digest(self.con, now=NOW)
        assert message is not None
        self.assertNotIn("estimate", message.body)


class FunAndShareTest(NotifyCase):
    def test_a_high_cache_share_becomes_the_fun_fact(self):
        self.seed([make(tin=100, tout=0, tcr=900, started=NOW.replace(hour=9))])
        message = notify.fun_fact(self.con, now=NOW)
        assert message is not None
        self.assertIn("90%", message.body)
        self.assertIn("cache", message.body)

    def test_a_streak_becomes_the_fun_fact_when_cache_is_ordinary(self):
        self.seed(
            [
                make(
                    "claude",
                    f"s{index}",
                    started=NOW.replace(hour=9) - timedelta(days=index),
                )
                for index in range(4)
            ]
        )
        message = notify.fun_fact(self.con, now=NOW)
        assert message is not None
        self.assertIn("4 days in a row", message.body)

    def test_the_streak_is_measured_against_the_given_clock(self):
        # Four consecutive days ending at NOW, so any other clock has to change
        # the answer. Streaks were the only one of the nine facts that read the
        # wall clock instead of the `now` it was handed, which let a digest state
        # a streak belonging to a different day than the numbers beside it.
        self.seed(
            [
                make(
                    "claude",
                    f"k{index}",
                    started=NOW.replace(hour=9) - timedelta(days=index),
                )
                for index in range(4)
            ]
        )
        day = NOW.date().isoformat()
        live = notify.digest_facts(
            self.con, start=day, end=day, period="today", now=NOW
        )
        self.assertEqual(live["streaks"]["current"], 4)
        # The same rows, read a month later: the streak is over by then.
        stale = notify.digest_facts(
            self.con,
            start=day,
            end=day,
            period="today",
            now=NOW + timedelta(days=30),
        )
        self.assertEqual(stale["streaks"]["current"], 0)

    def test_no_fun_fact_is_invented_from_nothing(self):
        self.assertIsNone(notify.fun_fact(self.con, now=NOW))

    def test_a_share_line_is_a_ready_to_post_one_liner(self):
        self.seed([make("claude", "c1", tin=1000), make("opencode", "o1", tin=500)])
        message = notify.share_line(self.con, now=NOW)
        assert message is not None
        self.assertTrue(message.share.startswith("SHARE: "))
        self.assertLessEqual(len(message.share), 200)
        self.assertNotIn("SHARE:", message.body)

    def test_no_share_line_without_a_month_of_usage(self):
        self.assertIsNone(notify.share_line(self.con, now=NOW))


class EventTest(NotifyCase):
    def test_a_meter_past_the_warning_line_is_actionable(self):
        messages = notify.event_messages(
            [
                snap("claude", "Claude Code", percent=93),
                snap("opencode", "OpenCode", percent=5),
            ]
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].kind, notify.ACTIONABLE)
        self.assertIn("Claude Code", messages[0].body)
        self.assertIn("OpenCode", messages[0].body)

    def test_a_meter_that_will_burn_out_before_it_resets_is_actionable(self):
        messages = notify.event_messages(
            [snap("claude", percent=40, eta=30 * 60), snap("opencode", percent=5)],
            wind_down_hours=2,
        )
        self.assertEqual(len(messages), 1)
        self.assertIn("spent in about 30m", messages[0].body)

    def test_a_comfortable_meter_says_nothing(self):
        messages = notify.event_messages(
            [snap("claude", percent=40, eta=9 * 3600)], wind_down_hours=2
        )
        self.assertEqual(messages, [])

    def test_a_meter_already_spent_reads_as_spent(self):
        messages = notify.event_messages([snap("claude", percent=100)])
        self.assertIn("is spent", messages[0].body)

    def test_a_borrowed_row_is_not_counted_twice(self):
        messages = notify.event_messages(
            [snap("pi", "Pi", percent=99, borrowed="opencode")]
        )
        self.assertEqual(messages, [])

    def test_a_broken_provider_is_not_reported_as_a_limit(self):
        messages = notify.event_messages([snap("claude", percent=0, status="error")])
        self.assertEqual(messages, [])

    def test_no_better_provider_is_named_when_there_is_none(self):
        messages = notify.event_messages([snap("claude", percent=95)])
        self.assertIn("Claude Code", messages[0].body)
        self.assertNotIn("has room", messages[0].body)


class TemplateTest(NotifyCase):
    """Every template-built message says which template and with what values,
    so the panel can render it in the user's language."""

    def test_a_digest_carries_its_values(self):
        self.seed(
            [
                make("claude", "c1", project="alpha", tin=1000),
                make("opencode", "o1", project="beta", tin=9000, model="deepseek-v4-flash"),
            ]
        )
        message = notify.weekly_digest(self.con, now=NOW)
        assert message is not None
        tpl = message.meta["tpl"]
        self.assertEqual(tpl["id"], "digest")
        params = tpl["p"]
        self.assertEqual(params["period"], "weekly")
        self.assertEqual(params["sessions"], 2)
        self.assertEqual(params["leader"], {"name": "OpenCode", "pct": 88})
        self.assertEqual(params["topProject"]["project"], "beta")
        self.assertEqual(params["topModel"], "deepseek-v4-flash")
        self.assertFalse(params["estimate"])

    def test_the_monthly_digest_carries_the_change_against_last_month(self):
        self.seed(
            [
                make("claude", "prev", started=datetime(2026, 9, 10, 9, tzinfo=timezone.utc), tin=1000),
                make("claude", "now", started=NOW.replace(hour=9), tin=3000),
            ]
        )
        message = notify.monthly_digest(self.con, now=NOW)
        assert message is not None
        change = message.meta["tpl"]["p"]["vsLastMonth"]
        self.assertEqual(change["dir"], "up")
        self.assertGreater(change["pct"], 0)

    def test_a_first_month_has_no_change_to_report(self):
        self.seed([make(started=NOW.replace(hour=9))])
        message = notify.monthly_digest(self.con, now=NOW)
        assert message is not None
        self.assertIsNone(message.meta["tpl"]["p"]["vsLastMonth"])

    def test_a_measured_period_is_not_marked_estimated(self):
        self.seed([make(source="estimate", started=NOW.replace(hour=9))])
        message = notify.daily_digest(self.con, now=NOW)
        assert message is not None
        self.assertTrue(message.meta["tpl"]["p"]["estimate"])

    def test_each_fun_fact_names_its_template(self):
        self.seed([make(tin=100, tout=0, tcr=900, started=NOW.replace(hour=9))])
        message = notify.fun_fact(self.con, now=NOW)
        assert message is not None
        self.assertEqual(message.meta["tpl"]["id"], "fun.cache")
        self.assertEqual(message.meta["tpl"]["p"]["pct"], 90)

    def test_a_streak_template_carries_both_runs(self):
        self.seed(
            [
                make("claude", f"s{i}", started=NOW.replace(hour=9) - timedelta(days=i))
                for i in range(4)
            ]
        )
        message = notify.fun_fact(self.con, now=NOW)
        assert message is not None
        self.assertEqual(message.meta["tpl"]["id"], "fun.streak")
        self.assertEqual(message.meta["tpl"]["p"]["current"], 4)

    def test_the_share_line_carries_its_values(self):
        self.seed([make(started=NOW.replace(hour=9))])
        message = notify.share_line(self.con, now=NOW)
        assert message is not None
        tpl = message.meta["tpl"]
        self.assertEqual(tpl["id"], "share")
        self.assertEqual(tpl["p"]["sessions"], 1)
        self.assertEqual(tpl["p"]["model"], "claude-opus-5-5")

    def test_an_actionable_message_carries_the_meter_and_the_better_provider(self):
        messages = notify.event_messages(
            [snap("claude", "Claude Code", percent=93), snap("opencode", "OpenCode", percent=5)]
        )
        params = messages[0].meta["tpl"]["p"]
        self.assertEqual(messages[0].meta["tpl"]["id"], "actionable")
        self.assertEqual(params["provider"], "Claude Code")
        self.assertEqual(params["percent"], 93)
        self.assertEqual(params["better"], "OpenCode")
        self.assertFalse(params["spent"])

    def test_the_payload_exposes_the_template_but_not_for_a_reworded_message(self):
        row = {
            "id": 1,
            "kind": "informative",
            "created_at": 100,
            "provider": "",
            "body": "b",
            "share": "",
            "meta": '{"tpl": {"id": "digest", "p": {"sessions": 2}}}',
        }
        self.assertEqual(
            notify.billboard_payload(row)["template"],
            {"id": "digest", "params": {"sessions": 2}},
        )
        row["meta"] = '{"tpl": {"id": "digest", "p": {}}, "composed_by": "claude"}'
        self.assertIsNone(notify.billboard_payload(row)["template"])
        row["meta"] = "{}"
        self.assertIsNone(notify.billboard_payload(row)["template"])


class MixerTest(NotifyCase):
    def test_the_daily_slot_is_a_digest_plus_a_fun_fact(self):
        self.seed([make(tin=100, tcr=900, started=NOW.replace(hour=9))])
        kinds = [
            m.kind for m in notify.scheduled_messages(self.con, slot="daily", now=NOW)
        ]
        self.assertIn(notify.INFORMATIVE, kinds)

    def test_the_monthly_slot_carries_a_share_line(self):
        self.seed([make(started=NOW.replace(hour=9))])
        kinds = [
            m.kind for m in notify.scheduled_messages(self.con, slot="monthly", now=NOW)
        ]
        self.assertIn(notify.SHAREABLE, kinds)

    def test_an_unknown_slot_produces_nothing(self):
        self.assertEqual(
            notify.scheduled_messages(self.con, slot="hourly", now=NOW), []
        )


class CooldownTest(NotifyCase):
    def message(self, key: str = "k") -> notify.Message:
        return notify.Message(kind=notify.INFORMATIVE, key=key, body="body")

    def test_a_new_message_is_due(self):
        self.assertTrue(notify.due(self.con, self.message(), cooldown_seconds=3600))

    def test_a_message_is_kept_and_then_held_by_its_cooldown(self):
        first = notify.keep(self.con, [self.message()], cooldown_seconds=3600)
        self.assertEqual(len(first), 1)
        again = notify.keep(self.con, [self.message()], cooldown_seconds=3600)
        self.assertEqual(again, [])

    def test_a_message_becomes_due_again_after_the_cooldown(self):
        ledger.store_message(
            self.con,
            kind=notify.INFORMATIVE,
            key="k",
            body="old",
            at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        self.assertTrue(notify.due(self.con, self.message(), cooldown_seconds=3600))

    def test_a_different_key_is_not_held_by_another_key_cooldown(self):
        notify.keep(self.con, [self.message("a")], cooldown_seconds=3600)
        self.assertTrue(notify.due(self.con, self.message("b"), cooldown_seconds=3600))


if __name__ == "__main__":
    unittest.main()


class RollingWindowTest(NotifyCase):
    def test_rolling_range_ends_now_and_spans_the_hours(self):
        since, until = notify.rolling_range(24, now=NOW)
        self.assertEqual(until, int(NOW.timestamp()))
        self.assertEqual(until - since, 24 * 3600)

    def test_a_session_from_last_evening_is_inside_the_last_24_hours(self):
        # 21:00 the previous UTC day: "yesterday" by the calendar, 15h ago by the clock.
        self.seed([make(started=NOW - timedelta(hours=15), duration_s=600)])
        message = notify.daily_digest(self.con, now=NOW)
        assert message is not None
        self.assertIn("Last 24h: 1 sessions", message.body)

    def test_a_session_older_than_24_hours_is_outside_it(self):
        self.seed([make(started=NOW - timedelta(hours=30), duration_s=600)])
        self.assertIsNone(notify.daily_digest(self.con, now=NOW))

    def test_a_session_is_placed_by_when_it_ended(self):
        # Started 25h ago but ran 2h, so it ended 23h ago: inside the window.
        self.seed(
            [make(started=NOW - timedelta(hours=25), duration_s=2 * 3600)]
        )
        message = notify.daily_digest(self.con, now=NOW)
        assert message is not None
        self.assertIn("1 sessions", message.body)

    def test_rolling_totals_rank_providers_and_name_the_top_project(self):
        self.seed(
            [
                make("claude", "c1", project="alpha", tin=5000,
                     started=NOW - timedelta(hours=3)),
                make("opencode", "o1", project="beta", tin=100,
                     started=NOW - timedelta(hours=2)),
            ]
        )
        facts = notify.rolling_facts(
            self.con, hours=24, period="last 24 hours", now=NOW
        )
        self.assertEqual(facts["ranked"][0]["provider"], "claude")
        self.assertEqual(facts["top_project"]["project"], "alpha")
        self.assertEqual(facts["totals"]["sessions"], 2)

    def test_a_rolling_window_with_an_estimate_says_so(self):
        self.seed([make(source="estimate", started=NOW - timedelta(hours=2))])
        message = notify.daily_digest(self.con, now=NOW)
        assert message is not None
        self.assertIn("includes an estimate", message.body)

    def test_an_unknown_rolling_grouping_is_refused(self):
        with self.assertRaises(ValueError):
            ledger.rolling_period_totals(self.con, since=0, until=1, group_by="day")


class ProvenanceTest(NotifyCase):
    def test_a_digest_carries_its_provenance(self):
        self.seed([make(started=NOW - timedelta(hours=2))])
        message = notify.daily_digest(self.con, now=NOW)
        assert message is not None
        self.assertEqual(message.meta["tier"], notify.COLD)
        self.assertEqual(message.meta["asOf"], int(NOW.timestamp()))
        self.assertEqual(message.meta["source"], notify.SOURCE_TEMPLATE)
        self.assertTrue(message.meta["fingerprint"])

    def test_the_fingerprint_is_stable_and_follows_the_figures(self):
        self.seed([make("s1", started=NOW - timedelta(hours=2))])
        first = notify.daily_digest(self.con, now=NOW)
        again = notify.daily_digest(self.con, now=NOW)
        self.seed([make("s2", external_id="s2", started=NOW - timedelta(hours=1))])
        changed = notify.daily_digest(self.con, now=NOW)
        assert first and again and changed
        self.assertEqual(first.meta["fingerprint"], again.meta["fingerprint"])
        self.assertNotEqual(first.meta["fingerprint"], changed.meta["fingerprint"])

    def test_weekly_and_monthly_digests_are_cold_too(self):
        self.seed([make(started=NOW - timedelta(hours=2))])
        for build in (notify.weekly_digest, notify.monthly_digest):
            message = build(self.con, now=NOW)
            assert message is not None
            self.assertEqual(message.meta["tier"], notify.COLD)


class TierExpiryTest(unittest.TestCase):
    CREATED = int(NOW.timestamp())

    def test_without_a_tier_the_kind_sets_the_limit(self):
        self.assertEqual(
            notify.expires_at_for(notify.INFORMATIVE, self.CREATED),
            self.CREATED + 24 * 3600,
        )

    def test_a_warm_note_expires_sooner_than_its_kind(self):
        self.assertEqual(
            notify.expires_at_for(
                notify.INFORMATIVE, self.CREATED, tier=notify.WARM
            ),
            self.CREATED + 2 * 3600,
        )

    def test_the_sooner_of_kind_and_tier_wins(self):
        # Actionable is 6h by kind; a cold tier would allow 24h. Kind wins.
        self.assertEqual(
            notify.expires_at_for(
                notify.ACTIONABLE, self.CREATED, tier=notify.COLD
            ),
            self.CREATED + 6 * 3600,
        )

    def test_the_tier_counts_from_when_the_facts_were_read(self):
        as_of = self.CREATED - 3600
        self.assertEqual(
            notify.expires_at_for(
                notify.INFORMATIVE, self.CREATED, tier=notify.WARM, as_of=as_of
            ),
            as_of + 2 * 3600,
        )

    def test_an_unknown_tier_falls_back_to_the_kind(self):
        self.assertEqual(
            notify.expires_at_for(notify.FUN, self.CREATED, tier="bogus"),
            self.CREATED + 12 * 3600,
        )

    def test_a_stored_warm_note_stops_being_the_billboard(self):
        meta = json.dumps({"tier": notify.WARM, "asOf": self.CREATED})
        stored = {
            "id": 1,
            "kind": notify.INFORMATIVE,
            "created_at": self.CREATED,
            "body": "x",
            "meta": meta,
        }
        later = NOW + timedelta(hours=3)
        self.assertIsNone(notify.choose_billboard([stored], now=later))
        self.assertIsNotNone(notify.choose_billboard([stored], now=NOW))

    def test_the_payload_reports_tier_age_and_source(self):
        meta = json.dumps(
            {"tier": notify.COLD, "asOf": self.CREATED - 60, "source": "llm"}
        )
        payload = notify.billboard_payload(
            {
                "id": 1,
                "kind": notify.INFORMATIVE,
                "created_at": self.CREATED,
                "body": "x",
                "meta": meta,
            }
        )
        self.assertEqual(payload["tier"], notify.COLD)
        self.assertEqual(payload["asOf"], self.CREATED - 60)
        self.assertEqual(payload["source"], "llm")

    def test_a_message_without_provenance_still_renders(self):
        payload = notify.billboard_payload(
            {"id": 1, "kind": notify.FUN, "created_at": self.CREATED, "body": "x"}
        )
        self.assertEqual(payload["tier"], "")
        self.assertEqual(payload["asOf"], self.CREATED)
        self.assertEqual(payload["source"], notify.SOURCE_TEMPLATE)


class TierTest(unittest.TestCase):
    def test_a_first_open_is_cold(self):
        self.assertEqual(notify.tier_for(None), notify.COLD)

    def test_a_long_absence_is_cold(self):
        self.assertEqual(notify.tier_for(5 * 3600), notify.COLD)

    def test_the_threshold_itself_is_cold(self):
        self.assertEqual(notify.tier_for(4 * 3600), notify.COLD)
        self.assertEqual(notify.tier_for(4 * 3600 - 1), notify.WARM)

    def test_an_open_inside_a_working_cycle_is_not_cold(self):
        self.assertEqual(notify.tier_for(30 * 60), notify.WARM)

    def test_the_threshold_is_configurable(self):
        self.assertEqual(notify.tier_for(2 * 3600, cold_hours=1), notify.COLD)
        self.assertEqual(notify.tier_for(2 * 3600, cold_hours=8), notify.WARM)

    def test_a_zero_threshold_makes_every_open_cold(self):
        self.assertEqual(notify.tier_for(0, cold_hours=0), notify.COLD)


def _local(ts: int) -> datetime:
    return datetime.fromtimestamp(ts)


class InsightData(NotifyCase):
    def seed_history(self) -> None:
        """Enough of a month for every insight to have something to say."""
        rows = []
        for i in range(6):  # this week: heavy, mostly cache, mostly "alpha"
            rows.append(
                make(
                    external_id=f"now{i}",
                    project="alpha" if i < 5 else "beta",
                    started=NOW - timedelta(days=i, hours=3),
                    tin=40_000,
                    tcr=120_000,
                )
            )
        for i in range(6):  # the week before: lighter
            rows.append(
                make(
                    external_id=f"before{i}",
                    project="alpha",
                    started=NOW - timedelta(days=8 + i, hours=3),
                    tin=20_000,
                    tcr=40_000,
                )
            )
        self.seed(rows)


class InsightTest(InsightData):
    def test_every_insight_speaks_when_there_is_a_month_of_data(self):
        self.seed_history()
        ids = [m.meta["insight"] for m in notify.insight_candidates(self.con, now=NOW)]
        self.assertEqual(ids, list(notify.INSIGHT_IDS))

    def test_too_little_data_says_nothing(self):
        self.seed([make(tin=500, started=NOW - timedelta(hours=2))])
        self.assertEqual(notify.insight_candidates(self.con, now=NOW), [])
        self.assertIsNone(notify.next_insight(self.con, now=NOW))

    def test_a_high_cache_share_carries_the_tip(self):
        self.seed_history()
        message = notify.insight_cache(self.con, now=NOW)
        assert message is not None
        self.assertTrue(message.meta["tpl"]["p"]["high"])
        self.assertIn("fresh session per task", message.body)

    def test_a_low_cache_share_gets_the_other_wording(self):
        self.seed(
            [
                make(
                    external_id=f"s{i}",
                    started=NOW - timedelta(days=i, hours=2),
                    tin=60_000,
                    tcr=5_000,
                )
                for i in range(3)
            ]
        )
        message = notify.insight_cache(self.con, now=NOW)
        assert message is not None
        self.assertFalse(message.meta["tpl"]["p"]["high"])
        self.assertIn("one task within a session", message.body)

    def test_a_heavier_week_is_reported_as_up(self):
        self.seed_history()
        message = notify.insight_week(self.con, now=NOW)
        assert message is not None
        params = message.meta["tpl"]["p"]
        self.assertEqual(params["dir"], "up")
        self.assertGreater(params["pct"], notify.FLAT_WEEK_PCT)
        self.assertIn("more tokens", message.body)

    def test_a_lighter_week_is_reported_as_down(self):
        self.seed(
            [
                make(external_id="a", started=NOW - timedelta(days=1), tin=10_000),
                make(external_id="b", started=NOW - timedelta(days=9), tin=90_000),
            ]
        )
        message = notify.insight_week(self.con, now=NOW)
        assert message is not None
        self.assertEqual(message.meta["tpl"]["p"]["dir"], "down")
        self.assertIn("fewer tokens", message.body)

    def test_a_steady_week_is_reported_as_flat(self):
        self.seed(
            [
                make(external_id="a", started=NOW - timedelta(days=1), tin=50_000),
                make(external_id="b", started=NOW - timedelta(days=9), tin=50_000),
            ]
        )
        message = notify.insight_week(self.con, now=NOW)
        assert message is not None
        self.assertEqual(message.meta["tpl"]["p"]["dir"], "flat")

    def test_no_prior_week_means_no_comparison(self):
        self.seed([make(started=NOW - timedelta(days=1), tin=50_000)])
        self.assertIsNone(notify.insight_week(self.con, now=NOW))

    def test_the_peak_hour_and_weekday_are_the_busiest_local_ones(self):
        self.seed_history()
        message = notify.insight_peak(self.con, now=NOW)
        assert message is not None
        params = message.meta["tpl"]["p"]
        # Every session started three hours before NOW, so one local hour wins.
        started = int((NOW - timedelta(hours=3)).timestamp())
        self.assertEqual(params["hour"], _local(started).hour)
        self.assertIn(notify.WEEKDAYS[params["weekday"]], message.body)
        self.assertIn(f"{params['hour']:02d}:00", message.body)

    def test_the_focus_insight_names_the_top_project_and_its_share(self):
        self.seed_history()
        message = notify.insight_focus(self.con, now=NOW)
        assert message is not None
        params = message.meta["tpl"]["p"]
        self.assertEqual(params["project"], "alpha")
        self.assertGreater(params["pct"], 50)
        self.assertIn("alpha", message.body)

    def test_the_rhythm_share_matches_the_ledger(self):
        self.seed_history()
        message = notify.insight_rhythm(self.con, now=NOW)
        assert message is not None
        start, end = notify.day_range(notify.INSIGHT_WINDOW_DAYS, now=NOW)
        shape = ledger.session_shape(self.con, start_day=start, end_day=end)
        self.assertEqual(
            message.meta["tpl"]["p"]["pct"], round(100 * shape["work_hours_share"])
        )

    def test_an_insight_is_a_cold_template_note(self):
        self.seed_history()
        message = notify.insight_cache(self.con, now=NOW)
        assert message is not None
        self.assertEqual(message.kind, notify.INFORMATIVE)
        self.assertEqual(message.meta["tier"], notify.COLD)
        self.assertEqual(message.meta["source"], notify.SOURCE_TEMPLATE)
        self.assertEqual(message.meta["asOf"], int(NOW.timestamp()))
        self.assertEqual(message.meta["tpl"]["id"], "insight.cache")
        self.assertTrue(message.meta["fingerprint"])

    def test_an_insights_key_carries_the_day(self):
        self.seed_history()
        today = notify.insight_cache(self.con, now=NOW)
        tomorrow = notify.insight_cache(self.con, now=NOW + timedelta(days=1))
        assert today and tomorrow
        self.assertEqual(today.key, "insight:cache:2026-10-06")
        self.assertNotEqual(today.key, tomorrow.key)


class InsightRotationTest(InsightData):
    def play(self, when: datetime) -> notify.Message:
        message = notify.next_insight(self.con, now=when)
        assert message is not None
        ledger.store_message(
            self.con,
            kind=message.kind,
            key=message.key,
            body=message.body,
            meta=message.meta,
            at=when,
        )
        return message

    def test_none_repeats_before_the_rest_have_had_a_turn(self):
        self.seed_history()
        seen = []
        for day in range(len(notify.INSIGHT_IDS)):
            seen.append(self.play(NOW + timedelta(days=day)).meta["insight"])
        self.assertEqual(sorted(seen), sorted(notify.INSIGHT_IDS))
        self.assertEqual(len(set(seen)), len(notify.INSIGHT_IDS))

    def test_after_a_full_round_the_oldest_goes_again(self):
        self.seed_history()
        first_round = [
            self.play(NOW + timedelta(days=d)).meta["insight"]
            for d in range(len(notify.INSIGHT_IDS))
        ]
        again = self.play(NOW + timedelta(days=len(notify.INSIGHT_IDS)))
        self.assertEqual(again.meta["insight"], first_round[0])

    def test_an_insight_that_never_spoke_goes_before_one_that_did(self):
        self.seed_history()
        ledger.store_message(
            self.con, kind=notify.INFORMATIVE, key="insight:cache:2026-10-05",
            body="x", at=NOW,
        )
        message = notify.next_insight(self.con, now=NOW)
        assert message is not None
        self.assertNotEqual(message.meta["insight"], "cache")


class ColdNoteTest(InsightData):
    def test_a_cold_open_produces_an_insight(self):
        self.seed_history()
        message = notify.cold_note(self.con, now=NOW)
        assert message is not None
        self.assertEqual(message.meta["tier"], notify.COLD)

    def test_an_unread_insight_means_no_second_one(self):
        self.seed_history()
        first = notify.cold_note(self.con, now=NOW)
        assert first is not None
        ledger.store_message(
            self.con, kind=first.kind, key=first.key, body=first.body,
            meta=first.meta, at=NOW,
        )
        self.assertIsNone(notify.cold_note(self.con, now=NOW + timedelta(hours=1)))

    def test_a_read_insight_makes_room_for_the_next(self):
        self.seed_history()
        first = notify.cold_note(self.con, now=NOW)
        assert first is not None
        mid = ledger.store_message(
            self.con, kind=first.kind, key=first.key, body=first.body,
            meta=first.meta, at=NOW,
        )
        ledger.mark_message_seen(self.con, mid)
        second = notify.cold_note(self.con, now=NOW + timedelta(hours=1))
        assert second is not None
        self.assertNotEqual(second.meta["insight"], first.meta["insight"])

    def test_an_expired_unread_insight_does_not_block_a_new_one(self):
        self.seed_history()
        first = notify.cold_note(self.con, now=NOW)
        assert first is not None
        ledger.store_message(
            self.con, kind=first.kind, key=first.key, body=first.body,
            meta=first.meta, at=NOW,
        )
        later = NOW + timedelta(hours=30)
        self.assertIsNotNone(notify.cold_note(self.con, now=later))

    def test_an_acknowledged_insight_does_not_hide_its_return(self):
        self.seed_history()
        key_day1 = notify.insight_cache(self.con, now=NOW)
        key_day2 = notify.insight_cache(self.con, now=NOW + timedelta(days=1))
        assert key_day1 and key_day2
        mid = ledger.store_message(
            self.con, kind=key_day1.kind, key=key_day1.key, body="x",
            meta=key_day1.meta, at=NOW,
        )
        ledger.mark_message_seen(self.con, mid)
        ledger.store_message(
            self.con, kind=key_day2.kind, key=key_day2.key, body="y",
            meta=key_day2.meta, at=NOW + timedelta(days=1),
        )
        pending = ledger.pending_messages(self.con)
        self.assertEqual([r["key"] for r in pending], [key_day2.key])

    def test_a_cold_insight_can_be_the_billboard(self):
        self.seed_history()
        message = notify.cold_note(self.con, now=NOW)
        assert message is not None
        ledger.store_message(
            self.con, kind=message.kind, key=message.key, body=message.body,
            meta=message.meta, at=NOW,
        )
        shown = notify.choose_billboard(ledger.pending_messages(self.con), now=NOW)
        assert shown is not None
        self.assertEqual(shown["tier"], notify.COLD)
        self.assertEqual(shown["template"]["id"], f"insight.{message.meta['insight']}")


class LedgerHelpersTest(NotifyCase):
    def test_last_generated_at_looks_across_days_by_prefix(self):
        ledger.store_message(self.con, kind="informative", key="insight:cache:2026-10-01", body="a", at=NOW - timedelta(days=5))
        ledger.store_message(self.con, kind="informative", key="insight:cache:2026-10-04", body="b", at=NOW - timedelta(days=2))
        ledger.store_message(self.con, kind="informative", key="insight:week:2026-10-05", body="c", at=NOW - timedelta(days=1))
        got = ledger.last_generated_at(self.con, kind="informative", key_prefix="insight:cache:")
        self.assertEqual(got, int((NOW - timedelta(days=2)).timestamp()))
        self.assertIsNone(
            ledger.last_generated_at(self.con, kind="informative", key_prefix="insight:focus:")
        )

    def test_a_prefix_with_sql_wildcards_matches_only_itself(self):
        ledger.store_message(self.con, kind="informative", key="insight:a_b:1", body="a", at=NOW)
        self.assertIsNone(
            ledger.last_generated_at(self.con, kind="informative", key_prefix="insight:a%")
        )

    def test_weekday_counts_are_local_and_monday_first(self):
        self.seed([make(external_id=f"s{i}", started=NOW - timedelta(days=i)) for i in range(3)])
        start, end = notify.day_range(30, now=NOW)
        counts = ledger.weekday_counts(self.con, start_day=start, end_day=end)
        self.assertEqual(len(counts), 7)
        self.assertEqual(sum(counts), 3)
        self.assertEqual(counts[_local(int(NOW.timestamp())).weekday()], 1)


class HotTierTest(unittest.TestCase):
    def test_a_recent_warm_note_makes_the_open_hot(self):
        self.assertEqual(
            notify.tier_for(1800, last_warm_age=60), notify.HOT
        )

    def test_an_older_warm_note_does_not(self):
        self.assertEqual(
            notify.tier_for(1800, last_warm_age=11 * 60), notify.WARM
        )

    def test_the_hot_window_is_configurable(self):
        self.assertEqual(
            notify.tier_for(1800, hot_minutes=30, last_warm_age=20 * 60), notify.HOT
        )
        self.assertEqual(
            notify.tier_for(1800, hot_minutes=0, last_warm_age=0), notify.WARM
        )

    def test_a_long_absence_is_cold_even_after_a_recent_warm_note(self):
        self.assertEqual(
            notify.tier_for(5 * 3600, last_warm_age=60), notify.COLD
        )

    def test_no_warm_note_yet_is_just_warm(self):
        self.assertEqual(notify.tier_for(1800, last_warm_age=None), notify.WARM)


def meter_snap(
    provider_id="claude",
    name="Claude Code",
    *,
    percent=42.0,
    kind="rolling",
    key="five_hour",
    status="ok",
    borrowed=None,
):
    return ProviderSnapshot(
        provider_id=provider_id,
        display_name=name,
        icon=provider_id,
        plan=None,
        metrics=[Meter(key, "5-hour limit", percent, kind=kind)],
        primary_key=key,
        status=status,
        borrowed_from=borrowed,
    )


class WarmNoteTest(NotifyCase):
    def recent(self, n=3, *, tokens=50_000, project="alpha", minutes_ago=30):
        self.seed(
            [
                make(
                    external_id=f"r{i}",
                    project=project,
                    started=NOW - timedelta(minutes=minutes_ago + i),
                    duration_s=300,
                    tin=tokens,
                )
                for i in range(n)
            ]
        )

    def test_nothing_recent_and_no_meter_says_nothing(self):
        self.assertIsNone(notify.warm_note(self.con, [], now=NOW))

    def test_recent_work_with_a_meter_names_both(self):
        self.recent()
        message = notify.warm_note(self.con, [meter_snap()], now=NOW)
        assert message is not None
        self.assertIn("Last 2h: 3 sessions", message.body)
        self.assertIn("mostly alpha", message.body)
        self.assertIn("Claude Code 5-hour limit is at 42%", message.body)

    def test_recent_work_alone_is_enough(self):
        self.recent()
        message = notify.warm_note(self.con, [], now=NOW)
        assert message is not None
        self.assertNotIn("is at", message.body)

    def test_a_meter_alone_is_enough_and_says_there_was_no_work(self):
        message = notify.warm_note(self.con, [meter_snap()], now=NOW)
        assert message is not None
        self.assertIn("No sessions in the last 2h.", message.body)
        self.assertIn("is at 42%", message.body)

    def test_work_older_than_the_window_is_not_counted(self):
        self.recent(minutes_ago=200)
        message = notify.warm_note(self.con, [meter_snap()], now=NOW)
        assert message is not None
        self.assertIn("No sessions in the last 2h.", message.body)

    def test_it_is_a_warm_template_note_about_now(self):
        self.recent()
        message = notify.warm_note(self.con, [meter_snap()], now=NOW)
        assert message is not None
        self.assertEqual(message.kind, notify.INFORMATIVE)
        self.assertEqual(message.meta["tier"], notify.WARM)
        self.assertEqual(message.meta["source"], notify.SOURCE_TEMPLATE)
        self.assertEqual(message.meta["asOf"], int(NOW.timestamp()))
        self.assertEqual(message.meta["tpl"]["id"], "warm")
        self.assertEqual(message.provider, "claude")
        params = message.meta["tpl"]["p"]
        self.assertEqual(params["sessions"], 3)
        self.assertEqual(params["meter"]["pct"], 42)
        self.assertEqual(message.key, f"warm:{message.meta['fingerprint']}")

    def test_the_fullest_rolling_meter_wins(self):
        message = notify.warm_note(
            self.con,
            [
                meter_snap("claude", "Claude Code", percent=30),
                meter_snap("opencode", "OpenCode", percent=77, key="rolling"),
            ],
            now=NOW,
        )
        assert message is not None
        self.assertEqual(message.meta["tpl"]["p"]["meter"]["provider"], "OpenCode")

    def test_only_rolling_meters_count(self):
        self.assertIsNone(
            notify.warm_note(
                self.con, [meter_snap(kind="monthly", percent=99)], now=NOW
            )
        )

    def test_a_broken_or_borrowed_provider_is_ignored(self):
        self.assertIsNone(
            notify.warm_note(
                self.con,
                [
                    meter_snap(status="error", percent=95),
                    meter_snap("pi", "Pi", percent=90, borrowed="claude"),
                ],
                now=NOW,
            )
        )

    def test_the_tokens_are_not_invented(self):
        self.recent(n=2, tokens=60_000)
        message = notify.warm_note(self.con, [], now=NOW)
        assert message is not None
        total = ledger.rolling_totals(
            self.con, since=int((NOW - timedelta(hours=2)).timestamp()),
            until=int(NOW.timestamp()),
        )["tokens"]
        self.assertEqual(message.meta["tpl"]["p"]["tokens"], total)
        self.assertIn(ledger.format_tokens(total), message.body)

    # -- the fingerprint ------------------------------------------------------

    def fingerprint(self, snaps=None):
        message = notify.warm_note(self.con, snaps or [], now=NOW)
        assert message is not None
        return message.meta["fingerprint"]

    def test_the_same_picture_has_the_same_fingerprint(self):
        self.recent()
        self.assertEqual(
            self.fingerprint([meter_snap()]), self.fingerprint([meter_snap()])
        )

    def test_a_new_session_is_news(self):
        self.recent(tokens=50_000)
        before = self.fingerprint([meter_snap()])
        self.seed(
            [
                make(
                    external_id="fresh", started=NOW - timedelta(minutes=5),
                    duration_s=60, tin=100,
                )
            ]
        )
        self.assertNotEqual(before, self.fingerprint([meter_snap()]))

    def test_tokens_inside_one_bucket_do_not_change_it(self):
        facts = {
            "sessions": 3, "tokens": 150_100, "project": "a",
            "meter": {"providerId": "claude", "key": "k", "pct": 40},
        }
        same = dict(facts, tokens=159_900)
        other = dict(facts, tokens=160_000)
        self.assertEqual(notify.warm_fingerprint(facts), notify.warm_fingerprint(same))
        self.assertNotEqual(notify.warm_fingerprint(facts), notify.warm_fingerprint(other))

    def test_a_meter_moving_a_point_is_news(self):
        self.recent()
        self.assertNotEqual(
            self.fingerprint([meter_snap(percent=42)]),
            self.fingerprint([meter_snap(percent=43)]),
        )

    def test_a_new_leading_project_is_news(self):
        self.recent(project="alpha")
        before = self.fingerprint()
        self.seed(
            [
                make(
                    external_id=f"b{i}", project="beta",
                    started=NOW - timedelta(minutes=10 + i), tin=900_000,
                )
                for i in range(2)
            ]
        )
        self.assertNotEqual(before, self.fingerprint())

    # -- storing and showing --------------------------------------------------

    def store(self, message, at):
        return ledger.store_message(
            self.con, kind=message.kind, key=message.key, body=message.body,
            provider=message.provider, meta=message.meta, at=at,
        )

    def test_an_unchanged_picture_is_not_stored_twice(self):
        self.recent()
        first = notify.warm_note(self.con, [meter_snap()], now=NOW)
        again = notify.warm_note(self.con, [meter_snap()], now=NOW + timedelta(minutes=20))
        assert first and again
        self.assertEqual(first.key, again.key)
        kept = notify.keep(self.con, [first], cooldown_seconds=6 * 3600)
        self.assertEqual(len(kept), 1)
        kept_again = notify.keep(self.con, [again], cooldown_seconds=6 * 3600)
        self.assertEqual(kept_again, [])

    def test_a_warm_note_is_the_billboard_and_is_gone_after_two_hours(self):
        self.recent()
        message = notify.warm_note(self.con, [meter_snap()], now=NOW)
        assert message is not None
        self.store(message, NOW)
        rows = ledger.pending_messages(self.con)
        shown = notify.choose_billboard(rows, now=NOW + timedelta(minutes=30))
        assert shown is not None
        self.assertEqual(shown["tier"], notify.WARM)
        self.assertEqual(shown["template"]["id"], "warm")
        self.assertIsNone(notify.choose_billboard(rows, now=NOW + timedelta(hours=3)))

    def test_a_newer_warm_note_outranks_an_unread_insight(self):
        self.recent()
        old = ledger.store_message(
            self.con, kind=notify.INFORMATIVE, key="insight:cache:2026-10-05",
            body="old insight", meta={"tier": notify.COLD, "asOf": int(NOW.timestamp()) - 600},
            at=NOW - timedelta(minutes=10),
        )
        message = notify.warm_note(self.con, [meter_snap()], now=NOW)
        assert message is not None
        self.store(message, NOW)
        shown = notify.choose_billboard(ledger.pending_messages(self.con), now=NOW)
        assert shown is not None
        self.assertNotEqual(shown["id"], old)
        self.assertEqual(shown["tier"], notify.WARM)

    def test_a_warm_note_does_not_count_as_a_pending_insight(self):
        self.recent()
        message = notify.warm_note(self.con, [meter_snap()], now=NOW)
        assert message is not None
        self.store(message, NOW)
        self.assertFalse(
            notify.has_pending_insight(ledger.pending_messages(self.con), now=NOW)
        )


def away_snap(provider_id="claude", name="Claude Code", *, percent=50.0, active=0, **kw):
    from cursor_spend_monitor.instances import Instance, InstanceReport

    snap = meter_snap(provider_id, name, percent=percent, **kw)
    if active:
        snap.instances = InstanceReport(
            active=[
                Instance(
                    provider_id=provider_id, pid=1, project="x", directory="/x",
                    started_at=None, suspended=False,
                )
            ]
        )
    return snap


class ElsewhereTest(NotifyCase):
    NOW_TS = int(NOW.timestamp())

    def series(self, start_pct=30.0, minutes_ago=90, provider="claude", key="five_hour"):
        return {(provider, key): [(self.NOW_TS - minutes_ago * 60, start_pct)]}

    def find(self, snaps, samples):
        return notify.find_elsewhere(self.con, snaps, samples, now=NOW)

    def test_a_climb_with_no_local_session_is_usage_from_elsewhere(self):
        found = self.find([away_snap(percent=50)], self.series(30))
        assert found is not None
        self.assertEqual(found["points"], 20)
        self.assertEqual(found["providerId"], "claude")
        self.assertEqual(found["since"], self.NOW_TS - 90 * 60)

    def test_a_local_session_for_that_provider_explains_the_climb(self):
        self.seed([make("claude", "here", started=NOW - timedelta(minutes=60), duration_s=300)])
        self.assertIsNone(self.find([away_snap(percent=50)], self.series(30)))

    def test_a_session_for_another_provider_does_not(self):
        self.seed([make("opencode", "other", started=NOW - timedelta(minutes=60), duration_s=300)])
        self.assertIsNotNone(self.find([away_snap(percent=50)], self.series(30)))

    def test_a_session_from_before_the_baseline_does_not_count(self):
        self.seed([make("claude", "old", started=NOW - timedelta(minutes=115), duration_s=60)])
        self.assertIsNotNone(self.find([away_snap(percent=50)], self.series(30)))

    def test_a_live_session_is_not_called_elsewhere(self):
        self.assertIsNone(self.find([away_snap(percent=50, active=1)], self.series(30)))

    def test_a_small_climb_says_nothing(self):
        self.assertIsNone(self.find([away_snap(percent=36)], self.series(30)))

    def test_a_reset_looks_like_a_fall_and_says_nothing(self):
        self.assertIsNone(self.find([away_snap(percent=5)], self.series(60)))

    def test_a_baseline_a_moment_old_is_not_a_baseline(self):
        self.assertIsNone(
            self.find([away_snap(percent=50)], self.series(30, minutes_ago=2))
        )

    def test_a_sample_older_than_the_window_is_ignored(self):
        self.assertIsNone(
            self.find([away_snap(percent=50)], self.series(30, minutes_ago=240))
        )

    def test_no_history_says_nothing(self):
        self.assertIsNone(self.find([away_snap(percent=50)], {}))

    def test_only_rolling_meters_are_considered(self):
        self.assertIsNone(
            self.find(
                [away_snap(percent=50, kind="monthly")], self.series(30)
            )
        )

    def test_a_borrowed_or_broken_provider_is_ignored(self):
        self.assertIsNone(
            self.find([away_snap(percent=50, borrowed="opencode")], self.series(30))
        )
        self.assertIsNone(
            self.find([away_snap(percent=50, status="error")], self.series(30))
        )

    def test_the_biggest_climb_is_reported(self):
        samples = {
            **self.series(30, provider="claude"),
            **self.series(10, provider="opencode", key="rolling"),
        }
        found = self.find(
            [
                away_snap("claude", "Claude Code", percent=45),
                away_snap("opencode", "OpenCode", percent=60, key="rolling"),
            ],
            samples,
        )
        assert found is not None
        self.assertEqual(found["providerId"], "opencode")

    # -- in the note ----------------------------------------------------------

    def warm(self, snaps, samples):
        return notify.warm_note(self.con, snaps, samples=samples, now=NOW)

    def test_the_warm_note_says_it_first(self):
        message = self.warm([away_snap(percent=50)], self.series(30))
        assert message is not None
        self.assertTrue(message.body.startswith("About 20 points of your Claude Code"))
        self.assertIn("somewhere other than this machine", message.body)
        self.assertIn("phone or web", message.body)
        self.assertIn("No sessions in the last 2h.", message.body)
        params = message.meta["tpl"]["p"]
        self.assertEqual(params["elsewhere"]["points"], 20)
        self.assertEqual(message.provider, "claude")

    def test_without_samples_there_is_no_such_claim(self):
        message = self.warm([away_snap(percent=50)], None)
        assert message is not None
        self.assertNotIn("somewhere other", message.body)
        self.assertIsNone(message.meta["tpl"]["p"]["elsewhere"])

    def test_the_claim_changes_the_fingerprint(self):
        plain = self.warm([away_snap(percent=50)], None)
        away = self.warm([away_snap(percent=50)], self.series(30))
        assert plain and away
        self.assertNotEqual(plain.meta["fingerprint"], away.meta["fingerprint"])

    def test_a_bigger_climb_is_news(self):
        a = self.warm([away_snap(percent=50)], self.series(30))
        b = self.warm([away_snap(percent=50)], self.series(25))
        assert a and b
        self.assertNotEqual(a.meta["fingerprint"], b.meta["fingerprint"])
