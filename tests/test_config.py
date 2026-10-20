"""Tests for reading the config file.

The config is a file a person edits by hand, so the failure mode that matters
is the one where a typo stops the daemon starting or makes every command exit
on a traceback. These tests pin the fallbacks.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tokens_go_brrr import config as config_module
from tokens_go_brrr.config import MonitorConfig


class ConfigLoadTest(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.root = Path(self._dir.name)
        self.path = self.root / "config.json"
        patcher = mock.patch.object(config_module, "CONFIG_FILE", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        dir_patcher = mock.patch.object(config_module, "CONFIG_DIR", self.root)
        dir_patcher.start()
        self.addCleanup(dir_patcher.stop)

    def write(self, text: str) -> None:
        self.path.write_text(text)

    def test_defaults_when_the_file_is_absent(self):
        found = MonitorConfig.load()
        self.assertEqual(found.ledger_days, 90)
        self.assertEqual(found.harvest_deep_seconds, 3600)

    def test_a_corrupt_file_falls_back_to_defaults(self):
        self.write("{not json")
        with mock.patch("sys.stderr"):
            found = MonitorConfig.load()
        self.assertEqual(found.poll_interval_seconds, 300)
        self.assertEqual(found.ledger_days, 90)

    def test_a_non_object_falls_back_to_defaults(self):
        self.write(json.dumps([1, 2, 3]))
        with mock.patch("sys.stderr"):
            found = MonitorConfig.load()
        self.assertEqual(found.ledger_days, 90)

    def test_a_typo_in_a_number_uses_the_default_for_that_field_only(self):
        self.write(json.dumps({"ledger_days": "ninety", "poll_interval_seconds": 60}))
        found = MonitorConfig.load()
        self.assertEqual(found.ledger_days, 90)
        self.assertEqual(found.poll_interval_seconds, 60)

    def test_valid_values_are_read(self):
        self.write(json.dumps({"ledger_days": 30, "harvest_deep_seconds": 120}))
        found = MonitorConfig.load()
        self.assertEqual(found.ledger_days, 30)
        self.assertEqual(found.harvest_deep_seconds, 120)

    def test_save_and_load_round_trip_the_ledger_fields(self):
        MonitorConfig(ledger_days=45, harvest_deep_seconds=600).save()
        found = MonitorConfig.load()
        self.assertEqual(found.ledger_days, 45)
        self.assertEqual(found.harvest_deep_seconds, 600)

    def test_defaults_include_all_five_providers(self):
        found = MonitorConfig.load()
        self.assertEqual(
            found.enabled_providers,
            ["cursor", "claude", "opencode", "pi", "codex"],
        )

    def test_hiding_a_provider_persists(self):
        cfg = MonitorConfig.load()
        self.assertTrue(cfg.set_provider_enabled("codex", False))
        self.assertNotIn("codex", cfg.enabled_providers)
        again = MonitorConfig.load()
        self.assertNotIn("codex", again.enabled_providers)

    def test_showing_a_provider_restores_default_order(self):
        cfg = MonitorConfig(enabled_providers=["cursor", "claude"])
        cfg.save()
        self.assertTrue(cfg.set_provider_enabled("codex", True))
        self.assertEqual(cfg.enabled_providers, ["cursor", "claude", "codex"])
        self.assertTrue(cfg.set_provider_enabled("opencode", True))
        self.assertEqual(
            cfg.enabled_providers,
            ["cursor", "claude", "opencode", "codex"],
        )

    def test_unknown_provider_is_ignored(self):
        cfg = MonitorConfig.load()
        before = list(cfg.enabled_providers)
        self.assertFalse(cfg.set_provider_enabled("nope", True))
        self.assertEqual(cfg.enabled_providers, before)

    def test_ui_theme_defaults_and_persists(self):
        found = MonitorConfig.load()
        self.assertEqual(found.ui_theme, "auto")
        self.write(json.dumps({"ui_theme": "light"}))
        found = MonitorConfig.load()
        self.assertEqual(found.ui_theme, "light")
        MonitorConfig(ui_theme="dark").save()
        self.assertEqual(MonitorConfig.load().ui_theme, "dark")

    def test_invalid_ui_theme_falls_back_to_auto(self):
        self.write(json.dumps({"ui_theme": "neon"}))
        self.assertEqual(MonitorConfig.load().ui_theme, "auto")


if __name__ == "__main__":
    unittest.main()
