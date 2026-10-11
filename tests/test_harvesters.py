"""Tests for the OpenCode reader and the `harvest` command.

This reader is the first thing that writes real vendor data into the ledger, so
these tests are about the properties the ledger's numbers depend on: writing an
unchanged store twice changes nothing, the watermark never runs ahead of the
data, and a store the TUI is holding open is skipped rather than waited on.
"""

from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from tokens_go_brrr import __main__ as cli
from tokens_go_brrr import ledger
from tokens_go_brrr.harvesters import build
from tokens_go_brrr.harvesters.opencode_db import OpenCodeHarvester

# The columns this reader depends on, which is all a test needs: the real table
# carries more, and a reader that needed them would be reading more than it says.
SCHEMA = """
CREATE TABLE session (
    id                 TEXT PRIMARY KEY,
    directory          TEXT,
    model              TEXT,
    agent              TEXT,
    cost               REAL,
    tokens_input       INTEGER DEFAULT 0,
    tokens_output      INTEGER DEFAULT 0,
    tokens_reasoning   INTEGER DEFAULT 0,
    tokens_cache_read  INTEGER DEFAULT 0,
    tokens_cache_write INTEGER DEFAULT 0,
    time_created       INTEGER,
    time_updated       INTEGER
);
CREATE TABLE message (
    id           TEXT PRIMARY KEY,
    session_id   TEXT,
    time_created INTEGER
);
"""


def ms(*parts: int) -> int:
    """Epoch milliseconds, which is what OpenCode stores."""
    return int(datetime(*parts, tzinfo=timezone.utc).timestamp() * 1000)


