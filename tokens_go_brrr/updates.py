"""Find out whether a newer release has been published.

The release pipeline ends with a ``manifest.json`` on the public releases site
(version, what the update needs, one artifact per distro family, each with a
sha256). This module fetches it and decides what, if anything, an installed
copy should be offered. It never installs anything: that is a later, explicit
step the user takes.

Every failure is quiet. An unreachable site, a malformed manifest or an
unknown distro all mean "no update to show", never an error on the panel.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from . import __version__
from . import config as _config
from .http_json import request_json_url

RELEASES_REPO = "fredrickmakoffu/tokens-go-brrr"
MANIFEST_URL = "https://fredrickmakoffu.github.io/tokens-go-brrr/manifest.json"
DOWNLOAD_BASE = f"https://github.com/{RELEASES_REPO}/releases/download"

# What a release asks of the installed copy: restart the daemon, or log out
# first because GNOME Shell cannot reload extension code in a running session.
REQUIRES = ("daemon", "relogin")

_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
# A file name goes into a URL and onto disk, so only the shape a package has.
_SAFE_FILE = re.compile(r"^[A-Za-z0-9._+~-]+\.(rpm|deb)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def state_file() -> Path:
    return _config.CONFIG_DIR / "update-state.json"


def parse_version(text: Any) -> tuple[int, int, int] | None:
    match = _SEMVER.match(str(text or "").strip())
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def is_newer(candidate: Any, current: str = __version__) -> bool:
    """True only when both parse and the candidate is strictly ahead."""
    new, old = parse_version(candidate), parse_version(current)
    return new is not None and old is not None and new > old


def distro_family(os_release: str | None = None) -> str | None:
    """``fedora`` or ``debian``, matching the manifest's platform keys."""
    if os_release is None:
        try:
            os_release = Path("/etc/os-release").read_text()
        except OSError:
            return None
    ids: list[str] = []
    for line in os_release.splitlines():
        key, _, value = line.partition("=")
        if key in ("ID", "ID_LIKE"):
            ids += value.strip().strip("\"'").lower().split()
    if any(i in ("fedora", "rhel", "centos") for i in ids):
        return "fedora"
    if any(i in ("debian", "ubuntu") for i in ids):
        return "debian"
    return None


def installed_from_package() -> bool:
    """True when this code runs from a distro package under /usr.

    A source install (``install.sh`` into ~/.local) is not touched by a package
    upgrade, so offering a button for it would install something that never
    takes effect.
    """
    return Path(__file__).resolve().is_relative_to("/usr")


def fetch_manifest(url: str = MANIFEST_URL) -> dict[str, Any] | None:
    try:
        return request_json_url("GET", url, headers={"Accept": "application/json"}, timeout=15)
    except Exception as exc:  # noqa: BLE001 - fail-soft: a check never takes the daemon down
        # Includes HttpJsonError: a 404 before the first public release is
        # expected and must stay quiet on the panel.
        print(f"update check failed: {exc}", file=sys.stderr, flush=True)
        return None


def offer_from_manifest(
    manifest: dict[str, Any] | None,
    *,
    current: str = __version__,
    family: str | None = None,
) -> dict[str, Any] | None:
    """The update to show for this manifest, or None.

    The result is the panel's shape (``version``, ``requires``, ``changes``)
    plus the artifact to fetch. Anything that does not validate returns None
    rather than a partial offer.
    """
    if not isinstance(manifest, dict) or not is_newer(manifest.get("version"), current):
        return None
    family = family or distro_family()
    artifacts = manifest.get("artifacts")
    if family is None or not isinstance(artifacts, list):
        return None
    entry = next(
        (a for a in artifacts if isinstance(a, dict) and a.get("platform") == family), None
    )
    if entry is None:
        return None
    name, digest = str(entry.get("file") or ""), str(entry.get("sha256") or "")
    if not _SAFE_FILE.match(name) or not _SHA256.match(digest):
        return None
    version = str(manifest["version"]).lstrip("v")
    requires = manifest.get("requires")
    changes = manifest.get("changes")
    return {
        "version": version,
        "requires": requires if requires in REQUIRES else "relogin",
        "released": str(manifest.get("released") or ""),
        "changes": [str(c) for c in changes[:15]] if isinstance(changes, list) else [],
        "artifact": {
            "file": name,
            "sha256": digest,
            "size": entry.get("size") if isinstance(entry.get("size"), int) else None,
            "url": f"{DOWNLOAD_BASE}/v{version}/{name}",
        },
    }


def check(url: str = MANIFEST_URL, *, current: str = __version__) -> dict[str, Any] | None:
    """Fetch the manifest and return the offer for this install, if any."""
    return offer_from_manifest(fetch_manifest(url), current=current)


# -- what the user has already been told ------------------------------------


def load_state() -> dict[str, Any]:
    try:
        data = json.loads(state_file().read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(state: dict[str, Any]) -> None:
    try:
        state_file().parent.mkdir(parents=True, exist_ok=True)
        state_file().write_text(json.dumps(state, indent=2) + "\n")
    except OSError as exc:
        print(f"could not write update state: {exc}", file=sys.stderr, flush=True)


def should_notify(offer: dict[str, Any], state: dict[str, Any]) -> bool:
    """Once per version, and never for one the user skipped."""
    version = offer["version"]
    return version not in (state.get("notified_version"), state.get("skipped_version"))
