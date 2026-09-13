from __future__ import annotations

import sys

from .config import CONFIG_DIR, MonitorConfig
from .local_auth import read_local_auth, state_db_path


def run_setup() -> int:
    print("Cursor Spend Monitor — setup")
    print()
    print("Primary auth: Cursor IDE login (recommended)")
    print(f"  Looks for: {state_db_path()}")
    print("  Just stay signed in to the Cursor desktop app.")
    print()

    auth = read_local_auth()
    if auth:
        print(f"Found Cursor login for: {auth.email or '(email unknown)'}")
        print(f"Plan: {auth.membership_type or 'unknown'}")
        print()
        print("No browser cookie needed. You can run:")
        print("  cursor-spend-monitor status")
        print("  systemctl --user restart cursor-spend-monitor.service")
        # Ensure a config file exists for poll/alert settings
        config = MonitorConfig.load()
        config.save()
        print(f"Config: {CONFIG_DIR / 'config.json'}")
        return 0

    print("No Cursor IDE login found.", file=sys.stderr)
    print("Open the Cursor app, sign in, then re-run: cursor-spend-monitor setup", file=sys.stderr)
    return 1