class OpenCodeCase(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.root = Path(self._dir.name)
        self.oc_path = self.root / "opencode.db"
        self._make_store()
        self.ledger_path = self.root / "usage.db"
        self.con = ledger.connect(self.ledger_path)
        self.addCleanup(self.con.close)
        self.reader = OpenCodeHarvester(self.oc_path)

    def _make_store(self, schema: str = SCHEMA) -> None:
        con = sqlite3.connect(self.oc_path)
        con.executescript(schema)
        con.commit()
        con.close()

    def _oc(self) -> sqlite3.Connection:
        return sqlite3.connect(self.oc_path)

    def add_session(
        self,
        session_id: str = "s1",
        *,
        model: str | None = '{"id": "deepseek-v4-flash", "providerID": "opencode-go"}',
        directory: str | None = "/home/u/alpha",
        cost: float | None = 0.5,
        tin: int = 100,
        tout: int = 20,
        treas: int = 0,
        tcr: int = 0,
        tcw: int = 0,
        agent: str | None = "build",
        created: int | None = None,
        updated: int | None = None,
        messages: int = 0,
    ) -> None:
        start = ms(2026, 10, 1, 10) if created is None else created
        end = start + 60_000 if updated is None else updated
        con = self._oc()
        con.execute(
            "INSERT INTO session (id, directory, model, agent, cost, tokens_input,"
            " tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write,"
            " time_created, time_updated)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " directory = excluded.directory, model = excluded.model,"
            " agent = excluded.agent, cost = excluded.cost,"
            " tokens_input = excluded.tokens_input,"
            " tokens_output = excluded.tokens_output,"
            " tokens_reasoning = excluded.tokens_reasoning,"
            " tokens_cache_read = excluded.tokens_cache_read,"
            " tokens_cache_write = excluded.tokens_cache_write,"
            " time_updated = excluded.time_updated",
            (
                session_id,
                directory,
                model,
                agent,
                cost,
                tin,
                tout,
                treas,
                tcr,
                tcw,
                start,
                end,
            ),
        )
        for index in range(messages):
            con.execute(
                "INSERT OR REPLACE INTO message (id, session_id, time_created)"
                " VALUES (?, ?, ?)",
                (f"{session_id}-m{index}", session_id, end),
            )
        con.commit()
        con.close()

    def all_sessions(self) -> list[sqlite3.Row]:
        return self.con.execute("SELECT * FROM sessions").fetchall()


class ReaderTest(OpenCodeCase):
    def test_the_tools_own_numbers_land_in_the_ledger(self):
        self.add_session(
            "s1",
            cost=0.022,
            tin=48848,
            tout=6561,
            treas=3651,
            tcr=650624,
        )
        result = self.reader.harvest(self.con)
        self.assertEqual(result.scanned, 1)
        self.assertEqual(result.sessions, 1)

        row = self.all_sessions()[0]
        self.assertEqual(row["provider"], "opencode")
        self.assertEqual(row["source"], "local-db")
        self.assertEqual(row["external_id"], "s1")
        self.assertEqual(row["model"], "deepseek-v4-flash")
        self.assertEqual(row["model_family"], "deepseek-v4-flash")
        self.assertEqual(row["project"], "alpha")
        self.assertEqual(row["directory"], "/home/u/alpha")
        self.assertEqual(row["tokens_cache_read"], 650624)
        self.assertEqual(row["tokens_reasoning"], 3651)
        self.assertAlmostEqual(row["cost_usd"], 0.022)

    def test_the_account_is_kept_even_though_the_provider_is_the_tool(self):
        self.add_session("s1")
        self.reader.harvest(self.con)
        meta = json.loads(self.all_sessions()[0]["meta"])
        self.assertEqual(meta["account"], "opencode-go")
        self.assertEqual(meta["agent"], "build")

    def test_duration_comes_from_the_tool_timestamps(self):
        self.add_session(
            "s1", created=ms(2026, 10, 1, 10), updated=ms(2026, 10, 1, 10, 30)
        )
        self.reader.harvest(self.con)
        self.assertEqual(
            self.con.execute("SELECT duration_s FROM sessions").fetchone()[0], 1800
        )

    def test_turns_are_counted_from_the_message_table(self):
        self.add_session("s1", messages=3)
        self.reader.harvest(self.con)
        self.assertEqual(
            self.con.execute("SELECT turns FROM sessions").fetchone()[0], 3
        )

    def test_a_store_without_a_message_table_still_reads_sessions(self):
        self.add_session("s1")
        con = self._oc()
        con.execute("DROP TABLE message")
        con.commit()
        con.close()
        result = self.reader.harvest(self.con)
        self.assertEqual(result.sessions, 1)
        self.assertIsNone(self.con.execute("SELECT turns FROM sessions").fetchone()[0])

    def test_rollups_are_rebuilt_from_what_was_read(self):
        self.add_session("s1")
        self.reader.harvest(self.con)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM daily").fetchone()[0], 1
        )
        self.assertEqual(
            self.con.execute("SELECT tokens FROM daily").fetchone()[0], 120
        )
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM hourly").fetchone()[0], 1
        )

    def test_the_reader_format_is_recorded(self):
        self.reader.harvest(self.con)
        self.assertEqual(ledger.reader_format(self.con, "opencode"), 1)


class IdempotencyTest(OpenCodeCase):
    def test_an_unchanged_store_writes_nothing_on_a_second_run(self):
        self.add_session("s1")
        first = self.reader.harvest(self.con)
        self.assertEqual(first.sessions, 1)
        self.assertEqual(first.folded_days, 1)

        second = self.reader.harvest(self.con)
        self.assertEqual(second.scanned, 0)
        self.assertEqual(second.sessions, 0)
        self.assertEqual(second.folded_days, 0)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1
        )

    def test_only_sessions_newer_than_the_watermark_are_read(self):
        self.add_session("old", updated=ms(2026, 10, 1, 10))
        self.reader.harvest(self.con)
        self.add_session("new", updated=ms(2026, 10, 2, 10))

        result = self.reader.harvest(self.con)
        self.assertEqual(result.scanned, 1)
        self.assertEqual(result.sessions, 1)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 2
        )

    def test_a_running_session_grows_in_place(self):
        start = ms(2026, 10, 1, 10)
        self.add_session("live", tin=100, updated=start + 60_000)
        self.reader.harvest(self.con)
        self.add_session("live", tin=900, updated=start + 120_000)

        result = self.reader.harvest(self.con)
        self.assertEqual(result.sessions, 1)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1
        )
        self.assertEqual(
            self.con.execute("SELECT tokens_input FROM sessions").fetchone()[0], 900
        )

    def test_full_ignores_the_watermark_but_still_writes_nothing_new(self):
        self.add_session("s1")
        self.reader.harvest(self.con)
        result = self.reader.harvest(self.con, full=True)
        self.assertEqual(result.scanned, 1)
        self.assertEqual(result.sessions, 0)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1
        )


