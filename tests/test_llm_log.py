"""Tests for the daily LLM call log and for what the composer hands it.

The log is a transparency feature, so the properties worth pinning are the ones
a person would be upset to find broken: every call is there (failures too), a
day is its own file in time order, nothing credential-shaped is written, a
log that cannot be written never breaks a call, and retention really deletes.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from tokens_go_brrr import llm_composer as llm
from tokens_go_brrr.llm_log import LlmLog
from tokens_go_brrr.notify_engine import INFORMATIVE, Message

AT = datetime(2026, 10, 10, 9, 30).astimezone()


class LogCase(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.root = Path(self._dir.name) / "llm-calls"
        self.log = LlmLog(self.root, keep_days=30)


class WritingTest(LogCase):
    def test_an_entry_lands_in_its_days_file_led_by_a_timestamp(self):
        self.log.record({"provider": "claude", "outcome": "ok"}, at=AT)
        files = list(self.root.glob("*.jsonl"))
        self.assertEqual([f.name for f in files], ["2026-10-10.jsonl"])
        line = json.loads(files[0].read_text().splitlines()[0])
        self.assertEqual(next(iter(line)), "ts")
        self.assertTrue(line["ts"].startswith("2026-10-10T09:30:00"))

    def test_entries_stay_in_time_order_within_a_day(self):
        for minute in (5, 1, 9):
            self.log.record(
                {"n": minute}, at=AT.replace(hour=10, minute=minute)
            )
        # Append order is the order they happened in, not a sort by value.
        self.assertEqual([e["n"] for e in self.log.read("2026-10-10")], [5, 1, 9])

    def test_a_new_day_is_a_new_file(self):
        self.log.record({"a": 1}, at=AT)
        self.log.record({"a": 2}, at=AT + timedelta(days=1))
        self.assertEqual(self.log.days(), ["2026-10-11", "2026-10-10"])

    def test_the_files_are_private(self):
        self.log.record({"a": 1}, at=AT)
        path = next(self.root.glob("*.jsonl"))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_a_credential_in_an_error_is_removed(self):
        self.log.record(
            {
                "outcome": "error",
                "error": "LlmError: 401 Bearer sk-ant-oat01-abcdef123456 rejected",
            },
            at=AT,
        )
        text = next(self.root.glob("*.jsonl")).read_text()
        self.assertNotIn("sk-ant", text)
        self.assertNotIn("abcdef123456", text)
        self.assertIn("[redacted]", text)

    def test_a_log_that_cannot_be_written_does_not_raise(self):
        self.root.parent.mkdir(parents=True, exist_ok=True)
        self.root.write_text("a file where the directory should be")
        self.log.record({"a": 1}, at=AT)  # must not raise

    def test_a_value_that_cannot_be_encoded_does_not_raise(self):
        self.log.record({"bad": object()}, at=AT)
        self.assertEqual(self.log.days(), [])

    def test_a_disabled_log_writes_nothing(self):
        off = LlmLog(self.root, keep_days=0)
        off.record({"a": 1}, at=AT)
        self.assertFalse(off.enabled)
        self.assertFalse(self.root.exists())


class ReadingTest(LogCase):
    def test_a_torn_last_line_is_skipped(self):
        self.log.record({"a": 1}, at=AT)
        path = next(self.root.glob("*.jsonl"))
        with open(path, "a") as handle:
            handle.write('{"ts": "half')
        self.assertEqual(len(self.log.read("2026-10-10")), 1)

    def test_a_day_that_is_not_a_date_reads_as_empty(self):
        self.assertEqual(self.log.read("../../etc/passwd"), [])
        self.assertEqual(self.log.read(""), [])

    def test_the_summary_counts_calls_failures_and_tokens(self):
        for entry in (
            {"outcome": "ok", "tokens_in": 100, "tokens_out": 20},
            {"outcome": "ok", "tokens_in": 50, "tokens_out": 10},
            {"outcome": "rate_limited"},
            {"outcome": "skipped", "reason": "no_generator"},
        ):
            self.log.record(entry, at=AT)
        summary = self.log.summary("2026-10-10")
        self.assertEqual(summary["calls"], 3)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["failures"], 1)
        self.assertEqual(summary["tokens_in"], 150)
        self.assertEqual(summary["tokens_out"], 30)

    def test_the_payload_defaults_to_the_newest_day(self):
        self.log.record({"a": 1}, at=AT)
        self.log.record({"a": 2}, at=AT + timedelta(days=1))
        payload = self.log.payload()
        self.assertEqual(payload["day"], "2026-10-11")
        self.assertEqual(payload["entries"][0]["a"], 2)
        self.assertEqual(self.log.payload("2026-10-10")["entries"][0]["a"], 1)

    def test_an_empty_log_has_a_payload_with_no_day(self):
        payload = self.log.payload()
        self.assertEqual(payload["days"], [])
        self.assertEqual(payload["day"], "")
        self.assertIsNone(payload["summary"])
        self.assertTrue(payload["enabled"])


class RetentionTest(LogCase):
    def test_prune_removes_days_older_than_the_window(self):
        for back in (0, 1, 29, 30, 45):
            self.log.record({"a": back}, at=AT - timedelta(days=back))
        removed = self.log.prune(today=AT)
        self.assertEqual(removed, 2)
        self.assertEqual(len(self.log.days()), 3)
        self.assertNotIn("2026-09-10", self.log.days())

    def test_clear_removes_everything(self):
        self.log.record({"a": 1}, at=AT)
        self.log.record({"a": 2}, at=AT + timedelta(days=1))
        self.assertEqual(self.log.clear(), 2)
        self.assertEqual(self.log.days(), [])


def generator(provider: str = "claude") -> llm.Generator:
    return llm.Generator(
        provider_id=provider,
        name=provider.title(),
        model="a-cheap-model",
        short_headroom=50,
        monthly_headroom=None,
        reason="test",
    )


class ComposerRecordingTest(unittest.TestCase):
    def call(self, response=None, error=None, **kwargs):
        seen: list[dict] = []
        patches = [
            mock.patch.object(llm, "_claude_token", return_value="tok-secret-1234"),
        ]
        if error is not None:
            patches.append(mock.patch.object(llm, "_post_json", side_effect=error))
        else:
            patches.append(mock.patch.object(llm, "_post_json", return_value=response))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        try:
            text = llm.generate(
                generator(), "the prompt", recorder=seen.append, **kwargs
            )
        except llm.LlmError:
            text = None
        return text, seen

    def test_a_good_call_is_recorded_with_its_reply_and_tokens(self):
        response = {
            "content": [{"type": "text", "text": "Hello."}],
            "usage": {"input_tokens": 42, "output_tokens": 7},
        }
        text, seen = self.call(response, context={"trigger": "scheduled:daily"})
        self.assertEqual(text, "Hello.")
        (entry,) = seen
        self.assertEqual(entry["outcome"], "ok")
        self.assertEqual(entry["trigger"], "scheduled:daily")
        self.assertEqual(entry["provider"], "claude")
        self.assertEqual(entry["model"], "a-cheap-model")
        self.assertEqual(entry["prompt"], "the prompt")
        self.assertEqual(entry["reply"], "Hello.")
        self.assertEqual((entry["tokens_in"], entry["tokens_out"]), (42, 7))
        self.assertGreaterEqual(entry["latency_ms"], 0)

    def test_an_openai_shaped_usage_block_is_read(self):
        response = {
            "choices": [{"message": {"content": "Hi."}}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 3},
        }
        seen: list[dict] = []
        with (
            mock.patch.object(llm, "_opencode_key", return_value="k"),
            mock.patch.object(llm, "_post_json", return_value=response),
        ):
            llm.generate(generator("opencode"), "p", recorder=seen.append)
        self.assertEqual((seen[0]["tokens_in"], seen[0]["tokens_out"]), (9, 3))

    def test_a_rate_limit_is_recorded_and_still_raised(self):
        with (
            mock.patch.object(llm, "_claude_token", return_value="t"),
            mock.patch.object(llm, "_post_json", side_effect=llm.LlmRateLimited("429")),
        ):
            seen: list[dict] = []
            with self.assertRaises(llm.LlmRateLimited):
                llm.generate(generator(), "p", recorder=seen.append)
        self.assertEqual(seen[0]["outcome"], "rate_limited")
        self.assertNotIn("reply", seen[0])

    def test_a_timeout_is_told_apart_from_other_errors(self):
        _, seen = self.call(error=llm.LlmError("host unreachable: timed out"))
        self.assertEqual(seen[0]["outcome"], "timeout")
        _, seen = self.call(error=llm.LlmError("HTTP 500 from host"))
        self.assertEqual(seen[0]["outcome"], "error")

    def test_a_missing_credential_is_recorded(self):
        seen: list[dict] = []
        with mock.patch.object(llm, "_claude_token", side_effect=llm.LlmError("none")):
            with self.assertRaises(llm.LlmError):
                llm.generate(generator(), "p", recorder=seen.append)
        self.assertEqual(seen[0]["outcome"], "error")

    def test_the_credential_never_reaches_the_entry(self):
        response = {"content": [{"type": "text", "text": "ok"}]}
        _, seen = self.call(response)
        self.assertNotIn("tok-secret-1234", json.dumps(seen))

    def test_a_recorder_that_raises_does_not_fail_the_call(self):
        response = {"content": [{"type": "text", "text": "Fine."}]}

        def boom(_entry):
            raise RuntimeError("disk full")

        with (
            mock.patch.object(llm, "_claude_token", return_value="t"),
            mock.patch.object(llm, "_post_json", return_value=response),
        ):
            self.assertEqual(llm.generate(generator(), "p", recorder=boom), "Fine.")

    def test_no_recorder_means_the_old_behaviour(self):
        response = {"content": [{"type": "text", "text": "Plain."}]}
        with (
            mock.patch.object(llm, "_claude_token", return_value="t"),
            mock.patch.object(llm, "_post_json", return_value=response),
        ):
            self.assertEqual(llm.generate(generator(), "p"), "Plain.")

    def test_rewrite_tags_the_entry_with_the_message_it_was_for(self):
        response = {"content": [{"type": "text", "text": "New body."}]}
        seen: list[dict] = []
        message = Message(kind=INFORMATIVE, key="daily:2026-10-10", body="x")
        with (
            mock.patch.object(llm, "_claude_token", return_value="t"),
            mock.patch.object(llm, "_post_json", return_value=response),
        ):
            llm.rewrite(
                message,
                generator=generator(),
                facts={"ranked": []},
                recorder=seen.append,
                context={"trigger": "scheduled:daily"},
            )
        self.assertEqual(seen[0]["message_kind"], INFORMATIVE)
        self.assertEqual(seen[0]["message_key"], "daily:2026-10-10")
        self.assertEqual(seen[0]["trigger"], "scheduled:daily")


class ConfigTest(unittest.TestCase):
    def test_the_retention_defaults_to_thirty_days(self):
        from tokens_go_brrr.config import MonitorConfig

        self.assertEqual(MonitorConfig().llm_log_days, 30)


if __name__ == "__main__":
    unittest.main()


class ReportTest(LogCase):
    def test_the_report_lists_every_day_with_model_tokens_and_time(self):
        self.log.record(
            {
                "provider": "claude",
                "model": "haiku",
                "outcome": "ok",
                "trigger": "warm",
                "latency_ms": 1200,
                "tokens_in": 1500,
                "tokens_out": 40,
                "prompt": "p",
                "reply": "r",
            },
            at=AT,
        )
        self.log.record({"outcome": "error", "error": "boom"}, at=AT - timedelta(days=1))
        path = self.log.write_report()
        text = path.read_text()
        self.assertEqual(path.parent, self.root.parent)
        for needle in ("2026-10-10", "2026-10-09", "09:30:00  OK", "haiku", "1,500", "1,200 ms", "boom"):
            self.assertIn(needle, text)
        self.assertLess(text.index("2026-10-10"), text.index("2026-10-09"))

    def test_an_empty_log_still_produces_a_document(self):
        self.assertIn("No model calls", self.log.report())
