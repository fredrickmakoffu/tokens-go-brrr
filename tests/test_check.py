"""Tests for the scriptable commands: `check` exit codes and `best` ranking."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from cursor_spend_monitor import __main__ as cli
from cursor_spend_monitor.config import MonitorConfig
from tests.test_state import payload_dict, tool_dict


def run(argv: list[str], tools: list[dict]):
    payload = dict(payload_dict(tools))
    payload["source"] = "daemon"
    config = MonitorConfig(enabled_providers=[t["id"] for t in tools])
    with (
        mock.patch.object(MonitorConfig, "load", return_value=config),
        mock.patch.object(cli, "_load_payload", return_value=payload),
    ):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def borrowed(provider_id: str = "pi", *, value: int = 80) -> dict:
    tool = tool_dict(provider_id, value=value, borrowed=True)
    tool["name"] = "Pi"
    return tool


class CheckExitCodeTest(unittest.TestCase):
    """The exit code is the product here, so each meaning gets its own code."""

    def test_headroom_passes(self):
        code, out, _ = run(["check", "--min", "20"], [tool_dict(value=40)])
        self.assertEqual(code, 0)
        self.assertIn("60% left", out)

    def test_below_the_threshold_fails(self):
        code, _, _ = run(["check", "--min", "20"], [tool_dict(value=95)])
        self.assertEqual(code, 1)

    def test_exactly_at_the_threshold_passes(self):
        code, _, _ = run(["check", "--min", "20"], [tool_dict(value=80)])
        self.assertEqual(code, 0)

    def test_every_provider_must_pass_by_default(self):
        tools = [tool_dict("claude", value=10), tool_dict("opencode", value=95)]
        self.assertEqual(run(["check", "--min", "20"], tools)[0], 1)

    def test_any_passes_when_one_has_room(self):
        tools = [tool_dict("claude", value=10), tool_dict("opencode", value=95)]
        self.assertEqual(run(["check", "--min", "20", "--any"], tools)[0], 0)

    def test_nothing_measurable_is_its_own_exit_code(self):
        # A stale login must not silently green-light a long run, nor fail a
        # build that had nothing to do with quota.
        code, _, err = run(["check"], [tool_dict(status="auth_needed")])
        self.assertEqual(code, 2)
        self.assertIn("No usable meters", err)

    def test_an_unreadable_provider_is_skipped_not_failed(self):
        tools = [tool_dict("claude", value=10), tool_dict("codex", status="auth_needed")]
        code, out, _ = run(["check", "--min", "20"], tools)
        self.assertEqual(code, 0)
        self.assertIn("Sign in to Claude Code", out)

    def test_fail_on_unknown_turns_a_skip_into_a_failure(self):
        tools = [tool_dict("claude", value=10), tool_dict("codex", status="auth_needed")]
        code, _, _ = run(["check", "--min", "20", "--fail-on-unknown"], tools)
        self.assertEqual(code, 2)

    def test_quiet_prints_nothing(self):
        code, out, _ = run(["check", "--min", "20", "--quiet"], [tool_dict(value=40)])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_provider_filter_narrows_the_check(self):
        tools = [tool_dict("claude", value=10), tool_dict("opencode", value=95)]
        code, _, _ = run(["check", "--min", "20", "--provider", "claude"], tools)
        self.assertEqual(code, 0)

    def test_unmatched_provider_filter_cannot_pass(self):
        code, _, err = run(["check", "--provider", "ghost"], [tool_dict()])
        self.assertEqual(code, 2)
        self.assertIn("No provider matched", err)

    def test_a_borrowed_row_does_not_vote(self):
        # Pi and OpenCode are one subscription; counting both would let it
        # decide the answer twice.
        tools = [tool_dict("opencode", value=95), borrowed(value=95)]
        code, out, _ = run(["check", "--min", "20", "--any"], tools)
        self.assertEqual(code, 1)
        self.assertIn("counted under opencode", out)

    def test_the_eta_is_shown_when_history_has_one(self):
        tool = tool_dict(value=40)
        tool["metrics"][0]["eta"] = "38m"
        code, out, _ = run(["check", "--min", "20"], [tool])
        self.assertEqual(code, 0)
        self.assertIn("spent in 38m", out)


class BestTest(unittest.TestCase):
    def test_names_the_id_with_the_most_headroom(self):
        tools = [tool_dict("claude", value=90), tool_dict("opencode", value=30)]
        code, out, _ = run(["best"], tools)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "opencode")

    def test_explain_compares_the_rest_in_the_same_terms(self):
        tools = [tool_dict("claude", value=90), tool_dict("opencode", value=30)]
        _, out, _ = run(["best", "--explain"], tools)
        self.assertIn("70% left", out)
        self.assertIn("Claude Code 10% left", out)

    def test_a_borrowed_row_is_never_the_recommendation(self):
        # Pi ties OpenCode because it is showing OpenCode's meters. Recommending
        # the harness would send the user to the account that is already busy.
        tools = [borrowed(value=90), tool_dict("opencode", value=90)]
        code, out, _ = run(["best"], tools)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "opencode")

    def test_only_borrowed_rows_means_nothing_to_recommend(self):
        code, _, err = run(["best"], [borrowed(value=40)])
        self.assertEqual(code, 2)
        self.assertIn("No provider is reporting", err)

    def test_a_signed_out_provider_is_not_recommended(self):
        tools = [tool_dict("claude", value=90), tool_dict("codex", status="auth_needed")]
        _, out, _ = run(["best"], tools)
        self.assertEqual(out.strip(), "claude")

    def test_nothing_measurable_exits_two(self):
        code, _, _ = run(["best"], [tool_dict(status="auth_needed")])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
