"""Tests for the Codex thread-store reader.

Codex has nothing to read on this machine, so the tests build the store the
reader is written for and also pin the empty-store behaviour that matters most
today: it must record what it found and write nothing, not fail and not guess.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from cursor_spend_monitor import ledger
from cursor_spend_monitor.harvesters.codex_state import CodexStateHarvester

RICH_SCHEMA = """
CREATE TABLE threads (
    id             TEXT PRIMARY KEY,
    model          TEXT,
    model_provider TEXT,
    cwd            TEXT,
    tokens_used    INTEGER,
    created_at     INTEGER,
    updated_at     INTEGER
);
"""

EMPTY_SCHEMA = "CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT);"

SECONDS = int(datetime(2026, 10, 1, 10, tzinfo=timezone.utc).timestamp())


class CodexCase(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.root = Path(self._dir.name)
        self.db = self.root / "state_5.sqlite"
        self.con = ledger.connect(self.root / "usage.db")
        self.addCleanup(self.con.close)

    def make(self, schema: str) -> CodexStateHarvester:
        con = sqlite3.connect(self.db)
        con.executescript(schema)
        con.commit()
        con.close()
        return CodexStateHarvester(self.db)

    def add_thread(self, **values) -> None:
        # One fixed statement with bound values: a thread helper that composed
        # its column list would be the very pattern the reader avoids.
        con = sqlite3.connect(self.db)
        con.execute(
            "INSERT INTO threads (id, model, model_provider, cwd, tokens_used,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                values.get("id"),
                values.get("model"),
                values.get("model_provider"),
                values.get("cwd"),
                values.get("tokens_used"),
                values.get("created_at"),
                values.get("updated_at"),
            ),
        )
        con.commit()
        con.close()

    def sessions(self) -> list[sqlite3.Row]:
        return self.con.execute("SELECT * FROM sessions").fetchall()

    def checks(self) -> list[sqlite3.Row]:
        return self.con.execute("SELECT kind, detail, ok FROM checks").fetchall()


class EmptyStoreTest(CodexCase):
    def test_no_token_column_writes_nothing_and_records_the_schema(self):
        reader = self.make(EMPTY_SCHEMA)
        result = reader.harvest(self.con)
        self.assertFalse(result.failed)
        self.assertEqual(result.sessions, 0)
        self.assertIn("no token column", result.note)
        self.assertEqual(self.sessions(), [])
        probed = self.checks()
        self.assertEqual(probed[0]["kind"], "threads_schema")
        self.assertIn("title", probed[0]["detail"])

    def test_a_real_threads_table_with_no_rows_is_still_no_rows(self):
        reader = self.make(RICH_SCHEMA)
        result = reader.harvest(self.con)
        self.assertFalse(result.failed)
        self.assertEqual(result.scanned, 0)

    def test_a_missing_store_is_a_note(self):
        reader = CodexStateHarvester(self.root / "nope.sqlite")
        self.assertFalse(reader.available())
        result = reader.harvest(self.con)
        self.assertFalse(result.failed)
        self.assertEqual(result.note, "no local store")


class ReadingTest(CodexCase):
    def seed(self) -> CodexStateHarvester:
        reader = self.make(RICH_SCHEMA)
        self.add_thread(
            id="t1",
            model="gpt-5-codex",
            model_provider="openai",
            cwd="/home/u/alpha",
            tokens_used=12345,
            created_at=SECONDS,
            updated_at=SECONDS + 600,
        )
        return reader

    def test_a_thread_becomes_a_session(self):
        reader = self.seed()
        result = reader.harvest(self.con)
        self.assertEqual(result.sessions, 1)
        row = self.sessions()[0]
        self.assertEqual(row["provider"], "codex")
        self.assertEqual(row["external_id"], "t1")
        self.assertEqual(row["model"], "gpt-5-codex")
        self.assertEqual(row["project"], "alpha")
        self.assertEqual(row["tokens_input"], 12345)
        self.assertEqual(row["duration_s"], 600)

    def test_the_account_lands_in_meta(self):
        reader = self.seed()
        reader.harvest(self.con)
        self.assertIn("openai", self.sessions()[0]["meta"])

    def test_millisecond_timestamps_are_converted(self):
        reader = self.make(RICH_SCHEMA)
        self.add_thread(
            id="t1",
            tokens_used=5,
            created_at=SECONDS * 1000,
            updated_at=(SECONDS + 60) * 1000,
        )
        reader.harvest(self.con)
        self.assertEqual(self.sessions()[0]["duration_s"], 60)

    def test_an_unchanged_store_writes_nothing_on_a_second_run(self):
        reader = self.seed()
        self.assertEqual(reader.harvest(self.con).sessions, 1)
        self.assertEqual(reader.harvest(self.con).sessions, 0)

    def test_a_missing_id_column_still_yields_a_row(self):
        reader = self.make(
            "CREATE TABLE threads (tokens_used INTEGER, created_at INTEGER);"
        )
        con = sqlite3.connect(self.db)
        con.execute(
            "INSERT INTO threads (tokens_used, created_at) VALUES (?, ?)",
            (7, SECONDS),
        )
        con.commit()
        con.close()
        result = reader.harvest(self.con)
        self.assertEqual(result.sessions, 1)
        self.assertTrue(self.sessions()[0]["external_id"].startswith("thread-"))


if __name__ == "__main__":
    unittest.main()
