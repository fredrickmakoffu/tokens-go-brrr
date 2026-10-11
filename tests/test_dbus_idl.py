"""Extension and daemon must advertise the same D-Bus method set."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from tokens_go_brrr.dbus_service import INTERFACE_XML

ROOT = Path(__file__).resolve().parents[1]
EXT_JS = (
    ROOT / "gnome-shell-extension" / "tokens-go-brrr@fredrickmakoffu.github.io" / "extension.js"
)


def _methods(xml: str) -> set[str]:
    return set(re.findall(r'<method name="([^"]+)"', xml))


class DbusIdlParityTest(unittest.TestCase):
    def test_extension_iface_matches_daemon(self) -> None:
        text = EXT_JS.read_text()
        match = re.search(r"const IFACE_XML = `([\s\S]*?)`;", text)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(_methods(match.group(1)), _methods(INTERFACE_XML))


if __name__ == "__main__":
    unittest.main()
