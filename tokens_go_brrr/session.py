from __future__ import annotations

import sys

from .config import CONFIG_DIR, MonitorConfig
from .providers.cursor import CursorProvider


def run_setup() -> int:
    print("tokens-go-brrr — setup")
    print()
    print("Providers use local app logins. No browser cookies.")
    print()

    cursor = CursorProvider()
    if cursor.available():
        snap = cursor.fetch()
        if snap.status == "ok":
            print(f"Cursor: ok — {snap.header()}")
            bits = " · ".join(f"{m.label} {m.percent:.0f}%" for m in snap.metrics)
            print(f"  {bits}")
            print(f"  {snap.primary.resets_label()}")
        else:
            print(f"Cursor: {snap.error or snap.status}", file=sys.stderr)
            return 1
    else:
        print("Cursor: not signed in. Open the Cursor app and sign in.", file=sys.stderr)
        return 1

    config = MonitorConfig.load()
    config.save()
    print()
    print(f"Config: {CONFIG_DIR / 'config.json'}")
    print("Start daemon: systemctl --user restart tokens-go-brrr.service")
    return 0
