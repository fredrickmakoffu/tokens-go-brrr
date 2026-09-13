from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

# Tray icon colors by usage band
COLORS = {
    "ok": (46, 204, 113),       # #2ecc71
    "warning": (243, 156, 18),  # #f39c12
    "critical": (231, 76, 60),  # #e74c3c
    "error": (149, 165, 166),   # #95a5a6
}

ICON_DIR = Path.home() / ".local" / "share" / "icons" / "cursor-spend-monitor"
SIZE = 22


def usage_level(percent: float) -> str:
    if percent >= 90:
        return "critical"
    if percent >= 70:
        return "warning"
    return "ok"


def make_icon(percent: float | None, *, error: bool = False) -> Path:
    """Write a PNG pie-chart icon GNOME AppIndicator can load reliably."""
    level = "error" if error else usage_level(percent or 0)
    color = COLORS[level]
    pct = 0 if percent is None else max(0, min(100, int(round(percent))))

    ICON_DIR.mkdir(parents=True, exist_ok=True)
    path = ICON_DIR / f"cursor-spend-{level}-{pct}.png"
    if path.exists():
        return path

    pixels = _render_pie(SIZE, color, 0 if error else pct)
    path.write_bytes(_encode_png(SIZE, SIZE, pixels))
    return path


def _render_pie(size: int, rgb: tuple[int, int, int], pct: int) -> bytes:
    cx = cy = (size - 1) / 2
    outer_r = size / 2 - 1.5
    inner_r = 2.2
    ring_w = 2.0
    fill_r = outer_r - ring_w - 0.5
    sweep = (pct / 100.0) * 2 * math.pi

    out = bytearray()
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            dist = math.hypot(dx, dy)
            # angle from top, clockwise
            ang = math.atan2(dx, -dy)
            if ang < 0:
                ang += 2 * math.pi

            r = g = b = 0
            a = 0

            # ring
            if abs(dist - outer_r + ring_w / 2) <= ring_w / 2 + 0.35:
                cover = max(0.0, 1.0 - abs(dist - (outer_r - ring_w / 2)) / (ring_w / 2 + 0.35))
                r, g, b = rgb
                a = int(255 * min(1.0, cover * 1.2))

            # pie fill
            if pct > 0 and dist <= fill_r + 0.5 and ang <= sweep:
                edge = max(0.0, 1.0 - max(0.0, dist - fill_r) / 0.5)
                r, g, b = rgb
                a = max(a, int(220 * edge))

            # center dot
            if dist <= inner_r:
                r, g, b = rgb
                a = 255

            out.extend((r, g, b, a))
    return bytes(out)


def _encode_png(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + rgba[y * width * 4 : (y + 1) * width * 4] for y in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
