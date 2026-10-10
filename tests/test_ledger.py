"""Tests for the usage ledger: schema, keyed writes, folding and the reports.

The store is behind every later number — a digest, a notification, a share
line — so these tests lean on the two properties that make it trustworthy:
writing the same thing twice changes nothing, and a recomputed day always
equals the sessions it came from.
"""

from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from cursor_spend_monitor import __main__ as cli
from cursor_spend_monitor import ledger

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def make(
    provider: str = "claude",
    external_id: str = "s1",
    *,
    model: str | None = "claude-opus-5-5",
    project: str | None = "alpha",
    started: datetime = NOW,
    duration_s: int = 600,
    tin: int = 100,
    tout: int = 20,
    treas: int = 0,
    tcr: int = 0,
    tcw: int = 0,
    cost: float | None = 0.5,
    source: str = "local-transcript",
) -> ledger.SessionRow:
    return ledger.SessionRow(
        provider=provider,
        source=source,
        external_id=external_id,
        model=model,
        project=project,
        directory=f"/home/u/{project}" if project else None,
        started_at=int(started.timestamp()),
        ended_at=int(started.timestamp()) + duration_s,
        duration_s=duration_s,
        tokens_input=tin,
        tokens_output=tout,
        tokens_reasoning=treas,
        tokens_cache_read=tcr,
        tokens_cache_write=tcw,
        cost_usd=cost,
        turns=3,
    )


