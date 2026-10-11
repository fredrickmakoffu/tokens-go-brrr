import importlib.util
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "make_manifest.py"
spec = importlib.util.spec_from_file_location("make_manifest", SCRIPT)
mm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mm)


def fake_git(tags, touched, changes):
    def run(*args):
        if args[0] == "tag":
            return tags
        if args[0] == "diff":
            return touched
        return changes

    return run


class UpdateInfoTests(unittest.TestCase):
    def info(self, tags, touched=(), changes=()):
        with mock.patch.object(mm, "_git", fake_git(list(tags), list(touched), list(changes))):
            return mm.update_info("0.7.1")

    def test_daemon_only_when_extension_untouched(self):
        got = self.info(["v0.7.0"], changes=["fix: x"])
        self.assertEqual(got["requires"], "daemon")
        self.assertEqual(got["since"], "v0.7.0")
        self.assertEqual(got["changes"], ["fix: x"])

    def test_relogin_when_extension_touched(self):
        got = self.info(["v0.7.0"], touched=["gnome-shell-extension/x/extension.js"])
        self.assertEqual(got["requires"], "relogin")

    def test_own_tag_is_not_the_baseline(self):
        got = self.info(["v0.7.1", "v0.7.0"])
        self.assertEqual(got["since"], "v0.7.0")

    def test_no_history_is_strict(self):
        self.assertEqual(self.info([])["requires"], "relogin")


if __name__ == "__main__":
    unittest.main()
