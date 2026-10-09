#!/usr/bin/env python3
"""Write SHA256SUMS and manifest.json for the packages in a directory.

manifest.json is what the download site reads: one entry per installable, with
enough to render a button and a checksum. Platform is inferred from the suffix.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

PLATFORMS = {
    ".rpm": ("linux", "fedora", "Fedora / RHEL"),
    ".deb": ("linux", "debian", "Debian / Ubuntu"),
    ".exe": ("windows", "windows", "Windows"),
    ".dmg": ("macos", "macos", "macOS"),
}


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    version = Path(__file__).resolve().parent.parent.joinpath("pyproject.toml")
    ver = next(
        line.split('"')[1] for line in version.read_text().splitlines() if line.startswith("version")
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
            {"platform": key, "os": os_name, "label": label, "file": path.name,
             "size": path.stat().st_size, "sha256": digest}
        )
        sums.append(f"{digest}  {path.name}")

    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    (out / "manifest.json").write_text(
        json.dumps(
            {"version": ver, "released": dt.date.today().isoformat(), "artifacts": entries}, indent=2
        ) + "\n"
    )
    print(f"wrote SHA256SUMS and manifest.json ({len(entries)} artifacts, v{ver})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