class LedgerCase(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.path = Path(self._dir.name) / "usage.db"
        self.con = ledger.connect(self.path)
        self.addCleanup(self.con.close)

    def count(self, table: str) -> int:
        """Row count for one of the fixed tables these tests use.

        Written as literals rather than an interpolated table name: the whole
        point of the store is that no statement is composed at runtime.
        """
        if table == "sessions":
            row = self.con.execute("SELECT COUNT(*) FROM sessions").fetchone()
        elif table == "daily":
            row = self.con.execute("SELECT COUNT(*) FROM daily").fetchone()
        elif table == "hourly":
            row = self.con.execute("SELECT COUNT(*) FROM hourly").fetchone()
        elif table == "per_model":
            row = self.con.execute("SELECT COUNT(*) FROM per_model").fetchone()
        elif table == "messages":
            row = self.con.execute("SELECT COUNT(*) FROM messages").fetchone()
        else:
            raise KeyError(table)
        return int(row[0])


class SchemaTest(LedgerCase):
    def test_the_store_is_created_with_the_tables_it_needs(self):
        names = {
            row[0]
            for row in self.con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        self.assertLessEqual(
            {
                "sessions",
                "per_model",
                "daily",
                "hourly",
                "harvest_state",
                "checks",
                "messages",
                "ledger_meta",
            },
            names,
        )

    def test_opening_twice_is_stable(self):
        again = ledger.connect(self.path)
        self.addCleanup(again.close)
        self.assertEqual(ledger.stored_format_version(again), ledger.FORMAT_VERSION)

    def test_a_newer_store_refuses_writes_rather_than_guessing(self):
        self.con.execute(
            "UPDATE ledger_meta SET value = '99' WHERE key = 'format_version'"
        )
        self.con.commit()
        with self.assertRaises(ledger.LedgerTooNewError):
            ledger.assert_writable(self.con)

    def test_writable_is_silent_on_a_current_store(self):
        ledger.assert_writable(self.con)


class SessionWriteTest(LedgerCase):
    def test_the_same_session_twice_is_one_row(self):
        ledger.upsert_sessions(self.con, [make()])
        ledger.upsert_sessions(self.con, [make()])
        self.assertEqual(self.count("sessions"), 1)

    def test_rewriting_an_unchanged_session_writes_nothing(self):
        # The count is "rows that changed". A harvest that finds nothing new has
        # to be able to say so, or every run reports phantom work.
        rows = [make()]
        self.assertEqual(ledger.upsert_sessions(self.con, rows), 1)
        self.assertEqual(ledger.upsert_sessions(self.con, rows), 0)

    def test_a_running_session_grows_in_place(self):
        # Token columns are absolute totals, so the second write replaces the
        # first rather than adding to it.
        ledger.upsert_sessions(self.con, [make(tin=100, tout=20)])
        ledger.upsert_sessions(self.con, [make(tin=250, tout=40)])
        self.assertEqual(self.count("sessions"), 1)
        stored = self.con.execute(
            "SELECT tokens_input, tokens_output FROM sessions"
        ).fetchone()
        self.assertEqual(stored[0], 250)
        self.assertEqual(stored[1], 40)

    def test_a_row_with_no_cost_does_not_erase_a_measured_one(self):
        ledger.upsert_sessions(self.con, [make(cost=0.75)])
        ledger.upsert_sessions(self.con, [make(cost=None)])
        cost = self.con.execute("SELECT cost_usd FROM sessions").fetchone()[0]
        self.assertEqual(cost, 0.75)

    def test_malformed_vendor_values_do_not_raise(self):
        row = make()
        # A store we do not control can hand back a string where a number was
        # expected; that must not take a harvest (or the daemon) down.
        row.tokens_input = "not-a-number"  # type: ignore[assignment]
        row.tokens_cache_read = "12"  # type: ignore[assignment]
        row.started_at = "whenever"  # type: ignore[assignment]
        row.cost_usd = "free"  # type: ignore[assignment]
        ledger.upsert_sessions(self.con, [row])
        stored = self.con.execute(
            "SELECT tokens_input, tokens_cache_read, started_at, cost_usd FROM sessions"
        ).fetchone()
        self.assertEqual(stored["tokens_input"], 0)
        self.assertEqual(stored["tokens_cache_read"], 12)
        self.assertIsNone(stored["started_at"])
        self.assertIsNone(stored["cost_usd"])

    def test_an_empty_batch_writes_nothing(self):
        self.assertEqual(ledger.upsert_sessions(self.con, []), 0)
        self.assertEqual(self.count("sessions"), 0)

    def test_model_family_is_derived_when_the_harvester_does_not_say(self):
        ledger.upsert_sessions(self.con, [make(model="claude-opus-5-5")])
        family = self.con.execute("SELECT model_family FROM sessions").fetchone()[0]
        self.assertEqual(family, "claude-opus-5")


class ModelFamilyTest(unittest.TestCase):
    def test_a_point_release_is_trimmed(self):
        self.assertEqual(ledger.model_family_of("claude-opus-5-5"), "claude-opus-5")

    def test_an_already_stable_name_is_kept(self):
        self.assertEqual(
            ledger.model_family_of("deepseek-v4-flash"), "deepseek-v4-flash"
        )

    def test_a_codename_is_not_trimmed(self):
        self.assertEqual(ledger.model_family_of("gpt-5.6-sol"), "gpt-5.6-sol")

    def test_a_date_suffix_is_trimmed(self):
        self.assertEqual(
            ledger.model_family_of("claude-3-5-sonnet-20241022"),
            "claude-3-5-sonnet",
        )

    def test_a_family_that_is_already_stable_is_kept(self):
        self.assertEqual(ledger.model_family_of("claude-opus-5"), "claude-opus-5")

    def test_a_family_is_never_invented(self):
        # Dropping the trailing digit would leave "gpt", which is not a model.
        self.assertEqual(ledger.model_family_of("gpt-5"), "gpt-5")

    def test_missing_and_empty_are_none(self):
        self.assertIsNone(ledger.model_family_of(None))
        self.assertIsNone(ledger.model_family_of(""))


class FoldTest(LedgerCase):
    def test_a_day_folds_into_daily_and_hourly(self):
        rows = [
            make(),
            make(external_id="s2", provider="opencode", model="deepseek-v4-flash"),
        ]
        ledger.upsert_sessions(self.con, rows)
        self.assertEqual(ledger.fold_days(self.con, ledger.affected_days(rows)), 1)
        self.assertEqual(self.count("daily"), 2)
        self.assertEqual(self.count("hourly"), 2)

    def test_folding_twice_changes_nothing(self):
        rows = [make()]
        ledger.upsert_sessions(self.con, rows)
        ledger.fold_days(self.con, ledger.affected_days(rows))
        before = self.con.execute("SELECT * FROM daily").fetchall()
        ledger.fold_days(self.con, ledger.affected_days(rows))
        after = self.con.execute("SELECT * FROM daily").fetchall()
        self.assertEqual([tuple(r) for r in before], [tuple(r) for r in after])

    def test_a_grown_session_is_recomputed_not_added(self):
        rows = [make(tin=100, cost=1.0)]
        ledger.upsert_sessions(self.con, rows)
        ledger.fold_days(self.con, ledger.affected_days(rows))
        tokens = self.con.execute("SELECT tokens FROM daily").fetchone()[0]
        self.assertEqual(tokens, 120)

        grown = [make(tin=300, cost=1.4)]
        ledger.upsert_sessions(self.con, grown)
        ledger.fold_days(self.con, ledger.affected_days(grown))
        # 300 + 20 output, not 120 + 320.
        totals = self.con.execute("SELECT tokens, cost_usd FROM daily").fetchone()
        self.assertEqual(totals[0], 320)
        self.assertAlmostEqual(totals[1], 1.4)

    def test_hourly_carries_the_same_sessions_as_daily(self):
        started = NOW.replace(hour=12)
        rows = [
            make(external_id="a", started=started),
            make(
                external_id="b",
                provider="opencode",
                started=started + timedelta(hours=1),
            ),
        ]
        ledger.upsert_sessions(self.con, rows)
        ledger.fold_days(self.con, ledger.affected_days(rows))
        daily_sessions = self.con.execute("SELECT SUM(sessions) FROM daily").fetchone()[
            0
        ]
        hourly_sessions = self.con.execute(
            "SELECT SUM(session_count) FROM hourly"
        ).fetchone()[0]
        self.assertEqual(daily_sessions, hourly_sessions)

    def test_fold_all_rebuilds_every_day(self):
        rows = [
            make(external_id="a", started=NOW - timedelta(days=2)),
            make(external_id="b", started=NOW),
        ]
        ledger.upsert_sessions(self.con, rows)
        self.assertEqual(ledger.fold_all(self.con), 2)
        self.assertEqual(self.count("daily"), 2)

    def test_an_estimate_is_counted_as_such_in_the_rollup(self):
        rows = [make(source="estimate")]
        ledger.upsert_sessions(self.con, rows)
        ledger.fold_days(self.con, ledger.affected_days(rows))
        estimated = self.con.execute("SELECT estimated_sessions FROM daily").fetchone()[
            0
        ]
        self.assertEqual(estimated, 1)


class ReportTest(LedgerCase):
    def seed(self) -> None:
        rows = [
            make(
                external_id="c1",
                provider="claude",
                model="claude-opus-5-5",
                project="alpha",
                started=datetime(2026, 10, 1, 10, tzinfo=timezone.utc),
                duration_s=1200,
                tin=1000,
                tcr=3000,
                cost=1.0,
            ),
            make(
                external_id="o1",
                provider="opencode",
                model="deepseek-v4-flash",
                project="alpha",
                started=datetime(2026, 10, 1, 11, tzinfo=timezone.utc),
                duration_s=1200,
                tin=2000,
                cost=0.1,
            ),
            make(
                external_id="c2",
                provider="claude",
                model="claude-opus-5-5",
                project="beta",
                started=datetime(2026, 10, 2, 9, tzinfo=timezone.utc),
                duration_s=100,
                tin=500,
                cost=2.0,
            ),
            make(
                external_id="o2",
                provider="opencode",
                model="deepseek-v4-flash",
                project="beta",
                started=datetime(2026, 10, 3, 9, tzinfo=timezone.utc),
                duration_s=3 * 3600 + 60,
                tin=400,
                cost=0.2,
                source="estimate",
            ),
        ]
        ledger.upsert_sessions(self.con, rows)
        ledger.fold_all(self.con)

    def report(self, **kwargs):
        return ledger.period_totals(
            self.con, start_day="2026-10-01", end_day="2026-10-03", **kwargs
        )

    def test_period_totals_by_provider(self):
        self.seed()
        rows = {r["provider"]: r for r in self.report()}
        self.assertEqual(rows["claude"]["sessions"], 2)
        self.assertEqual(rows["opencode"]["sessions"], 2)
        self.assertAlmostEqual(rows["claude"]["cost_usd"], 3.0)

    def test_a_whole_period_summary(self):
        self.seed()
        summary = ledger.totals(self.con, start_day="2026-10-01", end_day="2026-10-03")
        self.assertEqual(summary["sessions"], 4)
        self.assertEqual(summary["tokens"], 6980)
        self.assertEqual(summary["cache_read_tokens"], 3000)
        self.assertAlmostEqual(summary["cost_usd"], 3.3)
        self.assertEqual(summary["estimated_sessions"], 1)

    def test_group_by_project_and_model(self):
        self.seed()
        projects = {
            r["project"]: r["sessions"] for r in self.report(group_by="project")
        }
        self.assertEqual(projects, {"alpha": 2, "beta": 2})
        models = {r["model"]: r["sessions"] for r in self.report(group_by="model")}
        self.assertEqual(models, {"claude-opus-5-5": 2, "deepseek-v4-flash": 2})

    def test_group_by_day_orders_oldest_ties_by_token_volume(self):
        self.seed()
        days = self.report(group_by="day")
        self.assertEqual(days[0]["day"], "2026-10-01")
        self.assertEqual(days[0]["tokens"], 6040)

    def test_a_provider_filter_narrows_the_rows(self):
        self.seed()
        rows = self.report(provider="opencode")
        self.assertEqual([r["provider"] for r in rows], ["opencode"])

    def test_a_limit_caps_the_rows(self):
        self.seed()
        self.assertEqual(len(self.report(limit=1)), 1)

    def test_an_unknown_grouping_says_what_is_known(self):
        with self.assertRaises(ValueError) as caught:
            self.report(group_by="nonsense")
        self.assertIn("provider", str(caught.exception))

    def test_hour_grouping_reads_the_hourly_rollup(self):
        self.seed()
        rows = self.report(group_by="hour")
        self.assertEqual(sum(r["sessions"] for r in rows), 4)

    def test_sources_say_when_a_period_includes_an_estimate(self):
        self.seed()
        self.assertEqual(
            ledger.sources_in(self.con, start_day="2026-10-01", end_day="2026-10-03"),
            ["estimate", "local-transcript"],
        )

    def test_cache_share_reports_the_cached_fraction(self):
        self.seed()
        share = ledger.cache_share(
            self.con, start_day="2026-10-01", end_day="2026-10-03"
        )
        self.assertEqual(share["cache_read_tokens"], 3000)
        self.assertAlmostEqual(share["share"], 3000 / 6980)

    def test_records_pick_the_extremes(self):
        self.seed()
        found = ledger.records(self.con, start_day="2026-10-01", end_day="2026-10-03")
        self.assertEqual(found["max_tokens_day"]["day"], "2026-10-01")
        self.assertEqual(found["longest_session"]["provider"], "opencode")
        self.assertAlmostEqual(found["costliest_session"]["cost_usd"], 2.0)

    def test_streaks_count_consecutive_days(self):
        self.seed()
        found = ledger.streaks(
            self.con, now=datetime(2026, 10, 3, 23, tzinfo=timezone.utc)
        )
        self.assertEqual(found["longest"], 3)
        self.assertEqual(found["current"], 3)

    def test_a_streak_that_ended_yesterday_is_over(self):
        self.seed()
        found = ledger.streaks(
            self.con, now=datetime(2026, 10, 10, tzinfo=timezone.utc)
        )
        self.assertEqual(found["current"], 0)
        self.assertEqual(found["longest"], 3)

    def test_session_shape_buckets_by_duration(self):
        self.seed()
        shape = ledger.session_shape(
            self.con, start_day="2026-10-01", end_day="2026-10-03"
        )
        self.assertEqual(shape["sessions"], 4)
        self.assertEqual(shape["duration_buckets"]["under 15m"], 1)
        self.assertEqual(shape["duration_buckets"]["15m to 1h"], 2)
        self.assertEqual(shape["duration_buckets"]["over 3h"], 1)
        self.assertEqual(len(shape["hours"]), 24)
        self.assertEqual(sum(shape["hours"]), 4)

    def test_an_empty_period_is_all_zeroes(self):
        summary = ledger.totals(self.con, start_day="2026-01-01", end_day="2026-01-02")
        self.assertEqual(summary["sessions"], 0)
        self.assertEqual(summary["tokens"], 0)
        self.assertEqual(
            ledger.sources_in(self.con, start_day="2026-01-01", end_day="2026-01-02"),
            [],
        )


class PruneTest(LedgerCase):
    def test_raw_sessions_expire_but_the_rollup_stays(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=120)
        rows = [
            make(external_id="old", started=old),
            make(external_id="new", started=now - timedelta(days=1)),
        ]
        ledger.upsert_sessions(self.con, rows)
        ledger.fold_all(self.con)
        self.assertEqual(self.count("daily"), 2)

        removed = ledger.prune(self.con, keep_days=90)
        self.assertEqual(removed["sessions"], 1)
        self.assertEqual(self.count("sessions"), 1)
        # "This month vs last month" has to keep working after the events go.
        self.assertEqual(self.count("daily"), 2)

    def test_a_session_with_no_start_time_is_kept(self):
        row = make()
        row.started_at = None
        row.ended_at = None
        ledger.upsert_sessions(self.con, [row])
        ledger.prune(self.con, keep_days=1)
        self.assertEqual(self.count("sessions"), 1)

    def test_retention_off_prunes_nothing(self):
        ledger.upsert_sessions(self.con, [make(started=NOW - timedelta(days=900))])
        removed = ledger.prune(self.con, keep_days=0)
        self.assertEqual(
            removed, {"sessions": 0, "messages": 0, "transcript_messages": 0}
        )


class PerModelTest(LedgerCase):
    def test_cycle_rows_are_keyed_and_replaceable(self):
        ledger.upsert_per_model(
            self.con,
            [
                ledger.PerModelRow(
                    "cursor", "gpt-5", "2026-10-31", tokens_input=10, cost_usd=0.2
                )
            ],
        )
        ledger.upsert_per_model(
            self.con,
            [
                ledger.PerModelRow(
                    "cursor", "gpt-5", "2026-10-31", tokens_input=99, cost_usd=0.9
                )
            ],
        )
        self.assertEqual(self.count("per_model"), 1)
        tokens = self.con.execute("SELECT tokens_input FROM per_model").fetchone()[0]
        self.assertEqual(tokens, 99)

    def test_rewriting_an_unchanged_cycle_row_writes_nothing(self):
        row = ledger.PerModelRow(
            "cursor", "gpt-5", "2026-10-31", tokens_input=10, cost_usd=0.2
        )
        self.assertEqual(ledger.upsert_per_model(self.con, [row]), 1)
        self.assertEqual(ledger.upsert_per_model(self.con, [row]), 0)


class CheckTest(LedgerCase):
    def test_a_cross_check_is_recorded_with_its_verdict(self):
        ledger.record_check(
            self.con, ledger.CheckRow("cursor", "spend_vs_plan", "off by 3%", ok=False)
        )
        found = ledger.recent_checks(self.con)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["kind"], "spend_vs_plan")
        self.assertEqual(found[0]["ok"], 0)


class MessageTest(LedgerCase):
    def test_the_latest_message_is_the_newest(self):
        ledger.store_message(self.con, kind="daily", key="2026-10-01", body="first")
        ledger.store_message(self.con, kind="daily", key="2026-10-02", body="second")
        found = ledger.latest_message(self.con)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found["body"], "second")

    def test_recent_messages_are_newest_first_and_limited(self):
        for day in range(1, 5):
            ledger.store_message(
                self.con, kind="daily", key=f"2026-10-0{day}", body=f"m{day}"
            )
        found = ledger.recent_messages(self.con, limit=3)
        self.assertEqual([m["body"] for m in found], ["m4", "m3", "m2"])

    def test_a_stored_message_carries_its_share_line(self):
        ledger.store_message(
            self.con, kind="weekly", key="2026-W40", body="body", share="SHARE: hi"
        )
        found = ledger.latest_message(self.con)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found["share"], "SHARE: hi")

    def test_the_cooldown_key_is_the_kind_and_key(self):
        ledger.store_message(self.con, kind="weekly", key="2026-W40", body="body")
        age = ledger.last_message_age(self.con, kind="weekly", key="2026-W40")
        self.assertIsNotNone(age)
        assert age is not None
        self.assertGreaterEqual(age, 0)
        self.assertIsNone(
            ledger.last_message_age(self.con, kind="weekly", key="2026-W41")
        )

    def test_the_same_message_is_one_row(self):
        # A timestamp used to be part of the identity, so generating the same
        # message again in a different second made a second row -- and a
        # dismissal is stored per row, so the panel could offer an identical
        # message again under a new id.
        first = ledger.store_message(
            self.con, kind="daily", key="2026-10-08", body="first"
        )
        again = ledger.store_message(
            self.con,
            kind="daily",
            key="2026-10-08",
            body="second",
            at=datetime.now(timezone.utc) + timedelta(seconds=5),
        )
        self.assertEqual(self.count("messages"), 1)
        self.assertEqual(first, again)
        found = ledger.latest_message(self.con)
        assert found is not None
        self.assertEqual(found["body"], "second")

    def test_restating_a_message_keeps_it_acknowledged(self):
        mid = ledger.store_message(self.con, kind="daily", key="k", body="body")
        self.assertEqual(ledger.mark_message_seen(self.con, mid), 1)
        ledger.store_message(self.con, kind="daily", key="k", body="reworded")
        found = ledger.latest_message(self.con)
        assert found is not None
        self.assertEqual(found["body"], "reworded")
        self.assertIsNotNone(found["seen_at"])

    def test_an_old_store_folds_its_duplicates(self):
        # The shape 0.5.0 wrote: two rows for one logical message, one of them
        # acknowledged. The survivor has to carry the newest wording and the
        # dismissal, or upgrading silently resurrects a message the user read.
        path = Path(self._dir.name) / "old.db"
        old = sqlite3.connect(path)
        old.executescript(
            "CREATE TABLE messages ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " kind TEXT NOT NULL,"
            " key TEXT NOT NULL,"
            " created_at INTEGER NOT NULL,"
            " provider TEXT,"
            " body TEXT NOT NULL,"
            " share TEXT,"
            " meta TEXT,"
            " seen_at INTEGER,"
            " UNIQUE(kind, key, created_at));"
            "INSERT INTO messages (kind, key, created_at, body, seen_at)"
            " VALUES ('daily', 'k', 100, 'oldest', 555);"
            "INSERT INTO messages (kind, key, created_at, body, seen_at)"
            " VALUES ('daily', 'k', 200, 'newest', NULL);"
            "INSERT INTO messages (kind, key, created_at, body)"
            " VALUES ('daily', 'other', 150, 'other');"
        )
        old.commit()
        old.close()

        migrated = ledger.connect(path)
        self.addCleanup(migrated.close)
        rows = list(
            migrated.execute("SELECT key, body, seen_at FROM messages ORDER BY key")
        )
        self.assertEqual([row[0] for row in rows], ["k", "other"])
        self.assertEqual(rows[0][1], "newest")
        self.assertEqual(rows[0][2], 555)

    def test_messages_expire_with_retention(self):
        now = datetime.now(timezone.utc)
        ledger.store_message(
            self.con, kind="daily", key="old", body="old", at=now - timedelta(days=120)
        )
        ledger.store_message(self.con, kind="daily", key="new", body="new", at=now)
        removed = ledger.prune(self.con, keep_days=90, keep_messages_days=90)
        self.assertEqual(removed["messages"], 1)
        self.assertEqual(self.count("messages"), 1)


