from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

from . import __version__
from .config import CONFIG_FILE, MonitorConfig
from .providers import build_providers
from .session import run_setup
from .state import build_payload, header_of, primary_metric, read_state

# Placeholders accepted by `status --format`. Keep this table and the help text
# together: it is the only documentation a status-bar author gets.
FORMAT_FIELDS = {
    "id": "provider id, e.g. claude",
    "name": "display name",
    "icon": "icon name the extension uses",
    "plan": "plan name, or empty",
    "status": "ok | error | auth_needed | soon",
    "pct": "primary meter percent, or — when not ok",
    "label": "primary meter label, e.g. 5-hour limit",
    "resets": "when the primary meter resets",
    "sessions": "running sessions",
    "paused": "suspended sessions",
    "via": "backend account a harness is spending on, or empty",
    "error": "error text, or empty",
}


def _live_payload(config: MonitorConfig) -> dict[str, Any]:
    """Ask every provider directly. Costs one request per provider per call."""
    snapshots = []
    for provider in build_providers(config.enabled_providers):
        try:
            snap = provider.fetch()
        except Exception as exc:  # noqa: BLE001
            from .providers.base import ProviderSnapshot

            snap = ProviderSnapshot.error_snapshot(
                provider_id=getattr(provider, "id", "unknown"),
                display_name=getattr(provider, "display_name", "Provider"),
                icon=getattr(provider, "id", "cursor"),
                message=str(exc),
            )
        key = config.primary_overrides.get(snap.provider_id)
        if key and snap.status == "ok":
            snap = snap.with_primary(key)
        snapshots.append(snap)
    return build_payload(
        snapshots,
        version=__version__,
        updated_at=datetime.now(timezone.utc),
        error=None,
    )


def _load_payload(config: MonitorConfig, *, live: bool) -> dict[str, Any]:
    """Published state when the daemon is running and current, else a fetch.

    `source` says which happened, because it changes what the numbers mean: a
    live payload reports no running sessions (nothing scanned /proc for it).
    """
    if not live:
        payload = read_state(config)
        if payload is not None:
            payload["source"] = "daemon"
            return payload
    payload = _live_payload(config)
    payload["source"] = "live"
    return payload


def _format_fields(tool: dict[str, Any]) -> dict[str, str]:
    metric = primary_metric(tool)
    # A harness whose sessions are on an unmeterable account reports ok with no
    # meters at all. Rendering that as 0% would read as "plenty left" instead of
    # "unknown", so anything without a real meter shows the same dash as an error.
    ok = tool.get("status") == "ok" and bool(tool.get("metrics"))
    instances = tool.get("instances") or {}
    via = tool.get("via") or {}
    return {
        "id": str(tool.get("id", "")),
        "name": str(tool.get("name", "")),
        "icon": str(tool.get("icon", "")),
        "plan": str(tool.get("plan") or ""),
        "status": str(tool.get("status", "")),
        "pct": str(metric.get("value", 0)) if ok else "—",
        "label": str(metric.get("label", "")),
        "resets": str(metric.get("resets", "")),
        "sessions": str(instances.get("active", 0)),
        "paused": str(instances.get("suspended", 0)),
        "via": str(via.get("name") or ""),
        "error": str(tool.get("error") or ""),
    }


def _render_format(tools: list[dict[str, Any]], template: str, separator: str) -> str:
    parts = []
    for tool in tools:
        fields = _format_fields(tool)
        try:
            parts.append(template.format(**fields))
        except KeyError as exc:
            known = ", ".join(sorted(FORMAT_FIELDS))
            raise SystemExit(
                f"Unknown field {exc} in --format. Available fields: {known}"
            ) from exc
        except (IndexError, ValueError) as exc:
            raise SystemExit(
                f"Could not read --format template: {exc}. "
                "Write fields as {name}, and double any literal brace as {{ or }}."
            ) from exc
    return separator.join(parts)


