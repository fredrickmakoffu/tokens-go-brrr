"""Tests for session detection — fake /proc trees, no live processes required."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tokens_go_brrr.instances import ProcessSpec, scan, signature
from tokens_go_brrr.providers.cursor import CursorProvider

# tty_nr encoding used by the kernel: (major << 8) | minor for pts.
PTS = {n: (136 << 8) | n for n in range(16)}

AGENT = "/home/u/.local/share/cursor-agent/versions/x/index.js"
NODE = "/home/u/.local/share/cursor-agent/versions/x/node"
AGENT_BIN = "/home/u/.local/bin/agent"


def _write_proc(
    root: Path,
    pid: int,
    *,
    argv: list[str],
    state: str = "S",
    ppid: int = 1,
    tty_nr: int = 0,
    cwd: str | None = None,
) -> None:
    proc = root / str(pid)
    proc.mkdir(parents=True)
    (proc / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    # Minimal /proc/<pid>/stat: pid (comm) state ppid ... tty_nr ... starttime
    # Fields after ") " : state(0) ppid(1) pgrp(2) session(3) tty_nr(4) ... starttime(19)
    after = ["0"] * 20
    after[0] = state
    after[1] = str(ppid)
    after[4] = str(tty_nr)
    after[19] = "100"
    comm = os.path.basename(argv[0])[:15]
    (proc / "stat").write_text(f"{pid} ({comm}) " + " ".join(after) + "\n")
    if cwd is not None:
        os.symlink(cwd, proc / "cwd")


def _cursor_specs() -> dict[str, list[ProcessSpec]]:
    return {"cursor": list(CursorProvider.process_specs)}


class InstanceScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_worker_server_excluded(self) -> None:
        _write_proc(
            self.root,
            10,
            argv=[AGENT_BIN, "--use-system-ca", AGENT],
            tty_nr=PTS[2],
            cwd="/proj/a",
        )
        _write_proc(
            self.root,
            11,
            argv=[NODE, AGENT, "worker-server"],
            ppid=10,
            tty_nr=PTS[2],
            cwd="/proj/a",
        )
        report = scan(_cursor_specs(), proc=self.root)["cursor"]
        self.assertEqual(len(report.active), 1)
        self.assertEqual(report.active[0].pid, 10)

    def test_print_agent_excluded(self) -> None:
        _write_proc(
            self.root,
            20,
            argv=[AGENT_BIN, "--use-system-ca", AGENT, "--print", "do stuff"],
            tty_nr=0,
            cwd="/proj/b",
        )
        report = scan(_cursor_specs(), proc=self.root)["cursor"]
        self.assertEqual(report.active, [])
        self.assertEqual(report.suspended, [])

    def test_agent_under_electron_helper_collapses_to_editor(self) -> None:
        # cursor (matched) -> cursor --type=zygote (unmatched) -> agent (matched)
        _write_proc(self.root, 100, argv=["/usr/share/cursor/cursor"], tty_nr=0, cwd="/")
        _write_proc(
            self.root,
            101,
            argv=["/usr/share/cursor/cursor", "--type=zygote"],
            ppid=100,
            tty_nr=0,
        )
        _write_proc(
            self.root,
            102,
            argv=[AGENT_BIN, "--use-system-ca", AGENT],
            ppid=101,
            tty_nr=0,
            cwd="/proj/ide",
        )
        report = scan(_cursor_specs(), proc=self.root)["cursor"]
        self.assertEqual(sorted(i.pid for i in report.active), [100])
        self.assertEqual(report.suspended, [])

    def test_sibling_agents_same_tty_count_once(self) -> None:
        bash = 200
        _write_proc(self.root, bash, argv=["/bin/bash"], tty_nr=PTS[7], cwd="/proj/c")
        _write_proc(
            self.root,
            201,
            argv=[AGENT_BIN, "--use-system-ca", AGENT, "--resume"],
            state="T",
            ppid=bash,
            tty_nr=PTS[7],
            cwd="/proj/c",
        )
        _write_proc(
            self.root,
            202,
            argv=[AGENT_BIN, "--use-system-ca", AGENT],
            state="S",
            ppid=bash,
            tty_nr=PTS[7],
            cwd="/proj/c",
        )
        _write_proc(
            self.root,
            203,
            argv=[AGENT_BIN, "--use-system-ca", AGENT, "--resume"],
            state="T",
            ppid=bash,
            tty_nr=PTS[7],
            cwd="/proj/c",
        )
        report = scan(_cursor_specs(), proc=self.root)["cursor"]
        self.assertEqual(len(report.active), 1)
        self.assertEqual(report.active[0].pid, 202)
        self.assertEqual(report.suspended, [])

    def test_to_dict_lists_sessions(self) -> None:
        _write_proc(
            self.root,
            301,
            argv=[AGENT_BIN, "--use-system-ca", AGENT],
            tty_nr=PTS[2],
            cwd="/proj/x",
        )
        _write_proc(
            self.root,
            302,
            argv=[AGENT_BIN, "--use-system-ca", AGENT],
            state="T",
            tty_nr=PTS[3],
            cwd="/proj/y",
        )
        report = scan(_cursor_specs(), proc=self.root)["cursor"]
        payload = report.to_dict()
        self.assertEqual(payload["active"], 1)
        self.assertEqual(payload["suspended"], 1)
        self.assertEqual(
            [(s["project"], s["paused"], s["tty"], s["pid"]) for s in payload["sessions"]],
            [("x", False, "pts/2", 301), ("y", True, "pts/3", 302)],
        )

    def test_distinct_ttys_count_separately(self) -> None:
        _write_proc(
            self.root,
            301,
            argv=[AGENT_BIN, "--use-system-ca", AGENT],
            tty_nr=PTS[2],
            cwd="/proj/x",
        )
        _write_proc(
            self.root,
            302,
            argv=[AGENT_BIN, "--use-system-ca", AGENT],
            tty_nr=PTS[3],
            cwd="/proj/y",
        )
        report = scan(_cursor_specs(), proc=self.root)["cursor"]
        self.assertEqual(sorted(i.pid for i in report.active), [301, 302])

    def test_direct_worker_child_still_collapsed_if_matched(self) -> None:
        """Ancestor filter still works when a helper somehow matches the agent spec."""
        specs = {
            "cursor": [
                ProcessSpec(
                    names=frozenset({"agent", "node"}),
                    require_args=("cursor-agent",),
                    label="agent",
                )
            ]
        }
        _write_proc(
            self.root,
            40,
            argv=[AGENT_BIN, "--use-system-ca", AGENT],
            tty_nr=PTS[1],
            cwd="/proj/d",
        )
        _write_proc(
            self.root,
            41,
            argv=[NODE, AGENT, "worker-server"],
            ppid=40,
            tty_nr=PTS[1],
            cwd="/proj/d",
        )
        report = scan(specs, proc=self.root)["cursor"]
        self.assertEqual(len(report.active), 1)
        self.assertEqual(report.active[0].pid, 40)


class BackendResolverHookTests(unittest.TestCase):
    """A harness attaches the account each session spends against."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _specs(self, resolver):
        return {"pi": [ProcessSpec(names=frozenset({"pi"}), resolve_backend=resolver)]}

    def test_resolver_receives_the_cwd_and_result_reaches_the_panel(self) -> None:
        _write_proc(self.root, 10, argv=["/home/u/bin/pi"], tty_nr=PTS[3], cwd="/w/app")
        seen = []

        class FakeBackend:
            account = "opencode-go"
            model = "glm-5.3"

            def to_dict(self):
                return {"account": self.account, "model": self.model}

        def resolver(directory):
            seen.append(directory)
            return FakeBackend()

        reports = scan(self._specs(resolver), proc=self.root)
        self.assertEqual(seen, ["/w/app"])
        session = reports["pi"].to_dict()["sessions"][0]
        self.assertEqual(session["backend"], {"account": "opencode-go", "model": "glm-5.3"})

    def test_a_failing_resolver_does_not_take_the_scan_down(self) -> None:
        _write_proc(self.root, 11, argv=["/home/u/bin/pi"], tty_nr=PTS[4], cwd="/w/app")

        def resolver(_directory):
            raise RuntimeError("unreadable session log")

        reports = scan(self._specs(resolver), proc=self.root)
        self.assertEqual(len(reports["pi"].active), 1)
        self.assertNotIn("backend", reports["pi"].to_dict()["sessions"][0])

    def test_switching_backend_changes_the_signature(self) -> None:
        """A model switch has to reach the panel, so it must count as a change."""
        _write_proc(self.root, 12, argv=["/home/u/bin/pi"], tty_nr=PTS[5], cwd="/w/app")

        def resolver_for(model):
            class B:
                account = "opencode-go"

                def __init__(self):
                    self.model = model

                def to_dict(self):
                    return {"account": self.account, "model": self.model}

            return lambda _d: B()

        first = signature(scan(self._specs(resolver_for("glm-5.3")), proc=self.root))
        second = signature(scan(self._specs(resolver_for("grok-4.6")), proc=self.root))
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
