#!/usr/bin/env python3
"""Write SHA256SUMS and manifest.json for the packages in a directory.

manifest.json is what the download site reads: one entry per installable, with
enough to render a button and a checksum. Platform is inferred from the suffix.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PLATFORMS = {
    ".rpm": ("linux", "fedora", "Fedora / RHEL"),
    ".deb": ("linux", "debian", "Debian / Ubuntu"),
    ".exe": ("windows", "windows", "Windows"),
    ".dmg": ("macos", "macos", "macOS"),
}

ROOT = Path(__file__).resolve().parent.parent
EXTENSION_DIR = "gnome-shell-extension/"


def _git(*args: str) -> list[str]:
    out = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [line for line in out.splitlines() if line]


def previous_tag(version: str) -> str | None:
    """Newest v* tag reachable from HEAD, other than this release's own."""
    try:
        tags = _git("tag", "--merged", "HEAD", "--list", "v*", "--sort=-v:refname")
    except (OSError, subprocess.CalledProcessError):
        return None
    return next((t for t in tags if t != f"v{version}"), None)


def update_info(version: str) -> dict:
    """What an installed copy must do to pick this release up.

    GNOME Shell cannot reload extension code on Wayland, so a release that
    touches the extension needs a log out; anything else is a daemon restart.
    Unknown history is treated as the stricter case.
    """
    prev = previous_tag(version)
    if prev is None:
        return {"requires": "relogin", "since": None, "changes": []}
    try:
        touched = _git("diff", "--name-only", f"{prev}..HEAD", "--", EXTENSION_DIR)
        changes = _git("log", "--no-merges", "--format=%s", f"{prev}..HEAD")
    except (OSError, subprocess.CalledProcessError):
        return {"requires": "relogin", "since": prev, "changes": []}
    return {
        "requires": "relogin" if touched else "daemon",
        "since": prev,
        "changes": changes[:15],
    }


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    version = Path(__file__).resolve().parent.parent.joinpath("pyproject.toml")
    ver = next(
        line.split('"')[1]
        for line in version.read_text().splitlines()
        if line.startswith("version")
    )
    files = sorted(p for p in out.iterdir() if p.suffix in PLATFORMS)
    if not files:
        print(f"no packages in {out}", file=sys.stderr)
        return 1

    entries, sums = [], []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        os_name, key, label = PLATFORMS[path.suffix]
        entries.append(
            {
                "platform": key,
                "os": os_name,
                "label": label,
                "file": path.name,
                "size": path.stat().st_size,
                "sha256": digest,
            }
        )
        sums.append(f"{digest}  {path.name}")

    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    (out / "manifest.json").write_text(
        json.dumps(
            {
                "version": ver,
                "released": dt.date.today().isoformat(),
                **update_info(ver),
                "artifacts": entries,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote SHA256SUMS and manifest.json ({len(entries)} artifacts, v{ver})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
