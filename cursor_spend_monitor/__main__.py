from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .config import CONFIG_FILE, MonitorConfig
from .providers import build_providers
from .session import run_setup


def cmd_status(_args: argparse.Namespace) -> int:
    config = MonitorConfig.load()
    providers = build_providers(config.enabled_providers)
    if not providers:
        print("No providers enabled.")
        return 1

    exit_code = 0
    for provider in providers:
        try:
            snap = provider.fetch()
        except Exception as exc:  # noqa: BLE001
            print(f"{provider.display_name}: error — {exc}")
            exit_code = 1
            continue

        key = config.primary_overrides.get(snap.provider_id)
        if key and snap.status == "ok":
            snap = snap.with_primary(key)

        if snap.status != "ok":
            print(f"{snap.display_name}: {snap.error or snap.status}")
            exit_code = 1
            continue

        print(snap.header())
        for meter in snap.metrics:
            mark = "★" if meter.key == snap.primary_key else " "
            print(f"  {mark} {meter.label:<16} {meter.percent:5.1f}%  {meter.resets_label()}")
    return exit_code


def cmd_show_config(_args: argparse.Namespace) -> int:
    if CONFIG_FILE.exists():
        print(CONFIG_FILE.read_text())
    else:
        print(json.dumps(MonitorConfig().__dict__, indent=2))
    print(f"\nConfig path: {CONFIG_FILE}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cursor-spend-monitor",
        description="AI usage daemon for the GNOME Shell indicator",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="Verify provider logins (Cursor IDE)")
    sub.add_parser("run", help="Start the usage daemon (foreground)")
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
        from .daemon import run_daemon

        return run_daemon(MonitorConfig.load())

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
