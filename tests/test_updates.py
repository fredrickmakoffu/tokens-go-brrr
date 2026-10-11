import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tokens_go_brrr import updates

DIGEST = "a" * 64


def manifest(**over):
    base = {
        "version": "0.8.0",
        "released": "2026-10-12",
        "requires": "daemon",
        "changes": ["fix: x"],
        "artifacts": [
            {"platform": "fedora", "file": "tokens-go-brrr-0.8.0.noarch.rpm", "sha256": DIGEST},
            {"platform": "debian", "file": "tokens-go-brrr_0.8.0_all.deb", "sha256": DIGEST},
        ],
    }
    base.update(over)
    return base


class VersionTests(unittest.TestCase):
    def test_ordering_is_numeric_not_textual(self):
        self.assertTrue(updates.is_newer("0.10.0", "0.9.0"))
        self.assertFalse(updates.is_newer("0.7.0", "0.7.0"))
        self.assertFalse(updates.is_newer("0.6.9", "0.7.0"))

    def test_garbage_is_never_newer(self):
        for bad in (None, "", "latest", "1.2", "1.2.3-rc1"):
            self.assertFalse(updates.is_newer(bad, "0.7.0"))
        self.assertFalse(updates.is_newer("0.8.0", "dev"))


class DistroTests(unittest.TestCase):
    def test_families(self):
        self.assertEqual(updates.distro_family("ID=fedora\n"), "fedora")
        self.assertEqual(
            updates.distro_family('ID=rocky\nID_LIKE="rhel centos fedora"\n'), "fedora"
        )
        self.assertEqual(updates.distro_family("ID=ubuntu\nID_LIKE=debian\n"), "debian")
        self.assertIsNone(updates.distro_family("ID=arch\n"))


class OfferTests(unittest.TestCase):
    def offer(self, m, family="fedora", current="0.7.0"):
        return updates.offer_from_manifest(m, current=current, family=family)

    def test_offer_picks_the_family_artifact(self):
        got = self.offer(manifest())
        self.assertEqual(got["version"], "0.8.0")
        self.assertEqual(got["requires"], "daemon")
        self.assertTrue(got["artifact"]["file"].endswith(".rpm"))
        self.assertIn("/v0.8.0/", got["artifact"]["url"])

    def test_nothing_when_not_newer_or_unknown_distro(self):
        self.assertIsNone(self.offer(manifest(), current="0.8.0"))
        with mock.patch.object(updates, "distro_family", return_value=None):
            self.assertIsNone(self.offer(manifest(), family=None))
        self.assertIsNone(self.offer(None))

    def test_unknown_requires_is_the_strict_one(self):
        self.assertEqual(self.offer(manifest(requires="reboot"))["requires"], "relogin")

    def test_rejects_unsafe_artifacts(self):
        for entry in (
            {"platform": "fedora", "file": "../../x.rpm", "sha256": DIGEST},
            {"platform": "fedora", "file": "a.rpm", "sha256": "short"},
            {"platform": "fedora", "file": "a.sh", "sha256": DIGEST},
        ):
            self.assertIsNone(self.offer(manifest(artifacts=[entry])))


class NotifyOnceTests(unittest.TestCase):
    def test_once_per_version_and_not_when_skipped(self):
        offer = {"version": "0.8.0"}
        self.assertTrue(updates.should_notify(offer, {}))
        self.assertFalse(updates.should_notify(offer, {"notified_version": "0.8.0"}))
        self.assertFalse(updates.should_notify(offer, {"skipped_version": "0.8.0"}))
        self.assertTrue(updates.should_notify({"version": "0.9.0"}, {"notified_version": "0.8.0"}))

    def test_state_round_trip_and_bad_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "update-state.json"
            with mock.patch.object(updates, "state_file", return_value=path):
                self.assertEqual(updates.load_state(), {})
                updates.save_state({"notified_version": "0.8.0"})
                self.assertEqual(updates.load_state()["notified_version"], "0.8.0")
                path.write_text("not json")
                self.assertEqual(updates.load_state(), {})


class FetchTests(unittest.TestCase):
    def test_failure_is_none(self):
        with mock.patch.object(updates, "request_json_url", side_effect=OSError("down")):
            self.assertIsNone(updates.fetch_manifest("https://example.invalid/m.json"))


if __name__ == "__main__":
    unittest.main()
