"""Shared ui/tokens.json stays complete enough for generators and UIs."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKENS = ROOT / "ui" / "tokens.json"


class UiTokensTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = json.loads(TOKENS.read_text())

    def test_required_keys(self):
        for key in ("dark", "light", "lightMap", "primaryLightMap", "thresholds"):
            self.assertIn(key, self.data)
        for key in ("surface", "text", "ok", "wait", "crit", "hairline"):
            self.assertIn(key, self.data["dark"])
            self.assertIn(key, self.data["light"])
        self.assertEqual(self.data["thresholds"]["cautionAt"], 70)
        self.assertEqual(self.data["thresholds"]["criticalAt"], 90)

    def test_plasma_tree_exists(self):
        plasma = ROOT / "plasma" / "org.tokensgobrrr.panel"
        self.assertTrue((plasma / "metadata.json").is_file())
        self.assertTrue((plasma / "contents" / "ui" / "main.qml").is_file())
        self.assertTrue((plasma / "contents" / "ui" / "StateModel.qml").is_file())


if __name__ == "__main__":
    unittest.main()