class RecorderTest(LedgerCase):
    def test_the_wrapper_records_and_folds(self):
        recorder = ledger.LedgerRecorder(self.path)
        self.addCleanup(recorder.close)
        self.assertTrue(recorder.active)
        rows = [make()]
        self.assertEqual(recorder.upsert_sessions(rows), 1)
        self.assertEqual(recorder.fold_days(ledger.affected_days(rows)), 1)

    def test_a_worker_thread_gets_its_own_connection(self):
        # The daemon harvests and composes on worker threads, and a sqlite3
        # connection belongs to the thread that created it. Borrowing the main
        # loop's made every harvest fail on "SQLite objects created in a thread
        # can only be used in that same thread", so the ledger quietly stopped
        # filling while the panel still looked perfectly healthy.
        recorder = ledger.LedgerRecorder(self.path)
        self.addCleanup(recorder.close)
        result: list[object] = []

        def work() -> None:
            try:
                with recorder.worker() as con:
                    self.assertIsNot(con, recorder.connection)
                    if con is None:
                        result.append("the worker got no connection")
                    else:
                        row = con.execute("SELECT COUNT(*) FROM sessions").fetchone()
                        result.append(row[0])
            except Exception as exc:  # noqa: BLE001 - reported by the assertion
                result.append(exc)

        thread = threading.Thread(target=work, name="ai-usage-test")
        thread.start()
        thread.join()
        self.assertEqual(result, [0])

    def test_a_worker_write_reaches_the_main_connection(self):
        # What the harvest does, end to end: the worker writes on its own
        # connection and the next read anywhere sees it.
        recorder = ledger.LedgerRecorder(self.path)
        self.addCleanup(recorder.close)

        def work() -> None:
            with recorder.worker() as con:
                if con is not None:
                    ledger.upsert_sessions(con, [make()])

        thread = threading.Thread(target=work, name="ai-usage-test")
        thread.start()
        thread.join()
        self.assertEqual(self.count("sessions"), 1)

    def test_an_unopenable_store_disables_quietly(self):
        with (
            mock.patch.object(ledger, "connect", side_effect=sqlite3.Error("locked")),
            mock.patch("sys.stderr"),
        ):
            recorder = ledger.LedgerRecorder(self.path)
        self.assertFalse(recorder.active)
        self.assertEqual(recorder.upsert_sessions([make()]), 0)

    def test_a_too_new_store_disables_rather_than_writes(self):
        con = ledger.connect(self.path)
        con.execute("UPDATE ledger_meta SET value = '99' WHERE key = 'format_version'")
        con.commit()
        con.close()
        with mock.patch("sys.stderr"):
            recorder = ledger.LedgerRecorder(self.path)
        self.assertFalse(recorder.active)

    def test_a_write_failure_disables_rather_than_raises(self):
        recorder = ledger.LedgerRecorder(self.path)
        self.addCleanup(recorder.close)
        with (
            mock.patch.object(
                ledger, "upsert_sessions", side_effect=sqlite3.Error("full")
            ),
            mock.patch("sys.stderr"),
        ):
            self.assertEqual(recorder.upsert_sessions([make()]), 0)
        self.assertFalse(recorder.active)


