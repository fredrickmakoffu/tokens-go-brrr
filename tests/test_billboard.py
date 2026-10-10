"""Tests for the landing page: what earns the interruption, and what does not.

The routing rules are the part with edge cases, and they are pure Python, so
they are tested directly rather than through the panel. Three properties matter
most: an acknowledged message never comes back, a stale one stops interrupting
on its own, and the AI the page features is read out of the ledger rather than
being a fixed mapping.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from cursor_spend_monitor import ledger
from cursor_spend_monitor import notify_engine as notify
from cursor_spend_monitor.config import MonitorConfig
from cursor_spend_monitor.providers.base import Meter, ProviderSnapshot

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
NOW_TS = int(NOW.timestamp())

# A `messages` table as it existed before the landing page, without `seen_at`.
OLD_MESSAGES = """
CREATE TABLE messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT    NOT NULL,
    key        TEXT    NOT NULL,
    created_at INTEGER NOT NULL,
    provider   TEXT,
    body       TEXT    NOT NULL,
    share      TEXT,
    meta       TEXT,
    UNIQUE(kind, key, created_at)
);
"""


def row(
    message_id: int,
    kind: str,
    *,
    created: int | None = None,
    provider: str = "claude",
    role: str = "leading",
    body: str = "a message",
) -> dict:
    """One stored message, as `pending_messages` would return it."""
    return {
        "id": message_id,
        "kind": kind,
        "key": f"k{message_id}",
        "created_at": NOW_TS if created is None else created,
        "provider": provider,
        "body": body,
        "share": None,
        "meta": json.dumps({"role": role, "providerName": provider.title()}),
    }


def snap(provider_id: str, name: str, percent: float) -> ProviderSnapshot:
    return ProviderSnapshot(
        provider_id=provider_id,
        display_name=name,
        icon=provider_id,
        plan=None,
        metrics=[Meter("five_hour", "5-hour limit", percent, kind="rolling")],
        primary_key="five_hour",
        status="ok",
    )


class MigrationTest(unittest.TestCase):
    """The first additive schema change: it must upgrade a store in place."""

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.root = Path(self._dir.name)
        self.path = self.root / "usage.db"

    def test_an_older_store_gains_the_column_without_losing_rows(self):
        old = sqlite3.connect(self.path)
        old.executescript(OLD_MESSAGES)
        old.execute(
            "INSERT INTO messages (kind, key, created_at, body)"
            " VALUES ('fun', 'k', 1, 'an older row')"
        )
        old.commit()
        old.close()

        con = ledger.connect(self.path)
        self.addCleanup(con.close)
        columns = {r[1] for r in con.execute("PRAGMA table_info(messages)")}
        self.assertIn("seen_at", columns)
        kept = con.execute("SELECT body FROM messages").fetchone()[0]
        self.assertEqual(kept, "an older row")

    def test_running_the_migration_twice_is_a_no_op(self):
        ledger.connect(self.path).close()
        again = ledger.connect(self.path)
        self.addCleanup(again.close)
        columns = [r[1] for r in again.execute("PRAGMA table_info(messages)")]
        self.assertEqual(columns.count("seen_at"), 1)


class RoutingTest(unittest.TestCase):
    def chosen(self, rows: list[dict], *, now: datetime = NOW) -> dict:
        """`choose_billboard`, narrowed, for the tests that expect a winner."""
        result = notify.choose_billboard(rows, now=now)
        self.assertIsNotNone(result)
        assert result is not None
        return result

    def test_nothing_pending_means_no_landing_page(self):
        self.assertIsNone(notify.choose_billboard([], now=NOW))

    def test_an_actionable_warning_outranks_a_fresher_digest(self):
        chosen = self.chosen(
            [
                row(1, notify.INFORMATIVE, created=NOW_TS),
                row(2, notify.ACTIONABLE, created=NOW_TS - 3600),
            ]
        )
        self.assertEqual(chosen["id"], 2)
        self.assertEqual(chosen["kind"], notify.ACTIONABLE)

    def test_the_newest_wins_within_a_kind(self):
        chosen = self.chosen(
            [
                row(1, notify.FUN, created=NOW_TS - 600),
                row(2, notify.FUN, created=NOW_TS - 60),
            ]
        )
        self.assertEqual(chosen["id"], 2)

    def test_a_stale_digest_stops_interrupting(self):
        chosen = notify.choose_billboard(
            [row(1, notify.INFORMATIVE, created=NOW_TS - 25 * 3600)], now=NOW
        )
        self.assertIsNone(chosen)

    def test_windows_are_per_kind(self):
        # Seven hours old: past the actionable window, well inside the digest's.
        stale_warning = row(1, notify.ACTIONABLE, created=NOW_TS - 7 * 3600)
        fresh_digest = row(2, notify.INFORMATIVE, created=NOW_TS - 7 * 3600)
        self.assertIsNone(notify.choose_billboard([stale_warning], now=NOW))
        self.assertEqual(self.chosen([fresh_digest])["id"], 2)

    def test_the_payload_carries_what_the_panel_renders(self):
        chosen = self.chosen(
            [row(7, notify.ACTIONABLE, provider="opencode", role="suggested")]
        )
        self.assertEqual(chosen["id"], 7)
        self.assertEqual(chosen["priority"], notify.PRIORITY[notify.ACTIONABLE])
        self.assertEqual(
            chosen["featured"],
            {"providerId": "opencode", "name": "Opencode", "role": "suggested"},
        )
        self.assertEqual(chosen["expiresAt"], NOW_TS + 6 * 3600)
        self.assertIn("text", chosen)
        self.assertIn("reason", chosen)

    def test_a_message_with_no_provider_still_renders(self):
        chosen = self.chosen([row(1, notify.FUN, provider="", role="")])
        self.assertIsNone(chosen["featured"])


class FeaturedProviderTest(unittest.TestCase):
    """The featured AI is read from the ledger, never a fixed mapping."""

    def featured(self, facts: dict) -> dict:
        """`featured_provider`, narrowed, for the tests that expect a winner."""
        found = notify.featured_provider(facts)
        self.assertIsNotNone(found)
        assert found is not None
        return found

    def test_the_leader_is_featured_when_no_cheaper_provider_stands_out(self):
        facts = {
            "ranked": [
                {"provider": "claude", "tokens": 1000, "cost_usd": 10.0},
                # 10% of the period: real, but below the floor for the story.
                {"provider": "opencode", "tokens": 100, "cost_usd": 1.0},
            ]
        }
        featured = self.featured(facts)
        self.assertEqual(featured["providerId"], "claude")
        self.assertEqual(featured["role"], "leading")

    def test_a_cheaper_provider_doing_real_work_becomes_the_story(self):
        facts = {
            "ranked": [
                {"provider": "claude", "tokens": 1000, "cost_usd": 20.0},
                # 44% of the tokens at a twentieth of the cost per token.
                {"provider": "opencode", "tokens": 800, "cost_usd": 1.0},
            ]
        }
        featured = self.featured(facts)
        self.assertEqual(featured["providerId"], "opencode")
        self.assertEqual(featured["role"], "value")
        self.assertIn("$1.00", featured["reason"])

    def test_a_provider_with_no_cost_cannot_win_on_value(self):
        facts = {
            "ranked": [
                {"provider": "claude", "tokens": 1000, "cost_usd": 0},
                {"provider": "opencode", "tokens": 900, "cost_usd": 0},
            ]
        }
        self.assertEqual(self.featured(facts)["providerId"], "claude")

    def test_nothing_recorded_means_nothing_featured(self):
        self.assertIsNone(notify.featured_provider({"ranked": []}))
        self.assertIsNone(notify.featured_provider({}))

    def test_the_names_come_from_the_provider_classes(self):
        # Not a second copy of the names: the providers already own them.
        facts = {"ranked": [{"provider": "claude", "tokens": 10, "cost_usd": 1.0}]}
        self.assertEqual(self.featured(facts)["name"], "Claude Code")


class MessageFeatureTest(unittest.TestCase):
    """Generated messages carry who they are about."""

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.con = ledger.connect(Path(self._dir.name) / "usage.db")
        self.addCleanup(self.con.close)

    def seed(self) -> None:
        rows = [
            ledger.SessionRow(
                provider="opencode",
                source="local-db",
                external_id="o1",
                model="deepseek-v4-flash",
                project="alpha",
                started_at=NOW_TS - 3600,
                duration_s=600,
                tokens_input=800,
                tokens_output=0,
                cost_usd=1.0,
            ),
            ledger.SessionRow(
                provider="claude",
                source="local-transcript",
                external_id="c1",
                model="claude-opus-5-5",
                project="alpha",
                started_at=NOW_TS - 3600,
                duration_s=600,
                tokens_input=1000,
                tokens_output=0,
                cost_usd=20.0,
            ),
        ]
        ledger.upsert_sessions(self.con, rows)
        ledger.fold_all(self.con)

    def test_a_digest_features_a_provider_and_says_why(self):
        self.seed()
        message = notify.weekly_digest(self.con, now=NOW)
        assert message is not None
        self.assertTrue(message.provider)
        self.assertIn(message.meta.get("role"), {"leading", "value"})
        self.assertTrue(message.meta.get("providerName"))
        self.assertTrue(message.meta.get("reason"))

    def test_an_actionable_message_features_where_to_move_to(self):
        messages = notify.event_messages(
            [snap("claude", "Claude Code", 93), snap("opencode", "OpenCode", 5)]
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].provider, "opencode")
        self.assertEqual(messages[0].meta["role"], "suggested")
        self.assertEqual(messages[0].meta["trigger"], "claude")

    def test_an_actionable_message_with_nowhere_to_go_features_the_trigger(self):
        messages = notify.event_messages([snap("claude", "Claude Code", 95)])
        self.assertEqual(messages[0].provider, "claude")


class AcknowledgementTest(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.con = ledger.connect(Path(self._dir.name) / "usage.db")
        self.addCleanup(self.con.close)

    def store(self, **kwargs) -> int:
        return ledger.store_message(self.con, **kwargs)

    def test_an_unread_message_is_pending(self):
        self.store(kind="fun", key="k", body="body")
        self.assertEqual(len(ledger.pending_messages(self.con)), 1)

    def test_acknowledging_removes_it_from_pending(self):
        mid = self.store(kind="fun", key="k", body="body")
        self.assertEqual(ledger.mark_message_seen(self.con, mid), 1)
        self.assertEqual(ledger.pending_messages(self.con), [])

    def test_acknowledging_twice_changes_nothing(self):
        mid = self.store(kind="fun", key="k", body="body")
        ledger.mark_message_seen(self.con, mid)
        self.assertEqual(ledger.mark_message_seen(self.con, mid), 0)

    def test_an_acknowledged_message_still_shows_as_latest(self):
        # "Show me the most recent one" has to work months later, so the
        # Latest affordance ignores both acknowledgement and freshness.
        mid = self.store(kind="fun", key="k", body="body")
        ledger.mark_message_seen(self.con, mid)
        latest = ledger.latest_message(self.con)
        assert latest is not None
        self.assertEqual(latest["id"], mid)
        self.assertIsNotNone(latest["seen_at"])


class DaemonBillboardTest(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.con = ledger.connect(Path(self._dir.name) / "usage.db")
        self.addCleanup(self.con.close)

    def daemon(self, **config_values):
        from cursor_spend_monitor.daemon import UsageDaemon

        stub = mock.Mock()
        stub.config = MonitorConfig(**config_values)
        stub.ledger.connection = self.con
        stub._billboard = None
        stub._latest_message = None
        stub._recent_messages = []
        stub._publish = mock.Mock()
        for name in (
            "_billboard_ids",
            "_refresh_billboard",
            "_publish_billboard_change",
        ):
            setattr(stub, name, types.MethodType(getattr(UsageDaemon, name), stub))
        return stub

    def test_a_pending_message_becomes_the_billboard(self):
        ledger.store_message(self.con, kind="fun", key="k", body="body")
        stub = self.daemon()
        stub._refresh_billboard(self.con)
        self.assertIsNotNone(stub._billboard)
        self.assertIsNotNone(stub._latest_message)

    def test_an_acknowledged_message_is_no_longer_the_billboard(self):
        from cursor_spend_monitor.daemon import UsageDaemon

        mid = ledger.store_message(self.con, kind="fun", key="k", body="body")
        stub = self.daemon()
        stub._refresh_billboard(self.con)
        self.assertEqual(stub._billboard["id"], mid)

        UsageDaemon.acknowledge(stub, mid)
        self.assertIsNone(stub._billboard)
        # ...but it is still the most recent message, for Latest.
        self.assertEqual(stub._latest_message["id"], mid)

    def test_the_landing_page_can_be_turned_off(self):
        ledger.store_message(self.con, kind="fun", key="k", body="body")
        stub = self.daemon(billboard_enabled=False)
        stub._refresh_billboard(self.con)
        self.assertIsNone(stub._billboard)
        self.assertIsNone(stub._latest_message)

    def test_a_failed_digest_does_not_burn_the_slot(self):
        # The digest of 2026-10-07 18:03 died on a worker-thread connection
        # error, having already marked itself sent, so it never tried again: one
        # exception cost a whole day of digests and left a single journal line.
        from cursor_spend_monitor.daemon import UsageDaemon

        stub = self.daemon()
        stub._last_slot = {"daily": "2026-10-08"}
        stub.ledger.worker = mock.Mock(side_effect=sqlite3.Error("no connection"))
        with mock.patch("sys.stderr"):
            UsageDaemon._digest_worker(stub, "daily")
        self.assertNotIn("daily", stub._last_slot)

    def test_an_inactive_ledger_does_not_burn_the_slot(self):
        from cursor_spend_monitor.daemon import UsageDaemon

        stub = self.daemon()
        stub._last_slot = {"daily": "2026-10-08"}
        worker = mock.MagicMock()
        worker.return_value.__enter__.return_value = None
        stub.ledger.worker = worker
        UsageDaemon._digest_worker(stub, "daily")
        self.assertNotIn("daily", stub._last_slot)

    def test_the_freshness_ceiling_caps_what_lands(self):
        # A fun fact is fresh for 12h by kind; the configured ceiling is 1h.
        ledger.store_message(
            self.con,
            kind="fun",
            key="k",
            body="body",
            at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        stub = self.daemon(billboard_freshness_hours=1)
        stub._refresh_billboard(self.con)
        self.assertIsNone(stub._billboard)

    def test_a_new_message_is_published_exactly_once(self):
        # The popover triggers this on every open, so it has to be cheap and
        # quiet when nothing has changed.
        stub = self.daemon()
        self.assertFalse(stub._publish_billboard_change())
        ledger.store_message(self.con, kind="fun", key="k", body="body")
        self.assertTrue(stub._publish_billboard_change())
        self.assertFalse(stub._publish_billboard_change())
        self.assertEqual(stub._publish.call_count, 1)

    def test_acknowledging_republishes_with_the_next_message(self):
        from cursor_spend_monitor.daemon import UsageDaemon

        first = ledger.store_message(self.con, kind="fun", key="a", body="a")
        ledger.store_message(self.con, kind="fun", key="b", body="b")
        stub = self.daemon()
        stub._publish_billboard_change()
        newest = ledger.latest_message(self.con)
        assert newest is not None
        self.assertEqual(stub._billboard["id"], newest["id"])

        UsageDaemon.acknowledge(stub, stub._billboard["id"])
        # Acknowledging the newest leaves the older one as what the page offers.
        self.assertEqual(stub._billboard["id"], first)
        self.assertEqual(stub._publish.call_count, 2)

    def test_the_payload_carries_both_fields_when_absent(self):
        from cursor_spend_monitor.daemon import UsageDaemon

        stub = mock.Mock(
            snapshots=[],
            last_fetch=None,
            last_error=None,
            _billboard=None,
            _latest_message=None,
            _recent_messages=[],
        )
        payload = UsageDaemon.state_payload(stub)
        self.assertIn("billboard", payload)
        self.assertIsNone(payload["billboard"])
        self.assertIsNone(payload["latestMessage"])


if __name__ == "__main__":
    unittest.main()


class DaemonColdNoteTest(unittest.TestCase):
    """The daemon decides when an open is cold and makes the note off-loop."""

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.con = ledger.connect(Path(self._dir.name) / "usage.db")
        self.addCleanup(self.con.close)

    def daemon(self, **config_values):
        from cursor_spend_monitor.daemon import UsageDaemon

        stub = mock.Mock()
        stub.config = MonitorConfig(**config_values)
        stub.ledger.connection = self.con
        stub._last_open = None
        stub._cold_running = False
        stub.poll = mock.Mock(return_value=False)
        stub._wanted = mock.Mock(return_value=True)
        for name in ("panel_opened", "_start_cold_note", "_cold_worker"):
            setattr(stub, name, types.MethodType(getattr(UsageDaemon, name), stub))
        # `_start_cold_note` is the unit under test in some cases and a spy in
        # others; keep a handle on the real one.
        stub.real_start = stub._start_cold_note
        return stub

    def opened(self, stub, at: float) -> None:
        with mock.patch("cursor_spend_monitor.daemon.time.monotonic", return_value=at):
            stub._start_cold_note = mock.Mock()
            stub.panel_opened()

    def test_the_first_open_is_cold(self):
        stub = self.daemon()
        self.opened(stub, 1000.0)
        stub._start_cold_note.assert_called_once()

    def test_a_quick_reopen_is_not_cold(self):
        stub = self.daemon()
        self.opened(stub, 1000.0)
        stub._start_cold_note.reset_mock()
        self.opened(stub, 1000.0 + 600)
        stub._start_cold_note.assert_not_called()

    def test_an_open_after_a_long_absence_is_cold_again(self):
        stub = self.daemon()
        self.opened(stub, 1000.0)
        self.opened(stub, 1000.0 + 5 * 3600)
        stub._start_cold_note.assert_called_once()

    def test_the_threshold_comes_from_the_config(self):
        stub = self.daemon(live_cold_hours=1)
        self.opened(stub, 1000.0)
        self.opened(stub, 1000.0 + 2 * 3600)
        stub._start_cold_note.assert_called_once()

    def test_live_notes_off_never_makes_a_cold_note(self):
        stub = self.daemon(live_notes=False)
        self.opened(stub, 1000.0)
        stub._start_cold_note.assert_not_called()

    def test_every_open_still_refreshes(self):
        stub = self.daemon(live_notes=False)
        self.opened(stub, 1000.0)
        stub.poll.assert_called_once()

    def test_no_thread_starts_while_one_is_running(self):
        stub = self.daemon()
        stub._cold_running = True
        with mock.patch("cursor_spend_monitor.daemon.threading.Thread") as thread:
            stub.real_start()
        thread.assert_not_called()

    def test_no_thread_starts_when_informative_notes_are_unwanted(self):
        stub = self.daemon()
        stub._wanted.return_value = False
        with mock.patch("cursor_spend_monitor.daemon.threading.Thread") as thread:
            stub.real_start()
        thread.assert_not_called()

    def test_a_thread_starts_otherwise(self):
        stub = self.daemon()
        with mock.patch("cursor_spend_monitor.daemon.threading.Thread") as thread:
            stub.real_start()
        thread.return_value.start.assert_called_once()
        self.assertTrue(stub._cold_running)

    def run_worker(self, stub):
        stub.ledger.worker.return_value.__enter__ = mock.Mock(return_value=self.con)
        stub.ledger.worker.return_value.__exit__ = mock.Mock(return_value=False)
        stub._cold_running = True
        with mock.patch("cursor_spend_monitor.daemon.GLib") as glib:
            stub._cold_worker()
        return glib

    def seed(self):
        rows = [
            ledger.SessionRow(
                provider="claude", source="local-transcript", external_id=f"s{i}",
                model="m", project="alpha",
                started_at=int(datetime.now(timezone.utc).timestamp()) - i * 86400,
                ended_at=int(datetime.now(timezone.utc).timestamp()) - i * 86400 + 60,
                duration_s=60, tokens_input=60_000, tokens_cache_read=60_000,
            )
            for i in range(4)
        ]
        ledger.upsert_sessions(self.con, rows)
        ledger.fold_all(self.con)

    def test_the_worker_stores_an_insight_and_asks_for_a_publish(self):
        self.seed()
        stub = self.daemon()
        glib = self.run_worker(stub)
        stored = ledger.pending_messages(self.con)
        self.assertEqual(len(stored), 1)
        self.assertTrue(stored[0]["key"].startswith("insight:"))
        glib.idle_add.assert_called_once_with(stub._publish_cold)
        self.assertFalse(stub._cold_running)

    def test_the_worker_does_not_publish_when_there_is_nothing_to_say(self):
        stub = self.daemon()
        glib = self.run_worker(stub)
        self.assertEqual(ledger.pending_messages(self.con), [])
        glib.idle_add.assert_not_called()
        self.assertFalse(stub._cold_running)

    def test_the_worker_hands_the_flag_back_when_the_ledger_is_gone(self):
        stub = self.daemon()
        stub.ledger.worker.return_value.__enter__ = mock.Mock(return_value=None)
        stub.ledger.worker.return_value.__exit__ = mock.Mock(return_value=False)
        stub._cold_running = True
        with mock.patch("cursor_spend_monitor.daemon.GLib"):
            stub._cold_worker()
        self.assertFalse(stub._cold_running)


class LiveConfigTest(unittest.TestCase):
    def test_defaults(self):
        config = MonitorConfig()
        self.assertTrue(config.live_notes)
        self.assertEqual(config.live_cold_hours, 4.0)
