"""Tests for the notification engine's wording, mixing and cooldowns.

Everything here runs without an LLM, which is the point of shipping templates
first: the triggers, the mixer and the cooldowns are all verifiable before any
model is in the loop. The tests also pin the two things a message must never do
— invent a number, or present an estimate as a measurement.
"""

from __future__ import annotations

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
