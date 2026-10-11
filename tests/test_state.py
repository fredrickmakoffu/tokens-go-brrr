"""Tests for reading published state and rendering it as JSON or a template."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from tokens_go_brrr import config as config_module
from tokens_go_brrr import state
from tokens_go_brrr.cli import app as cli
from tokens_go_brrr.config import MonitorConfig


def tool_dict(
    provider_id: str = "claude",
    *,
    value: int = 42,
    status: str = "ok",
    borrowed: bool = False,
    active: int = 0,
) -> dict:
    tool = {
        "id": provider_id,
        "name": "Claude Code",
        "icon": provider_id,
        "plan": "Max",
        "primary": "five_hour",
        "status": status,
        "error": None if status == "ok" else "Sign in to Claude Code",
        "dashboardUrl": "https://claude.ai/settings/usage",
        "instances": {
            "active": active,
            "suspended": 0,
            "projects": ["monorepo"] if active else [],
            "suspendedProjects": [],
            "sessions": [],
        },
        "via": None,
        "metrics": [
            {
                "key": "five_hour",
                "label": "5-hour limit",
                "value": value,
                "resets": "in 2h",
            },
            {"key": "seven_day", "label": "Weekly", "value": 12, "resets": "in 4 days"},
        ],
    }
    if borrowed:
        tool["via"] = {"name": "OpenCode Go", "borrowed": True, "from": "opencode"}
    return tool


def payload_dict(tools: list[dict] | None = None, *, age_seconds: float = 0) -> dict:
    stamp = datetime.now(UTC) - timedelta(seconds=age_seconds)
    return {
        "schema": state.SCHEMA_VERSION,
        "version": "0.4.0",
        "updated_at": stamp.isoformat(),
        "error": None,
        "tools": tools if tools is not None else [tool_dict()],
    }


class StateFileTest(unittest.TestCase):
    """read_state only hands back state a caller should still believe."""

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.path = Path(self._dir.name) / "state.json"
        patcher = mock.patch.object(config_module, "STATE_FILE", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.config = MonitorConfig()

    def write(self, payload: dict) -> None:
        self.path.write_text(json.dumps(payload))

    def test_missing_file_reads_as_no_state(self):
        self.assertIsNone(state.read_state(self.config))

    def test_fresh_state_is_returned(self):
        self.write(payload_dict())
        result = state.read_state(self.config)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["tools"][0]["id"], "claude")

    def test_state_older_than_two_polls_is_stale(self):
        # A daemon that stopped publishing leaves its last payload behind; the
        # numbers in it are no longer worth reporting as current.
        self.write(payload_dict(age_seconds=state.max_age_for(self.config) + 60))
        self.assertIsNone(state.read_state(self.config))

    def test_state_within_the_grace_window_is_kept(self):
        self.write(payload_dict(age_seconds=state.max_age_for(self.config) - 10))
        self.assertIsNotNone(state.read_state(self.config))

    def test_corrupt_json_reads_as_no_state(self):
        self.path.write_text("{not json")
        self.assertIsNone(state.read_state(self.config))

    def test_payload_without_tools_is_rejected(self):
        self.write({"schema": 1, "version": "0.4.0", "updated_at": None})
        self.assertIsNone(state.read_state(self.config))

    def test_missing_timestamp_falls_back_to_file_mtime(self):
        payload = payload_dict()
        payload["updated_at"] = None
        self.write(payload)
        self.assertIsNotNone(state.read_state(self.config))

    def test_max_age_follows_the_configured_poll_interval(self):
        slow = MonitorConfig(poll_interval_seconds=900)
        self.assertGreater(state.max_age_for(slow), state.max_age_for(MonitorConfig()))

    def test_state_from_a_daemon_predating_the_schema_key_is_stamped(self):
        payload = payload_dict()
        del payload["schema"]
        self.write(payload)
        stamped = state.read_state(self.config)
        self.assertIsNotNone(stamped)
        assert stamped is not None
        self.assertEqual(stamped["schema"], state.SCHEMA_VERSION)

    def test_max_age_respects_the_daemons_minimum_interval(self):
        # The daemon clamps its timer to 60s, so a smaller configured interval
        # must not make us call its output stale early.
        eager = MonitorConfig(poll_interval_seconds=5)
        self.assertEqual(state.max_age_for(eager), 2 * 60 + state.STALE_GRACE_SECONDS)


class PayloadReadingTest(unittest.TestCase):
    def test_primary_metric_follows_a_chip_swap(self):
        tool = tool_dict()
        tool["primary"] = "seven_day"
        self.assertEqual(state.primary_metric(tool)["label"], "Weekly")

    def test_primary_metric_falls_back_to_the_first(self):
        tool = tool_dict()
        tool["primary"] = "gone"
        self.assertEqual(state.primary_metric(tool)["key"], "five_hour")

    def test_primary_metric_survives_a_tool_with_no_metrics(self):
        self.assertEqual(state.primary_metric({})["value"], 0)

    def test_header_names_the_backend_for_a_harness(self):
        self.assertEqual(state.header_of(tool_dict(borrowed=True)), "Claude Code · via OpenCode Go")

    def test_header_uses_the_plan_otherwise(self):
        self.assertEqual(state.header_of(tool_dict()), "Claude Code · Max")

    def test_borrowed_rows_do_not_own_their_meters(self):
        self.assertFalse(state.owns_meters(tool_dict(borrowed=True)))
        self.assertTrue(state.owns_meters(tool_dict()))


class StatusCommandTest(unittest.TestCase):
    """The CLI renders whatever payload it was handed, and never double-fetches."""

    def setUp(self) -> None:
        self.config = MonitorConfig(enabled_providers=["claude"])
        patcher = mock.patch.object(MonitorConfig, "load", return_value=self.config)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_status(self, argv: list[str], payload: dict | None = None):
        given = payload if payload is not None else payload_dict()
        given = dict(given)
        given.setdefault("source", "daemon")
        with mock.patch.object(cli, "_load_payload", return_value=given) as loader:
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = cli.main(["status", *argv])
        return code, out.getvalue(), err.getvalue(), loader

    def test_json_output_parses_and_carries_the_schema(self):
        code, out, _, _ = self.run_status(["--json"])
        parsed = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(parsed["schema"], state.SCHEMA_VERSION)
        self.assertEqual(parsed["tools"][0]["metrics"][0]["value"], 42)

    def test_compact_json_is_one_line(self):
        _, out, _, _ = self.run_status(["--json", "--compact"])
        self.assertEqual(len(out.strip().splitlines()), 1)

    def test_format_renders_the_primary_meter(self):
        _, out, _, _ = self.run_status(["--format", "{icon} {pct}%"])
        self.assertEqual(out.strip(), "claude 42%")

    def test_format_joins_providers_with_the_separator(self):
        payload = payload_dict([tool_dict("claude"), tool_dict("opencode", value=7)])
        _, out, _, _ = self.run_status(["--format", "{pct}", "--separator", " | "], payload)
        self.assertEqual(out.strip(), "42 | 7")

    def test_format_shows_a_dash_rather_than_zero_when_not_ok(self):
        # 0% would read as "plenty left" for a provider we could not reach.
        payload = payload_dict([tool_dict(status="auth_needed")])
        _, out, _, _ = self.run_status(["--format", "{pct}"], payload)
        self.assertEqual(out.strip(), "—")

    def test_a_harness_with_no_meters_shows_a_dash_not_zero(self):
        # Pi on an unmeterable backend is status ok with nothing to measure.
        tool = tool_dict("pi")
        tool["metrics"] = []
        tool["error"] = "xAI reports no limits"
        _, out, _, _ = self.run_status(["--format", "{pct}"], payload_dict([tool]))
        self.assertEqual(out.strip(), "—")

    def test_text_output_says_why_a_row_has_no_meters(self):
        tool = tool_dict("pi")
        tool["metrics"] = []
        tool["error"] = "xAI reports no limits"
        _, out, _, _ = self.run_status([], payload_dict([tool]))
        self.assertIn("xAI reports no limits", out)

    def test_unknown_format_field_explains_itself(self):
        with self.assertRaises(SystemExit) as caught:
            self.run_status(["--format", "{nope}"])
        self.assertIn("Available fields", str(caught.exception))

    def test_provider_filter_selects_one_row(self):
        payload = payload_dict([tool_dict("claude"), tool_dict("opencode", value=7)])
        _, out, _, _ = self.run_status(["--format", "{id}", "--provider", "opencode"], payload)
        self.assertEqual(out.strip(), "opencode")

    def test_unmatched_provider_filter_is_its_own_exit_code(self):
        code, _, err, _ = self.run_status(["--provider", "ghost"])
        self.assertEqual(code, 2)
        self.assertIn("Enabled: claude", err)

    def test_exit_code_reports_a_provider_that_is_not_ok(self):
        payload = payload_dict([tool_dict(status="auth_needed")])
        code, out, _, _ = self.run_status([], payload)
        self.assertEqual(code, 1)
        self.assertIn("Sign in to Claude Code", out)

    def test_text_output_marks_the_primary_and_lists_sessions(self):
        payload = payload_dict([tool_dict(active=2)])
        _, out, _, _ = self.run_status([], payload)
        self.assertIn("★ 5-hour limit", out)
        self.assertIn("2 running (monorepo)", out)

    def test_text_output_says_when_sessions_were_not_scanned(self):
        payload = dict(payload_dict())
        payload["source"] = "live"
        _, out, _, _ = self.run_status([], payload)
        self.assertIn("daemon not running", out)


class DaemonPayloadTest(unittest.TestCase):
    """The daemon publishes the same shape the CLI prints."""

    def test_daemon_state_payload_carries_the_schema_and_tools(self):
        from tokens_go_brrr.daemon import UsageDaemon

        snapshot = mock.Mock()
        snapshot.to_panel_dict.return_value = tool_dict()
        stub = mock.Mock(
            snapshots=[snapshot],
            last_fetch=datetime.now(UTC),
            last_error=None,
            _billboard=None,
            _latest_message=None,
            _recent_messages=[],
            config=MonitorConfig(enabled_providers=["claude", "cursor"]),
        )

        payload = UsageDaemon.state_payload(stub)

        self.assertEqual(payload["schema"], state.SCHEMA_VERSION)
        self.assertEqual(payload["tools"][0]["id"], "claude")
        self.assertIsNotNone(payload["updated_at"])
        self.assertEqual(len(payload["catalog"]), 5)
        by_id = {entry["id"]: entry for entry in payload["catalog"]}
        self.assertTrue(by_id["claude"]["enabled"])
        self.assertFalse(by_id["codex"]["enabled"])

    def test_daemon_payload_without_a_fetch_yet_has_no_timestamp(self):
        from tokens_go_brrr.daemon import UsageDaemon

        stub = mock.Mock(
            snapshots=[],
            last_fetch=None,
            last_error=None,
            _billboard=None,
            _latest_message=None,
            _recent_messages=[],
            config=MonitorConfig(),
        )
        self.assertIsNone(UsageDaemon.state_payload(stub)["updated_at"])


class PayloadSourceTest(unittest.TestCase):
    """Published state is preferred; fetching is the fallback, not the default."""

    def setUp(self) -> None:
        self.config = MonitorConfig(enabled_providers=["claude"])

    def test_fresh_state_is_used_without_fetching(self):
        with (
            mock.patch.object(cli, "read_state", return_value=payload_dict()),
            mock.patch.object(cli, "_live_payload") as fetch,
        ):
            payload = cli._load_payload(self.config, live=False)
        fetch.assert_not_called()
        self.assertEqual(payload["source"], "daemon")

    def test_no_state_falls_back_to_fetching(self):
        with (
            mock.patch.object(cli, "read_state", return_value=None),
            mock.patch.object(cli, "_live_payload", return_value=payload_dict()),
        ):
            payload = cli._load_payload(self.config, live=False)
        self.assertEqual(payload["source"], "live")

    def test_live_flag_skips_published_state(self):
        with (
            mock.patch.object(cli, "read_state") as reader,
            mock.patch.object(cli, "_live_payload", return_value=payload_dict()),
        ):
            payload = cli._load_payload(self.config, live=True)
        reader.assert_not_called()
        self.assertEqual(payload["source"], "live")


if __name__ == "__main__":
    unittest.main()


class RefreshCooldownTest(unittest.TestCase):
    """A refresh on every menu open must not become a request on every open."""

    def _daemon(self, last_fetch):
        from tokens_go_brrr.daemon import UsageDaemon

        stub = mock.Mock(spec=UsageDaemon)
        stub._polling = False
        stub.last_fetch = last_fetch
        return stub

    def poll(self, stub, **kwargs):
        from tokens_go_brrr.daemon import UsageDaemon

        with mock.patch("tokens_go_brrr.daemon.threading.Thread") as thread:
            UsageDaemon.poll(stub, **kwargs)
        return thread.called

    def test_a_first_poll_always_runs(self):
        self.assertTrue(self.poll(self._daemon(None)))

    def test_a_second_poll_inside_the_cooldown_is_dropped(self):
        just_now = datetime.now(UTC) - timedelta(seconds=5)
        self.assertFalse(self.poll(self._daemon(just_now)))

    def test_a_poll_after_the_cooldown_runs(self):
        from tokens_go_brrr.daemon import REFRESH_COOLDOWN_SECONDS

        stale = datetime.now(UTC) - timedelta(seconds=REFRESH_COOLDOWN_SECONDS + 5)
        self.assertTrue(self.poll(self._daemon(stale)))

    def test_force_ignores_the_cooldown(self):
        # The scheduled tick is already spaced by the poll interval.
        just_now = datetime.now(UTC) - timedelta(seconds=5)
        self.assertTrue(self.poll(self._daemon(just_now), force=True))

    def test_a_poll_already_in_flight_is_never_doubled(self):
        stub = self._daemon(None)
        stub._polling = True
        self.assertFalse(self.poll(stub))

    def test_force_does_not_override_a_poll_in_flight(self):
        stub = self._daemon(None)
        stub._polling = True
        self.assertFalse(self.poll(stub, force=True))


class DaemonStartupTest(unittest.TestCase):
    """Startup idle callbacks must fire once, not forever.

    `GLib.idle_add` re-schedules any callback that returns True. The scan and
    harvest functions return True because their own timers need them to stay
    scheduled, so queueing them as idle callbacks directly spun the main loop
    at idle priority and pegged a CPU core — 6h24m of CPU in 6h30m of wall time
    before it was found.
    """

    def test_the_startup_scan_removes_its_idle_source(self):
        from tokens_go_brrr.daemon import UsageDaemon

        stub = mock.Mock()
        self.assertFalse(UsageDaemon._startup_scan(stub))
        stub._scan_instances.assert_called_once_with()

    def test_the_startup_harvest_removes_its_idle_source(self):
        from tokens_go_brrr.daemon import UsageDaemon

        stub = mock.Mock()
        self.assertFalse(UsageDaemon._startup_harvest(stub))
        stub._harvest_tick.assert_called_once_with()
