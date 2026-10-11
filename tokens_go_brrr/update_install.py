"""Fetch a published package, check it, and hand it to the package manager.

``updates`` decides *whether* there is something newer; this module does the
two things that follow once the user presses Update: download the package for
this distro, and install it with root rights through polkit (``pkexec``), so
the person types their password into the desktop's own dialog and the daemon
never sees it.

The download is checked against the sha256 in the manifest before anything is
installed, and again just before the install starts. Failures raise
``UpdateError`` with a message fit to show on the panel.
"""

from __future__ import annotations

import hashlib
import http.client
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from .http_json import USER_AGENT

# A package is a few hundred KB; this only stops a runaway response.
MAX_BYTES = 200 * 1024 * 1024
MAX_REDIRECTS = 5
INSTALL_TIMEOUT_SECONDS = 600
_CHUNK = 64 * 1024


class UpdateError(Exception):
    """Something went wrong that the user should be told about."""


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "tokens-go-brrr" / "updates"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _open(url: str) -> http.client.HTTPResponse:
    """GET ``url`` over verified HTTPS, following redirects (GitHub uses them)."""
    for _ in range(MAX_REDIRECTS + 1):
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            raise UpdateError("refusing a non-HTTPS download")
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        connection = http.client.HTTPSConnection(parts.hostname, timeout=60)
        connection.request("GET", path, headers={"User-Agent": USER_AGENT})
        response = connection.getresponse()
        if response.status in (301, 302, 303, 307, 308):
            location = response.getheader("Location")
            response.close()
            connection.close()
            if not location:
                raise UpdateError("download redirected nowhere")
            url = urljoin(url, location)
            continue
        if response.status != 200:
            status = response.status
            response.close()
            connection.close()
            raise UpdateError(f"download failed (HTTP {status})")
        return response
    raise UpdateError("too many redirects")


def download(offer: dict[str, Any], dest: Path | None = None) -> Path:
    """The verified package on disk, reusing a previous download if intact."""
    artifact = offer["artifact"]
    folder = dest or cache_dir()
    folder.mkdir(parents=True, exist_ok=True)
    # Private: the file is installed with root rights, so no one else may swap it.
    folder.chmod(0o700)
    target = folder / artifact["file"]
    if target.exists() and _sha256(target) == artifact["sha256"]:
        return target

    limit = min(artifact.get("size") or MAX_BYTES, MAX_BYTES)
    partial = target.with_suffix(target.suffix + ".part")
    digest = hashlib.sha256()
    written = 0
    try:
        response = _open(artifact["url"])
        try:
            with partial.open("wb") as out:
                while chunk := response.read(_CHUNK):
                    written += len(chunk)
                    if written > limit:
                        raise UpdateError("download is larger than the manifest says")
                    digest.update(chunk)
                    out.write(chunk)
        finally:
            response.close()
        if digest.hexdigest() != artifact["sha256"]:
            raise UpdateError("download does not match its checksum")
        partial.chmod(0o400)
        partial.replace(target)
    except OSError as exc:
        raise UpdateError(f"download failed: {exc}") from exc
    finally:
        partial.unlink(missing_ok=True)
    return target


def install_command(package: Path, family: str | None) -> list[str]:
    """The privileged command for this distro, or UpdateError if there is none."""
    if shutil.which("pkexec") is None:
        raise UpdateError("pkexec (polkit) is not installed")
    path = str(package.resolve())
    if family == "fedora" and shutil.which("dnf"):
        return ["pkexec", "dnf", "install", "-y", path]
    if family == "debian" and shutil.which("apt-get"):
        # An absolute path is what makes apt treat the argument as a file.
        return ["pkexec", "apt-get", "install", "-y", path]
    raise UpdateError("no supported package manager found")


def manual_hint(package: Path, family: str | None) -> str:
    """What to type in a terminal when the graphical install cannot run."""
    tool = "apt-get" if family == "debian" else "dnf"
    return f"sudo {tool} install {package}"


def install(package: Path, offer: dict[str, Any], family: str | None) -> None:
    """Install the package; blocks until the package manager finishes."""
    # The check at download time is not enough on its own: look again at the
    # moment the file is about to be given root rights.
    if _sha256(package) != offer["artifact"]["sha256"]:
        package.unlink(missing_ok=True)
        raise UpdateError("package changed on disk; download it again")
    command = install_command(package, family)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(f"install did not run: {exc}") from exc
    hint = manual_hint(package, family)
    if result.returncode == 126:
        raise UpdateError("not authorised (password prompt dismissed)")
    if result.returncode == 127 and command[0] == "pkexec":
        # pkexec found no authentication agent to ask: nothing was installed.
        raise UpdateError(f"no password prompt available. Try: {hint}")
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-1:]
        raise UpdateError(f"install failed ({tail[0] if tail else result.returncode}). Try: {hint}")