def _render_text(payload: dict[str, Any], tools: list[dict[str, Any]]) -> str:
    lines = []
    for tool in tools:
        if tool.get("status") != "ok":
            lines.append(f"{tool.get('name', '?')}: {tool.get('error') or tool.get('status')}")
            continue
        lines.append(header_of(tool))
        if not tool.get("metrics"):
            lines.append(f"    {tool.get('error') or 'No limits to report'}")
        for metric in tool.get("metrics") or []:
            mark = "★" if metric.get("key") == tool.get("primary") else " "
            label = str(metric.get("label", ""))
            value = metric.get("value", 0)
            lines.append(f"  {mark} {label:<16} {value:>3}%  {metric.get('resets', '')}")
        instances = tool.get("instances") or {}
        if instances.get("active"):
            projects = ", ".join(instances.get("projects") or [])
            detail = f" ({projects})" if projects else ""
            lines.append(f"    {instances['active']} running{detail}")
    if payload.get("source") == "live":
        lines.append("")
        lines.append("Fetched directly; daemon not running, so sessions are not counted.")
    return "\n".join(lines)


def cmd_status(args: argparse.Namespace) -> int:
    config = MonitorConfig.load()
    if not config.enabled_providers:
        print("No providers enabled.", file=sys.stderr)
        return 1

    payload = _load_payload(config, live=args.live)
    tools = payload.get("tools") or []
    if args.provider:
        wanted = set(args.provider)
        tools = [t for t in tools if t.get("id") in wanted]
        if not tools:
            enabled = ", ".join(config.enabled_providers)
            print(
                f"No provider matched {', '.join(sorted(wanted))}. Enabled: {enabled}",
                file=sys.stderr,
            )
            return 2

    if args.json:
        shown = dict(payload)
        shown["tools"] = tools
        print(json.dumps(shown, indent=None if args.compact else 2))
    elif args.format:
        rendered = _render_format(tools, args.format, args.separator)
        if rendered:
            print(rendered)
    else:
        print(_render_text(payload, tools))

    return 0 if all(t.get("status") == "ok" for t in tools) else 1


def cmd_show_config(_args: argparse.Namespace) -> int:
    if CONFIG_FILE.exists():
        print(CONFIG_FILE.read_text())
    else:
        print(json.dumps(MonitorConfig().__dict__, indent=2))
    print(f"\nConfig path: {CONFIG_FILE}")
    return 0


def _add_status_parser(sub: argparse._SubParsersAction) -> None:
    fields = "\n".join(f"  {{{name}}}  {desc}" for name, desc in FORMAT_FIELDS.items())
    parser = sub.add_parser(
        "status",
        help="Print current usage to stdout",
        description=(
            "Print current usage.\n\n"
            "Reads the running daemon's published state, so this makes no network "
            "request and is safe to call as often as a status bar needs. With no "
            "daemon running it falls back to fetching from each provider, which "
            "does cost one request per provider.\n\n"
            "--format fields:\n" + fields
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  cursor-spend-monitor status --json\n"
            '  cursor-spend-monitor status --format "{icon} {pct}%%" --provider claude\n'
            '  cursor-spend-monitor status --format "{name} {pct}%% ({sessions})"\n'
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print the payload as JSON")
    parser.add_argument(
        "--compact", action="store_true", help="With --json, print it on one line"
    )
    parser.add_argument(
        "--format",
        metavar="TEMPLATE",
        help="Render one line per provider from a {field} template",
    )
    parser.add_argument(
        "--separator",
        default="  ",
        help="String between providers in --format output (default: two spaces)",
    )
    parser.add_argument(
        "--provider",
        action="append",
        metavar="ID",
        help="Limit output to this provider; repeatable",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Fetch from providers even when the daemon has fresh state",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cursor-spend-monitor",
        description="AI usage daemon for the GNOME Shell indicator",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="Verify provider logins (Cursor IDE)")
    sub.add_parser("run", help="Start the usage daemon (foreground)")
    _add_status_parser(sub)
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
