"""Tiny stderr logger — levels without pulling in a logging framework.

Match this when a module needs more than a one-off ``print(..., file=sys.stderr)``.
Existing modules may keep their local ``print`` style until touched.
"""

from __future__ import annotations

import sys
from typing import TextIO


def log(message: str, *, level: str = "info", stream: TextIO | None = None) -> None:
    """Write ``[tokens-go-brrr LEVEL] message`` to stderr (or ``stream``)."""
    out = stream if stream is not None else sys.stderr
    print(f"[tokens-go-brrr {level.upper()}] {message}", file=out, flush=True)


def warn(message: str) -> None:
    log(message, level="warn")


def error(message: str) -> None:
    log(message, level="error")