class FailureTest(OpenCodeCase):
    def test_a_missing_store_is_a_note_not_a_failure(self):
        reader = OpenCodeHarvester(self.root / "nope.db")
        self.assertFalse(reader.available())
        result = reader.harvest(self.con)
        self.assertFalse(result.failed)
        self.assertEqual(result.note, "no local database")

    def test_a_locked_store_is_skipped_and_leaves_the_watermark_alone(self):
        before = ledger.watermark(self.con, "opencode")[0]
        with mock.patch.object(
            sqlite3,
            "connect",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            result = self.reader.harvest(self.con)
        self.assertTrue(result.failed)
        self.assertIn("locked", result.note)
        # The watermark must never lead the data: a skipped read has to be
        # re-read next time, not assumed done.
        self.assertEqual(ledger.watermark(self.con, "opencode")[0], before)

    def test_an_unparsable_model_is_kept_as_the_model_name(self):
        self.add_session("s1", model="not json at all")
        self.reader.harvest(self.con)
        self.assertEqual(
            self.con.execute("SELECT model FROM sessions").fetchone()[0],
            "not json at all",
        )

    def test_a_model_object_without_an_account_has_none(self):
        self.add_session("s1", model='{"id": "gpt-5"}', agent=None)
        self.reader.harvest(self.con)
        meta = self.all_sessions()[0]["meta"]
        self.assertIsNone(meta)


class RegistryTest(unittest.TestCase):
    def test_the_registry_exposes_every_reader(self):
        self.assertEqual(
            sorted(reader.provider for reader in build()),
            ["claude", "codex", "cursor", "opencode", "pi"],
        )

    def test_building_for_an_unknown_provider_yields_nothing(self):
        self.assertEqual(build(["does-not-exist"]), [])


class HarvestCliTest(OpenCodeCase):
    def run_harvest(self, argv: list[str]) -> tuple[int, str]:
        real_connect = ledger.connect
        out = io.StringIO()
        with (
            mock.patch.object(
                ledger, "connect", side_effect=lambda: real_connect(self.ledger_path)
            ),
            mock.patch(
                "tokens_go_brrr.harvesters.build", return_value=[self.reader]
            ),
            redirect_stdout(out),
        ):
            code = cli.main(["harvest", *argv])
        return code, out.getvalue()

    def test_harvest_reports_what_changed(self):
        self.add_session("s1")
        code, out = self.run_harvest([])
        self.assertEqual(code, 0)
        self.assertIn("opencode: 1 sessions", out)
        self.assertIn("1 day(s) folded", out)

    def test_a_second_harvest_says_no_change(self):
        self.add_session("s1")
        self.run_harvest([])
        code, out = self.run_harvest([])
        self.assertEqual(code, 0)
        self.assertIn("no change", out)

    def test_a_missing_store_is_reported_as_not_installed(self):
        self.reader = OpenCodeHarvester(self.root / "nope.db")
        code, out = self.run_harvest([])
        self.assertEqual(code, 0)
        self.assertIn("not installed", out)

    def test_a_too_new_ledger_exits_nonzero(self):
        self.con.execute(
            "UPDATE ledger_meta SET value = '99' WHERE key = 'format_version'"
        )
        self.con.commit()
        code, _out = self.run_harvest([])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
