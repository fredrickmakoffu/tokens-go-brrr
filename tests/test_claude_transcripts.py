"""Tests for the Claude transcript reader.

The two failure modes this reader exists to avoid are easy to reproduce, so they
are tested directly: a streamed response written as several records must count
once, and a subagent transcript must land on the session that spawned it. The
rest are the properties the ledger depends on — an incremental read that never
loses or double-counts a record.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cursor_spend_monitor import ledger
from cursor_spend_monitor.harvesters.claude_transcripts import ClaudeTranscriptHarvester

ROOT_SLUG = "-home-u-alpha"


def record(
    message_id: str,
    *,
    session: str = "s1",
    ts: str = "2026-10-01T10:00:00.000Z",
    model: str = "claude-opus-5-5",
    cwd: str = "/home/u/alpha",
    entrypoint: str = "cli",
    tin: int = 100,
    tcw: int = 0,
    tcr: int = 0,
    tout: int = 20,
    thinking: int = 0,
    with_session: bool = True,
) -> dict:
    payload = {
        "type": "assistant",
        "cwd": cwd,
        "entrypoint": entrypoint,
        "timestamp": ts,
        "requestId": f"req-{message_id}",
        "message": {
            "id": message_id,
            "model": model,
            "usage": {
                "input_tokens": tin,
                "cache_creation_input_tokens": tcw,
                "cache_read_input_tokens": tcr,
                "output_tokens": tout,
                "output_tokens_details": {"thinking_tokens": thinking},
            },
        },
    }
    if with_session:
        payload["sessionId"] = session
    return payload


class TranscriptCase(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.root = Path(self._dir.name)
        self.con = ledger.connect(self.root / "usage.db")
        self.addCleanup(self.con.close)
        self.reader = ClaudeTranscriptHarvester(self.root)

    def transcript(self, session: str = "s1", slug: str = ROOT_SLUG) -> Path:
        path = self.root / slug / f"{session}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def subagent(self, session: str = "s1", name: str = "agent-a") -> Path:
        path = self.root / ROOT_SLUG / session / "subagents" / f"{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def write(
        path: Path, records: list[dict], *, trailing_newline: bool = True
    ) -> None:
        text = "\n".join(json.dumps(r) for r in records)
        if trailing_newline and records:
            text += "\n"
        path.write_text(text)

    def session_row(self, external_id: str = "s1"):
        row = self.con.execute(
            "SELECT * FROM sessions WHERE provider = 'claude' AND external_id = ?",
            (external_id,),
        ).fetchone()
        return row

    def count(self, table: str) -> int:
        """Row count for one of the fixed tables these tests use, as literals."""
        if table == "sessions":
            row = self.con.execute("SELECT COUNT(*) FROM sessions").fetchone()
        elif table == "transcript_messages":
            row = self.con.execute(
                "SELECT COUNT(*) FROM transcript_messages"
            ).fetchone()
        elif table == "daily":
            row = self.con.execute("SELECT COUNT(*) FROM daily").fetchone()
        else:
            raise KeyError(table)
        return int(row[0])


class ReadingTest(TranscriptCase):
    def test_a_response_written_three_times_counts_once(self):
        path = self.transcript()
        shared = record("msg_1", tin=1000, tout=200)
        self.write(path, [shared, shared, shared])
        result = self.reader.harvest(self.con)
        self.assertEqual(result.sessions, 1)
        self.assertEqual(self.count("transcript_messages"), 1)
        self.assertEqual(self.session_row()["tokens_input"], 1000)
        self.assertEqual(self.session_row()["tokens_output"], 200)

    def test_tokens_cover_every_kind(self):
        path = self.transcript()
        self.write(path, [record("msg_1", tin=10, tcw=20, tcr=30, tout=40, thinking=5)])
        self.reader.harvest(self.con)
        row = self.session_row()
        self.assertEqual(row["tokens_input"], 10)
        self.assertEqual(row["tokens_cache_write"], 20)
        self.assertEqual(row["tokens_cache_read"], 30)
        self.assertEqual(row["tokens_output"], 40)
        self.assertEqual(row["tokens_reasoning"], 5)

    def test_a_subagent_transcript_lands_on_its_parent_session(self):
        parent = self.transcript(session="s1")
        self.write(parent, [record("msg_parent", session="s1", tin=100)])
        # Subagent records carry no sessionId here, so the layout has to decide.
        sub = self.subagent(session="s1")
        self.write(sub, [record("msg_sub", tin=900, with_session=False)])

        self.reader.harvest(self.con)
        self.assertEqual(self.count("sessions"), 1)
        row = self.session_row()
        self.assertEqual(row["tokens_input"], 1000)
        self.assertEqual(row["turns"], 2)

    def test_model_project_and_entrypoint_come_from_the_transcript(self):
        path = self.transcript()
        self.write(
            path, [record("msg_1", model="claude-opus-5-5", cwd="/home/u/alpha")]
        )
        self.reader.harvest(self.con)
        row = self.session_row()
        self.assertEqual(row["model"], "claude-opus-5-5")
        self.assertEqual(row["model_family"], "claude-opus-5")
        self.assertEqual(row["project"], "alpha")
        self.assertEqual(json.loads(row["meta"])["entrypoint"], "cli")

    def test_duration_spans_first_to_last_message(self):
        path = self.transcript()
        self.write(
            path,
            [
                record("msg_1", ts="2026-10-01T10:00:00.000Z"),
                record("msg_2", ts="2026-10-01T10:30:00.000Z"),
            ],
        )
        self.reader.harvest(self.con)
        self.assertEqual(self.session_row()["duration_s"], 1800)

    def test_records_without_usage_are_ignored(self):
        path = self.transcript()
        self.write(
            path,
            [
                {"type": "user", "sessionId": "s1", "message": {"content": "hi"}},
                {
                    "type": "assistant",
                    "sessionId": "s1",
                    "message": {"id": "m", "content": []},
                },
                record("msg_1"),
            ],
        )
        self.reader.harvest(self.con)
        self.assertEqual(self.count("transcript_messages"), 1)

    def test_rollups_are_built(self):
        self.write(self.transcript(), [record("msg_1")])
        self.reader.harvest(self.con)
        self.assertEqual(self.count("daily"), 1)


class IncrementTest(TranscriptCase):
    def test_a_second_harvest_of_an_unchanged_store_changes_nothing(self):
        self.write(self.transcript(), [record("msg_1")])
        self.assertEqual(self.reader.harvest(self.con).sessions, 1)
        second = self.reader.harvest(self.con)
        self.assertEqual(second.scanned, 0)
        self.assertEqual(second.sessions, 0)

    def test_an_appended_record_is_picked_up_without_rereading(self):
        path = self.transcript()
        self.write(path, [record("msg_1", tin=100)])
        self.reader.harvest(self.con)

        self.write(path, [record("msg_1", tin=100), record("msg_2", tin=50)])
        result = self.reader.harvest(self.con)
        self.assertEqual(result.scanned, 1)
        self.assertEqual(self.session_row()["tokens_input"], 150)

    def test_a_partial_trailing_line_is_left_for_next_time(self):
        path = self.transcript()
        good = json.dumps(record("msg_1", tin=100))
        path.write_text(good + "\n" + json.dumps(record("msg_2", tin=50))[:40])

        self.reader.harvest(self.con)
        self.assertEqual(self.count("transcript_messages"), 1)

        # Completing the line makes it readable; nothing before it is re-read.
        self.write(path, [record("msg_1", tin=100), record("msg_2", tin=50)])
        result = self.reader.harvest(self.con)
        self.assertEqual(result.scanned, 1)
        self.assertEqual(self.session_row()["tokens_input"], 150)

    def test_a_file_read_again_does_not_double_count(self):
        path = self.transcript()
        self.write(path, [record("msg_1", tin=100)])
        self.reader.harvest(self.con)
        # A rotation that leaves the file smaller sends the reader back to zero.
        path.write_text("")
        self.write(path, [record("msg_1", tin=100)])
        result = self.reader.harvest(self.con)
        self.assertEqual(self.session_row()["tokens_input"], 100)
        self.assertEqual(result.sessions, 0)

    def test_full_ignores_offsets_and_still_changes_nothing(self):
        self.write(self.transcript(), [record("msg_1")])
        self.reader.harvest(self.con)
        result = self.reader.harvest(self.con, full=True)
        self.assertEqual(result.scanned, 1)
        self.assertEqual(result.sessions, 0)


class RobustnessTest(TranscriptCase):
    def test_a_missing_root_is_a_note_not_a_failure(self):
        reader = ClaudeTranscriptHarvester(self.root / "nope")
        self.assertFalse(reader.available())
        result = reader.harvest(self.con)
        self.assertFalse(result.failed)
        self.assertEqual(result.note, "no transcripts")

    def test_malformed_lines_are_skipped(self):
        path = self.transcript()
        path.write_text("{not json\n" + json.dumps(record("msg_1")) + "\n[]\n")
        self.reader.harvest(self.con)
        self.assertEqual(self.count("transcript_messages"), 1)

    def test_an_unparsable_timestamp_does_not_lose_the_tokens(self):
        path = self.transcript()
        self.write(path, [record("msg_1", ts="whenever", tin=42)])
        self.reader.harvest(self.con)
        row = self.session_row()
        self.assertEqual(row["tokens_input"], 42)
        self.assertIsNone(row["started_at"])

    def test_pruning_drops_a_whole_old_session_but_keeps_a_recent_one(self):
        old = record("msg_old", session="old", ts="2020-01-01T10:00:00.000Z")
        recent = record("msg_new", session="new", ts="2030-01-01T10:00:00.000Z")
        self.write(self.transcript(session="old"), [old])
        self.write(self.transcript(session="new"), [recent])
        self.reader.harvest(self.con)

        removed = ledger.prune(self.con, keep_days=90)
        self.assertEqual(removed["transcript_messages"], 1)
        self.assertEqual(self.count("transcript_messages"), 1)


if __name__ == "__main__":
    unittest.main()
