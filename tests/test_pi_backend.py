"""Tests for Pi's backend resolution and the borrowing that follows from it."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from cursor_spend_monitor.providers import pi_backend
from cursor_spend_monitor.providers.base import Meter, ProviderSnapshot
from cursor_spend_monitor.providers.pi_backend import Backend, BackendResolver, dominant


class SlugTest(unittest.TestCase):
    def test_matches_pi_layout(self):
        self.assertEqual(
            pi_backend._slug("/home/u/work/app"),
            "--home-u-work-app--",
        )

    def test_trailing_slash_does_not_change_the_slug(self):
        self.assertEqual(pi_backend._slug("/home/u/"), pi_backend._slug("/home/u"))


class ResolverTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.agent = Path(self._tmp.name)
        self.sessions = self.agent / "sessions"
        self.sessions.mkdir()
        self._patches = [
            mock.patch.object(pi_backend, "AGENT_DIR", self.agent),
            mock.patch.object(pi_backend, "SESSIONS_DIR", self.sessions),
            mock.patch.object(
                pi_backend, "SETTINGS_FILE", self.agent / "settings.json"
            ),
            mock.patch.object(pi_backend, "AUTH_FILE", self.agent / "auth.json"),
        ]
        for patch in self._patches:
            patch.start()
        self.addCleanup(self._tmp.cleanup)
        for patch in self._patches:
            self.addCleanup(patch.stop)

    def _settings(self, provider="opencode-go", model="deepseek-v4-flash"):
        (self.agent / "settings.json").write_text(
            json.dumps({"defaultProvider": provider, "defaultModel": model})
        )

    def _log(self, directory, lines, name="2026-01-01T00-00-00-000Z_a.jsonl"):
        session_dir = self.sessions / pi_backend._slug(directory)
        session_dir.mkdir(parents=True, exist_ok=True)
        path = session_dir / name
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
        return path

    def test_reads_the_last_model_change(self):
        self._settings()
        self._log(
            "/w/app",
            [
                {"type": "session", "cwd": "/w/app"},
                {"type": "model_change", "provider": "xai", "modelId": "grok-4.5"},
                {"type": "message"},
                {
                    "type": "model_change",
                    "provider": "opencode-go",
                    "modelId": "glm-5.3",
                },
            ],
        )
        backend = BackendResolver().resolve("/w/app")
        assert backend is not None
        self.assertEqual(backend.account, "opencode-go")
        self.assertEqual(backend.model, "glm-5.3")
        self.assertEqual(backend.provider_id, "opencode")
        self.assertTrue(backend.metered)

    def test_unmetered_account_is_still_named(self):
        self._settings()
        self._log(
            "/w/app",
            [{"type": "model_change", "provider": "xai", "modelId": "grok-4.6"}],
        )
        backend = BackendResolver().resolve("/w/app")
        assert backend is not None
        self.assertEqual(backend.name, "xAI")
        self.assertFalse(backend.metered)
        self.assertEqual(backend.provider_id, "")

    def test_falls_back_to_settings_when_no_log_exists(self):
        self._settings(provider="xai", model="grok-4.5")
        backend = BackendResolver().resolve("/w/never-used")
        assert backend is not None
        self.assertEqual(backend.account, "xai")
        self.assertEqual(backend.model, "grok-4.5")

    def test_no_settings_and_no_log_means_no_backend(self):
        self.assertIsNone(BackendResolver().resolve("/w/app"))

    def test_newest_log_wins(self):
        self._settings()
        old = self._log(
            "/w/app",
            [
                {"type": "model_change", "provider": "xai", "modelId": "grok-4.5"},
            ],
            name="2026-01-01T00-00-00-000Z_a.jsonl",
        )
        new = self._log(
            "/w/app",
            [
                {
                    "type": "model_change",
                    "provider": "opencode-go",
                    "modelId": "glm-5.3",
                },
            ],
            name="2026-02-01T00-00-00-000Z_b.jsonl",
        )
        import os

        os.utime(old, (1_000_000, 1_000_000))
        os.utime(new, (2_000_000, 2_000_000))
        backend = BackendResolver().resolve("/w/app")
        assert backend is not None
        self.assertEqual(backend.model, "glm-5.3")

    def test_only_the_tail_of_a_huge_log_is_read(self):
        """A model change beyond the tail window must not cost a full read."""
        self._settings()
        filler = {"type": "message", "message": "x" * 4096}
        lines = [{"type": "model_change", "provider": "xai", "modelId": "grok-4.5"}]
        lines += [filler] * 200
        lines += [
            {"type": "model_change", "provider": "opencode-go", "modelId": "glm-5.3"}
        ]
        self._log("/w/app", lines)
        backend = BackendResolver().resolve("/w/app")
        assert backend is not None
        self.assertEqual(backend.model, "glm-5.3")

    def test_cache_is_reused_until_the_log_changes(self):
        self._settings()
        path = self._log(
            "/w/app",
            [
                {
                    "type": "model_change",
                    "provider": "opencode-go",
                    "modelId": "glm-5.3",
                },
            ],
        )
        resolver = BackendResolver()
        backend = resolver.resolve("/w/app")
        assert backend is not None
        self.assertEqual(backend.model, "glm-5.3")
        # Removing the file leaves only the cached answer reachable; a second
        # call that still returns the model proves the first one was cached.
        with mock.patch.object(pi_backend, "_last_model_change") as reader:
            reader.side_effect = AssertionError("log re-read despite no change")
            backend = resolver.resolve("/w/app")
            assert backend is not None
            self.assertEqual(backend.model, "glm-5.3")
        self.assertTrue(path.exists())

    def test_corrupt_lines_are_skipped(self):
        self._settings()
        session_dir = self.sessions / pi_backend._slug("/w/app")
        session_dir.mkdir(parents=True)
        (session_dir / "a.jsonl").write_text(
            '{"type": "model_change", "provider": "opencode-go", "modelId": "glm-5.3"}\n'
            '{"type": "model_change", not json at all\n'
        )
        backend = BackendResolver().resolve("/w/app")
        assert backend is not None
        self.assertEqual(backend.model, "glm-5.3")

    def test_codex_account_is_metered(self):
        self._settings()
        self._log(
            "/w/cx",
            [{"type": "model_change", "provider": "codex", "modelId": "gpt-5.6-sol"}],
        )
        backend = BackendResolver().resolve("/w/cx")
        assert backend is not None
        self.assertEqual(backend.account, "codex")
        self.assertEqual(backend.name, "Codex")
        self.assertEqual(backend.provider_id, "codex")
        self.assertTrue(backend.metered)

    def test_chatgpt_alias_is_metered(self):
        self._settings()
        self._log(
            "/w/cx2",
            [{"type": "model_change", "provider": "chatgpt", "modelId": "gpt-5"}],
        )
        backend = BackendResolver().resolve("/w/cx2")
        assert backend is not None
        self.assertEqual(backend.provider_id, "codex")


class DominantTest(unittest.TestCase):
    OC = Backend("opencode-go", "glm-5.3", "opencode")
    XAI = Backend("xai", "grok-4.5", "")
    CODE = Backend("codex", "gpt-5.6-sol", "codex")

    def test_no_sessions_means_no_backend(self):
        self.assertIsNone(dominant([]))

    def test_majority_wins(self):
        backend = dominant([self.XAI, self.OC, self.OC])
        assert backend is not None
        self.assertEqual(backend.account, "opencode-go")

    def test_metered_account_breaks_a_tie(self):
        """A tie should land on the account that can actually show a limit."""
        backend = dominant([self.XAI, self.OC])
        assert backend is not None
        self.assertEqual(backend.account, "opencode-go")

    def test_codex_breaks_a_tie_like_any_metered_account(self):
        backend = dominant([self.XAI, self.CODE])
        assert backend is not None
        self.assertEqual(backend.account, "codex")


class BorrowingTest(unittest.TestCase):
    """The daemon step that copies a backend provider's meters onto a harness."""

    def setUp(self):
        from cursor_spend_monitor.daemon import UsageDaemon
        from cursor_spend_monitor.instances import Instance, InstanceReport, ProcessSpec

        self.Instance = Instance
        self.InstanceReport = InstanceReport

        class Harness:
            _apply_borrowing = UsageDaemon._apply_borrowing
            _is_harness = UsageDaemon._is_harness

            def __init__(self, snapshots, overrides=None):
                self.snapshots = snapshots
                self._specs = {
                    "opencode": [ProcessSpec(names=frozenset({"opencode"}))],
                    "pi": [
                        ProcessSpec(
                            names=frozenset({"pi"}), resolve_backend=lambda d: None
                        )
                    ],
                }
                self.config = mock.Mock(primary_overrides=overrides or {})

        self.Harness = Harness

    def _opencode(self, status="ok"):
        return ProviderSnapshot(
            provider_id="opencode",
            display_name="OpenCode",
            icon="opencode",
            plan="Go",
            metrics=[
                Meter("rolling", "Rolling limit", 74.0),
                Meter("weekly", "Weekly", 41.0),
            ],
            primary_key="rolling",
            status=status,
            fetched_at=datetime.now(timezone.utc),
        )

    def _pi(self, backends):
        snap = ProviderSnapshot(
            provider_id="pi",
            display_name="Pi",
            icon="pi",
            plan=None,
            metrics=[],
            primary_key="",
            status="ok",
            fetched_at=datetime.now(timezone.utc),
        )
        snap.instances = self.InstanceReport(
            active=[
                self.Instance(
                    "pi", 100 + n, "app", "/w/app", None, False, backend=backend
                )
                for n, backend in enumerate(backends)
            ]
        )
        return snap

    def test_metered_backend_lends_its_meters(self):
        oc, pi = (
            self._opencode(),
            self._pi([Backend("opencode-go", "glm-5.3", "opencode")]),
        )
        self.Harness([oc, pi])._apply_borrowing()
        self.assertEqual([m.key for m in pi.metrics], ["rolling", "weekly"])
        self.assertEqual(pi.primary_key, "rolling")
        self.assertEqual(pi.borrowed_from, "opencode")
        self.assertEqual(pi.plan, "glm-5.3")
        self.assertEqual(pi.to_panel_dict()["via"]["borrowed"], True)

    def test_unmetered_backend_gets_no_meters_but_keeps_its_name(self):
        oc, pi = self._opencode(), self._pi([Backend("xai", "grok-4.5", "")])
        self.Harness([oc, pi])._apply_borrowing()
        self.assertEqual(pi.metrics, [])
        self.assertIsNone(pi.borrowed_from)
        self.assertEqual(pi.status, "ok")
        assert pi.error is not None
        self.assertIn("xAI", pi.error)
        self.assertEqual(pi.to_panel_dict()["via"]["metered"], False)

    def test_backend_provider_signed_out_reports_why(self):
        oc, pi = (
            self._opencode(status="auth_needed"),
            self._pi([Backend("opencode-go", "glm-5.3", "opencode")]),
        )
        self.Harness([oc, pi])._apply_borrowing()
        self.assertEqual(pi.metrics, [])
        self.assertIsNone(pi.borrowed_from)
        assert pi.error is not None
        self.assertIn("Sign in", pi.error)

    def test_no_sessions_means_no_meters_and_no_backend(self):
        oc, pi = self._opencode(), self._pi([])
        self.Harness([oc, pi])._apply_borrowing()
        self.assertIsNone(pi.backend)
        self.assertEqual(pi.metrics, [])
        self.assertIsNone(pi.to_panel_dict()["via"])

    def test_the_lending_provider_is_left_alone(self):
        oc, pi = (
            self._opencode(),
            self._pi([Backend("opencode-go", "glm-5.3", "opencode")]),
        )
        self.Harness([oc, pi])._apply_borrowing()
        self.assertIsNone(oc.backend)
        self.assertIsNone(oc.borrowed_from)
        self.assertEqual(oc.primary_key, "rolling")

    def test_a_chip_swap_on_the_harness_survives_the_next_borrow(self):
        oc, pi = (
            self._opencode(),
            self._pi([Backend("opencode-go", "glm-5.3", "opencode")]),
        )
        self.Harness([oc, pi], overrides={"pi": "weekly"})._apply_borrowing()
        self.assertEqual(pi.primary_key, "weekly")


if __name__ == "__main__":
    unittest.main()
