"""Session → panel UI package selection."""

from __future__ import annotations

import unittest

from tokens_go_brrr.desktop import detect_ui


class DetectUiTest(unittest.TestCase):
    def test_explicit_wins(self):
        env = {"XDG_CURRENT_DESKTOP": "GNOME"}
        self.assertEqual(detect_ui("plasma", environ=env), "plasma")
        self.assertEqual(detect_ui("none", environ=env), "none")

    def test_gnome_session(self):
        self.assertEqual(
            detect_ui("auto", environ={"XDG_CURRENT_DESKTOP": "GNOME"}),
            "gnome",
        )
        self.assertEqual(
            detect_ui(environ={"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}),
            "gnome",
        )

    def test_plasma_session(self):
        self.assertEqual(
            detect_ui(environ={"XDG_CURRENT_DESKTOP": "KDE"}),
            "plasma",
        )
        self.assertEqual(
            detect_ui(environ={"DESKTOP_SESSION": "plasma"}),
            "plasma",
        )

    def test_gnome_shell_on_disk_does_not_matter(self):
        # Detection must ignore installed binaries; only the session counts.
        self.assertEqual(
            detect_ui(environ={"XDG_CURRENT_DESKTOP": "KDE", "PATH": "/usr/bin"}),
            "plasma",
        )

    def test_unknown_is_none(self):
        self.assertEqual(detect_ui(environ={"XDG_CURRENT_DESKTOP": "XFCE"}), "none")
        self.assertEqual(detect_ui("auto", environ={}), "none")


if __name__ == "__main__":
    unittest.main()
