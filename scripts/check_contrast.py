#!/usr/bin/env python3
"""WCAG contrast for the website's colour tokens, light and dark.

Reads nothing from the CSS: the pairs below mirror site/styles.css. If a token
changes there, change it here and rerun. Exits non-zero if a pair that must
pass does not.

    python3 scripts/check_contrast.py
"""

import math
import sys


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))


def oklch(l, c, h):
    a, b = c * math.cos(math.radians(h)), c * math.sin(math.radians(h))
    l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (l - 0.0894841775 * a - 1.2914855480 * b) ** 3
    lin = (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )
    return tuple(max(0.0, min(1.0, x)) for x in lin)  # already linear


def lum(rgb, linear=False):
    def ch(v):
        if linear:
            return v
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (ch(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg, bg):
    (f, fl), (b, bl) = fg, bg
    x, y = lum(f, fl), lum(b, bl)
    hi, lo = max(x, y), min(x, y)
    return (hi + 0.05) / (lo + 0.05)


def H(h):
    return (hexrgb(h), False)


def OK(l, c, h):
    return (oklch(l, c, h), True)


# surface, text and muted are the tokens; "text" pairs need 4.5, "ui" pairs 3.0.
THEMES = {
    "light": {
        "bg": H("#f2f2f3"),
        "text": H("#1d1f20"),
        "muted": H("#5d5d60"),
        "link": H("#416180"),
        "accent": H("#5980a6"),
        "ok": H("#5980a6"),
        "btn": H("#416180"),
        "warn": OK(0.54, 0.14, 65),
        "crit": OK(0.55, 0.19, 30),
    },
    "dark": {
        "bg": H("#2b2b2d"),
        "text": H("#f5f5f8"),
        "muted": H("#b7b7ba"),
        "link": H("#94bce3"),
        "accent": H("#94bce3"),
        "ok": H("#94bce3"),
        "btn": H("#94bce3"),
        "warn": OK(0.82, 0.13, 80),
        "crit": OK(0.72, 0.17, 30),
    },
}
PAIRS = [  # name, foreground token, background token, required ratio
    ("body text", "text", "bg", 4.5),
    ("muted text", "muted", "bg", 4.5),
    ("link text", "link", "bg", 4.5),
    ("primary button label", "bg", "btn", 4.5),
    ("ok bar", "ok", "bg", 3.0),
    ("warn value text", "warn", "bg", 4.5),
    ("crit value text", "crit", "bg", 4.5),
]

failed = False
for theme, tok in THEMES.items():
    print(theme)
    for name, fg, bg, need in PAIRS:
        r = ratio(tok[fg], tok[bg])
        ok = r >= need
        failed |= not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {name:22s} {r:5.2f}  (needs {need})")
sys.exit(1 if failed else 0)
