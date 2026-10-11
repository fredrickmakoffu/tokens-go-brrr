"""Tests for the Pi session reader.

Pi is the one source with no token data at all, so these tests are mostly about
the two claims the reader is allowed to make: sessions and durations are real,
and no token figure is invented. The lifecycle matters too — a session is only
visible while its process runs, so it is written as it is seen and closed out on
a later pass.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from tokens_go_brrr import ledger
from tokens_go_brrr.harvesters.pi_sessions import PiSessionHarvester
from tokens_go_brrr.instances import Instance, InstanceReport
from tokens_go_brrr.providers.pi_backend import Backend

STARTED = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)


def instance(
    pid: int = 4242,
    *,
    project: str = "alpha",
    account: str = "opencode-go",
    model: str = "deepseek-v4-flash",
) -> Instance:
    return Instance(
        provider_id="pi",
        pid=pid,
        project=project,
        directory=f"/home/u/{project}",
        started_at=STARTED,
        suspended=False,
        kind="session",
        tty_nr=0,
        backend=Backend(account=account, model=model, provider_id="opencode"),
    )


class PiCase(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.root = Path(self._dir.name)
        self.con = ledger.connect(self.root / "usage.db")
        self.addCleanup(self.con.close)
        self.reader = PiSessionHarvester()
        installed = mock.patch(
            "tokens_go_brrr.harvesters.pi_sessions.pi_backend.installed",
            return_value=True,
        )
        installed.start()
        self.addCleanup(installed.stop)

    def with_sessions(self, *instances: Instance):
        report = InstanceReport(active=list(instances), suspended=[])
        return mock.patch(
            "tokens_go_brrr.harvesters.pi_sessions.scan",
            return_value={"pi": report},
        )

    def rows(self) -> list:
        return self.con.execute(
            "SELECT * FROM sessions ORDER BY external_id"
        ).fetchall()


class LifecycleTest(PiCase):
    def test_a_live_session_becomes_a_row(self):
        with self.with_sessions(instance()):
            result = self.reader.harvest(self.con)
        self.assertEqual(result.sessions, 1)
        row = self.rows()[0]
        self.assertEqual(row["provider"], "pi")
        self.assertEqual(row["project"], "alpha")
        self.assertEqual(row["model"], "deepseek-v4-flash")
        self.assertEqual(row["started_at"], int(STARTED.timestamp()))

    def test_no_token_figure_is_invented(self):
        with self.with_sessions(instance()):
            self.reader.harvest(self.con)
        row = self.rows()[0]
        self.assertEqual(row["tokens_input"], 0)
        self.assertEqual(row["tokens_output"], 0)
        self.assertEqual(row["tokens_cache_read"], 0)

    def test_the_account_is_recorded(self):
        with self.with_sessions(instance()):
            self.reader.harvest(self.con)
        self.assertIn("opencode-go", self.rows()[0]["meta"])

    def test_a_session_that_disappears_keeps_its_last_seen_end(self):
        with self.with_sessions(instance()):
            self.reader.harvest(self.con)
        first_end = self.rows()[0]["ended_at"]

        # The session is gone. Its row already records the last moment it was
        # seen, so closing it out changes nothing — which is the point: the end
        # is never guessed forward to "now".
        with self.with_sessions():
            result = self.reader.harvest(self.con)
        self.assertEqual(result.sessions, 0)
        row = self.rows()[0]
        self.assertEqual(row["ended_at"], first_end)
        self.assertEqual(len(self.rows()), 1)

    def test_a_closed_session_is_not_written_again(self):
        with self.with_sessions(instance()):
            self.reader.harvest(self.con)
        with self.with_sessions():
            self.reader.harvest(self.con)
        with self.with_sessions():
            result = self.reader.harvest(self.con)
        self.assertEqual(result.sessions, 0)

    def test_two_sessions_are_two_rows(self):
        with self.with_sessions(instance(pid=1), instance(pid=2, project="beta")):
            result = self.reader.harvest(self.con)
        self.assertEqual(result.sessions, 2)
        self.assertEqual({r["project"] for r in self.rows()}, {"alpha", "beta"})


class AvailabilityTest(PiCase):
    def test_no_pi_install_is_a_note(self):
        with mock.patch(
            "tokens_go_brrr.harvesters.pi_sessions.pi_backend.installed",
            return_value=False,
        ):
            self.assertFalse(self.reader.available())
            result = self.reader.harvest(self.con)
        self.assertFalse(result.failed)
        self.assertEqual(result.note, "Pi is not installed")

    def test_a_scan_failure_is_reported_not_raised(self):
        with mock.patch(
            "tokens_go_brrr.harvesters.pi_sessions.scan",
            side_effect=OSError("proc went away"),
        ):
            result = self.reader.harvest(self.con)
        self.assertTrue(result.failed)
        self.assertIn("scan failed", result.note)


if __name__ == "__main__":
    unittest.main()
