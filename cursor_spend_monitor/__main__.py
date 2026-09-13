from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .api import CursorUsageClient
from .config import CONFIG_DIR, CONFIG_FILE, MonitorConfig
from .session import run_setup


def cmd_status(_args: argparse.Namespace) -> int:
    from .local_auth import read_local_auth

    if not read_local_auth():
        print("No Cursor IDE login found. Open Cursor, sign in, then retry.")
        return 1
    try:
        usage = CursorUsageClient().fetch()
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}")
        return 1

    print(f"Plan: {usage.membership_type}")
    print(f"Total:  {usage.total_percent:.1f}%")
    print(f"Auto:   {usage.auto_percent:.1f}%  ({usage.auto_message})")
    print(f"API:    {usage.api_percent:.1f}%  ({usage.api_message})")
    print(f"Reset:  {usage.reset_label()}")
    return 0


def cmd_show_config(_args: argparse.Namespace) -> int:
    if CONFIG_FILE.exists():
        print(CONFIG_FILE.read_text())
    else:
        print(json.dumps({"session_token": "(not set)"}, indent=2))
    print(f"\nConfig path: {CONFIG_FILE}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cursor-spend-monitor",
        description="GNOME tray monitor for Cursor AI usage",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="Configure WorkosCursorSessionToken cookie")
    sub.add_parser("run", help="Start the tray applet (foreground)")
    sub.add_parser("status", help="Print current usage to stdout")
    sub.add_parser("config", help="Print config file path and contents")

    args = parser.parse_args(argv)
    if args.command == "setup":
        return run_setup()
    if args.command == "status":
        return cmd_status(args)
    if args.command == "config":
        return cmd_show_config(args)
    if args.command == "run" or args.command is None:
        from .tray import run_tray

        return run_tray(MonitorConfig.load())

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
