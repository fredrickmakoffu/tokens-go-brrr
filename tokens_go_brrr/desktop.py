"""Detect which panel UI package belongs on this session.

Install and packaging use the same rules: prefer an explicit choice, then the
session desktop, and never treat a leftover gnome-shell binary on a Plasma
machine as proof the user wants the GNOME extension.
"""

from __future__ import annotations

import os
import re

# XDG_CURRENT_DESKTOP is a colon-separated list (e.g. ubuntu:GNOME).
_GNOME = re.compile(r"(^|:)(GNOME|ubuntu:GNOME|Budgie)(:|$)", re.I)
_PLASMA = re.compile(r"(^|:)(KDE|Plasma)(:|$)", re.I)


def detect_ui(explicit: str | None = None, *, environ: dict[str, str] | None = None) -> str:
    """Return ``gnome``, ``plasma``, or ``none``.

    ``explicit`` may be ``gnome``, ``plasma``, ``none``, or ``auto`` / empty.
    """
    choice = (explicit or "").strip().lower()
    if choice in ("gnome", "plasma", "none"):
        return choice
    if choice not in ("", "auto"):
        return "none"

    env = environ if environ is not None else os.environ
    desktop = env.get("XDG_CURRENT_DESKTOP") or env.get("XDG_SESSION_DESKTOP") or ""
    session = env.get("DESKTOP_SESSION") or ""
    blob = f"{desktop}:{session}"

    if _PLASMA.search(blob):
        return "plasma"
    if _GNOME.search(blob):
        return "gnome"
    # Common session names without the XDG list.
    low = blob.lower()
    if "plasma" in low or "kde" in low:
        return "plasma"
    if "gnome" in low:
        return "gnome"
    return "none"
