#!/usr/bin/env python3
"""Keep the project's version in one place.

pyproject.toml is the source of truth. This script rewrites the other places
that carry a copy (the package's __version__, the GNOME extension's
metadata.json `version-name`, and the Plasma plasmoid Version) and can check
that they agree.

    scripts/bump_version.py 0.6.0     # set everywhere
    scripts/bump_version.py --check   # exit 1 if the copies disagree
    scripts/bump_version.py --print   # print the current version
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
INIT = ROOT / "tokens_go_brrr" / "__init__.py"
METADATA = (
    ROOT / "gnome-shell-extension" / "tokens-go-brrr@fredrickmakoffu.github.io" / "metadata.json"
)
PLASMA_META = ROOT / "plasma" / "org.tokensgobrrr.panel" / "metadata.json"

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
PYPROJECT_RE = re.compile(r'^(version\s*=\s*)"([^"]+)"', re.M)
INIT_RE = re.compile(r'^(__version__\s*=\s*)"([^"]+)"', re.M)


def _plasma_version() -> str:
    if not PLASMA_META.exists():
        return ""
    data = json.loads(PLASMA_META.read_text())
    return str(data.get("KPlugin", {}).get("Version") or "")


def read_versions() -> dict[str, str]:
    versions = {
        "pyproject.toml": PYPROJECT_RE.search(PYPROJECT.read_text()).group(2),
        "__init__.py": INIT_RE.search(INIT.read_text()).group(2),
        "metadata.json": json.loads(METADATA.read_text()).get("version-name", ""),
    }
    if PLASMA_META.exists():
        versions["plasma/metadata.json"] = _plasma_version()
    return versions


def set_version(version: str) -> None:
    for path, pattern in ((PYPROJECT, PYPROJECT_RE), (INIT, INIT_RE)):
        path.write_text(pattern.sub(rf'\g<1>"{version}"', path.read_text(), count=1))
    # Edit the JSON as text so the file's key order and layout are untouched.
    text = METADATA.read_text()
    if '"version-name"' in text:
        text = re.sub(r'("version-name"\s*:\s*)"[^"]*"', rf'\g<1>"{version}"', text)
    else:
        text = re.sub(
            r'(\n\s*)("version"\s*:\s*\d+)', rf'\g<1>\g<2>,\g<1>"version-name": "{version}"', text
        )
    METADATA.write_text(text)
    if PLASMA_META.exists():
        ptext = PLASMA_META.read_text()
        ptext = re.sub(
            r'("Version"\s*:\s*)"[^"]*"',
            rf'\g<1>"{version}"',
            ptext,
            count=1,
        )
        PLASMA_META.write_text(ptext)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("version", nargs="?", help="new version, X.Y.Z")
    parser.add_argument("--check", action="store_true", help="fail if the copies disagree")
    parser.add_argument(
        "--print", action="store_true", dest="show", help="print the current version"
    )
    args = parser.parse_args()

    if args.show:
        print(read_versions()["pyproject.toml"])
        return 0
    if args.check:
        versions = read_versions()
        if len(set(versions.values())) != 1:
            print("version mismatch:", file=sys.stderr)
            for name, value in versions.items():
                print(f"  {name}: {value!r}", file=sys.stderr)
            return 1
        print(f"ok: {versions['pyproject.toml']}")
        return 0
    if not args.version or not SEMVER.match(args.version):
        parser.error("give a version like 1.2.3")
    set_version(args.version)
    print(f"set {args.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
