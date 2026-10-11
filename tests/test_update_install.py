import hashlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tokens_go_brrr import update_install as ui

PAYLOAD = b"not really an rpm"
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


def offer(digest=DIGEST, size=len(PAYLOAD)):
    return {
        "version": "0.8.0",
        "artifact": {
            "file": "tokens-go-brrr-0.8.0.noarch.rpm",
            "sha256": digest,
            "size": size,
            "url": "https://example.test/x.rpm",
        },
    }


class FakeResponse(io.BytesIO):
    pass


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name) / "cache"

    def test_verified_download_lands_private(self):
        with mock.patch.object(ui, "_open", return_value=FakeResponse(PAYLOAD)):
            path = ui.download(offer(), self.dest)
        self.assertEqual(path.read_bytes(), PAYLOAD)
        self.assertEqual(path.stat().st_mode & 0o777, 0o400)
        self.assertEqual(self.dest.stat().st_mode & 0o777, 0o700)
        self.assertEqual(list(self.dest.glob("*.part")), [])

    def test_wrong_checksum_leaves_nothing(self):
        with mock.patch.object(ui, "_open", return_value=FakeResponse(b"tampered!!!!!!!!!")):
            with self.assertRaises(ui.UpdateError):
                ui.download(offer(), self.dest)
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_oversized_response_is_cut_off(self):
        with mock.patch.object(ui, "_open", return_value=FakeResponse(PAYLOAD * 5)):
            with self.assertRaises(ui.UpdateError):
                ui.download(offer(), self.dest)

    def test_intact_cache_is_reused_without_network(self):
        with mock.patch.object(ui, "_open", return_value=FakeResponse(PAYLOAD)):
            ui.download(offer(), self.dest)
        with mock.patch.object(ui, "_open", side_effect=AssertionError("network")):
            self.assertTrue(ui.download(offer(), self.dest).exists())


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pkg = Path(self.tmp.name) / "p.rpm"
        self.pkg.write_bytes(PAYLOAD)

    def run_install(self, code, family="fedora", stderr=""):
        done = subprocess.CompletedProcess([], code, "", stderr)
        with (
            mock.patch.object(ui.shutil, "which", return_value="/usr/bin/x"),
            mock.patch.object(ui.subprocess, "run", return_value=done) as run,
        ):
            ui.install(self.pkg, offer(), family)
        return run

    def test_fedora_and_debian_commands(self):
        self.assertEqual(
            self.run_install(0).call_args[0][0][:4], ["pkexec", "dnf", "install", "-y"]
        )
        run = self.run_install(0, family="debian")
        self.assertEqual(run.call_args[0][0][1], "apt-get")

    def test_dismissed_prompt_and_no_agent_are_readable(self):
        with self.assertRaisesRegex(ui.UpdateError, "not authorised"):
            self.run_install(126)
        with self.assertRaisesRegex(ui.UpdateError, "sudo dnf install"):
            self.run_install(127)

    def test_failure_carries_the_last_line_and_a_manual_command(self):
        with self.assertRaisesRegex(ui.UpdateError, "boom.*sudo dnf install"):
            self.run_install(1, stderr="warn\nboom")

    def test_a_swapped_file_is_never_installed(self):
        self.pkg.write_bytes(b"swapped")
        with mock.patch.object(ui.subprocess, "run") as run:
            with self.assertRaises(ui.UpdateError):
                ui.install(self.pkg, offer(), "fedora")
        run.assert_not_called()

    def test_unknown_distro_is_an_error_not_a_guess(self):
        with mock.patch.object(ui.shutil, "which", return_value="/usr/bin/x"):
            with self.assertRaises(ui.UpdateError):
                ui.install_command(self.pkg, None)


if __name__ == "__main__":
    unittest.main()