class FormattingTest(unittest.TestCase):
    def test_tokens_read_as_quantities(self):
        self.assertEqual(ledger.format_tokens(0), "0")
        self.assertEqual(ledger.format_tokens(999), "999")
        self.assertEqual(ledger.format_tokens(1500), "1.5K")
        self.assertEqual(ledger.format_tokens(2_000_000), "2M")
        self.assertEqual(ledger.format_tokens(8_400_000), "8.4M")

    def test_tokens_tolerate_junk(self):
        self.assertEqual(ledger.format_tokens(None), "0")
        self.assertEqual(ledger.format_tokens("nonsense"), "0")  # type: ignore[arg-type]

    def test_cost_is_dollars_or_a_dash(self):
        self.assertEqual(ledger.format_cost(None), "—")
        self.assertEqual(ledger.format_cost(4.1), "$4.10")


class ReportCliTest(LedgerCase):
    """`report` reads the ledger and renders it; it never touches the network."""

    def seed(self) -> None:
        rows = [
            make(
                external_id="c1",
                provider="claude",
                model="claude-opus-5-5",
                project="alpha",
                started=datetime(2026, 10, 1, 10, tzinfo=timezone.utc),
                tin=1000,
                cost=1.0,
            ),
            make(
                external_id="o1",
                provider="opencode",
                model="deepseek-v4-flash",
                project="beta",
                started=datetime(2026, 10, 2, 10, tzinfo=timezone.utc),
                tin=2000,
                cost=0.1,
            ),
        ]
        ledger.upsert_sessions(self.con, rows)
        ledger.fold_all(self.con)

    def run_report(self, argv: list[str]) -> tuple[int, str]:
        real_connect = ledger.connect
        out = io.StringIO()
        with (
            mock.patch.object(
                ledger, "connect", side_effect=lambda: real_connect(self.path)
            ),
            redirect_stdout(out),
        ):
            code = cli.main(["report", *argv])
        return code, out.getvalue()

    def test_json_reports_totals_and_rows(self):
        self.seed()
        code, out = self.run_report(
            ["--since", "2026-10-01", "--until", "2026-10-02", "--json"]
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["totals"]["sessions"], 2)
        self.assertEqual(
            {r["provider"] for r in payload["rows"]}, {"claude", "opencode"}
        )

    def test_text_names_the_grouping_when_asked_for_models(self):
        self.seed()
        code, out = self.run_report(
            ["--since", "2026-10-01", "--until", "2026-10-02", "--by", "model"]
        )
        self.assertEqual(code, 0)
        self.assertIn("deepseek-v4-flash", out)
        self.assertIn("2 sessions", out)

    def test_a_provider_filter_narrows_the_report(self):
        self.seed()
        _, out = self.run_report(
            ["--since", "2026-10-01", "--until", "2026-10-02", "--provider", "claude"]
        )
        self.assertIn("claude", out)
        self.assertNotIn("opencode", out)

    def test_an_empty_period_says_so_rather_than_printing_nothing(self):
        code, out = self.run_report(["--since", "2026-01-01", "--until", "2026-01-02"])
        self.assertEqual(code, 0)
        self.assertIn("No sessions recorded", out)

    def test_a_malformed_date_is_its_own_error(self):
        with self.assertRaises(SystemExit):
            self.run_report(["--since", "yesterday", "--until", "2026-10-02"])

    def test_only_one_sided_range_is_refused(self):
        with self.assertRaises(SystemExit):
            self.run_report(["--since", "2026-10-01"])

    def test_checks_are_reported_when_present(self):
        ledger.record_check(
            self.con, ledger.CheckRow("cursor", "spend_vs_plan", "off by 3%", ok=False)
        )
        code, out = self.run_report(["--checks"])
        self.assertEqual(code, 0)
        self.assertIn("FAIL", out)
        self.assertIn("spend_vs_plan", out)

    def test_no_checks_is_an_answer_not_an_error(self):
        code, out = self.run_report(["--checks"])
        self.assertEqual(code, 0)
        self.assertIn("No cross-checks", out)


if __name__ == "__main__":
    unittest.main()
