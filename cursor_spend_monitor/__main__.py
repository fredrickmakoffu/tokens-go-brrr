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
from .state import build_payload, header_of, owns_meters, primary_metric, read_state

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
    "eta": "time until the primary meter is spent, or empty",
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
        "eta": str(metric.get("eta") or "") if ok else "",
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
            line = f"  {mark} {label:<16} {value:>3}%  {metric.get('resets', '')}"
            if metric.get("eta"):
                line += f"  ·  spent in {metric['eta']}"
            lines.append(line)
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


def _measurable(tool: dict[str, Any]) -> bool:
    """True when this row reports a limit of its own that we could read.

    Excludes a harness showing borrowed meters: it is a second view of a
    subscription already in the payload, so counting it would let one account
    decide an answer twice.
    """
    return bool(
        tool.get("status") == "ok" and tool.get("metrics") and owns_meters(tool)
    )


def _why_unmeasured(tool: dict[str, Any]) -> str:
    """Why a row was left out, in the row's own terms.

    A harness is skipped because its meters belong to another row, which is not
    the same as having none — saying "no meters" about a provider that is
    plainly showing a percentage reads as a bug.
    """
    via = tool.get("via") or {}
    if via.get("borrowed"):
        return f"on {via.get('name', 'another account')}, counted under {via.get('from')}"
    if tool.get("error"):
        return str(tool["error"])
    if not tool.get("metrics"):
        return "no limits reported"
    return str(tool.get("status", "unknown"))


def _select(config: MonitorConfig, payload: dict[str, Any], wanted) -> list[dict]:
    tools = payload.get("tools") or []
    if not wanted:
        return tools
    return [t for t in tools if t.get("id") in set(wanted)]


def cmd_check(args: argparse.Namespace) -> int:
    """Exit non-zero when there is not enough quota left to be worth starting.

    Written for hooks and shell aliases, so the exit code carries the answer and
    "we could not tell" is deliberately its own code rather than a pass or a
    fail: a stale login should not silently green-light a long run, nor fail a
    build that had nothing to do with quota.
    """
    config = MonitorConfig.load()
    payload = _load_payload(config, live=args.live)
    tools = _select(config, payload, args.provider)

    if args.provider and not tools:
        print(f"No provider matched {', '.join(sorted(set(args.provider)))}.", file=sys.stderr)
        return 2

    known = [t for t in tools if _measurable(t)]
    unknown = [t for t in tools if t not in known]

    if not known:
        if not args.quiet:
            names = ", ".join(t.get("name", "?") for t in unknown) or "nothing enabled"
            print(f"No usable meters ({names}).", file=sys.stderr)
        return 2

    results = [(t, 100 - int(primary_metric(t).get("value", 0))) for t in known]
    passing = [(t, h) for t, h in results if h >= args.min]

    if args.any:
        ok = bool(passing)
    else:
        ok = len(passing) == len(results)

    if not args.quiet:
        for tool, headroom in sorted(results, key=lambda r: r[1]):
            mark = "ok  " if headroom >= args.min else "low "
            eta = primary_metric(tool).get("eta")
            tail = f"  (spent in {eta})" if eta else ""
            print(f"{mark} {tool.get('name', '?')}: {headroom}% left{tail}")
        for tool in unknown:
            print(f"?    {tool.get('name', '?')}: {_why_unmeasured(tool)}")

    if unknown and args.fail_on_unknown:
        return 2
    return 0 if ok else 1


def cmd_best(args: argparse.Namespace) -> int:
    """Name the provider with the most headroom right now.

    The reason to run four subscriptions is that one of them always has room;
    this is the line that says which.
    """
    config = MonitorConfig.load()
    payload = _load_payload(config, live=args.live)
    candidates = [t for t in (payload.get("tools") or []) if _measurable(t)]

    if not candidates:
        print("No provider is reporting a usable limit.", file=sys.stderr)
        return 2

    ranked = sorted(candidates, key=lambda t: int(primary_metric(t).get("value", 0)))
    winner = ranked[0]

    if not args.explain:
        print(winner.get("id", ""))
        return 0

    headroom = 100 - int(primary_metric(winner).get("value", 0))
    others = ", ".join(
        f"{t.get('name')} {100 - int(primary_metric(t).get('value', 0))}% left"
        for t in ranked[1:]
    )
    line = f"Use {winner.get('name')} — {headroom}% left"
    print(f"{line} ({others})." if others else f"{line}.")
    return 0


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


def _add_check_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "check",
        help="Exit non-zero when quota is running low",
        description=(
            "Check that enough quota is left before starting something long.\n\n"
            "Exit codes: 0 there is headroom, 1 a provider is below the threshold, "
            "2 nothing could be measured (no daemon, signed out, no meters).\n\n"
            "Providers that report no usable limit are skipped rather than failed, "
            "unless --fail-on-unknown."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  cursor-spend-monitor check --min 20 --provider claude\n"
            "  cursor-spend-monitor check --min 10 --any --quiet\n"
        ),
    )
    parser.add_argument(
        "--min", type=int, default=10, metavar="PCT",
        help="Percent of the limit that must remain (default: 10)",
    )
    parser.add_argument(
        "--provider", action="append", metavar="ID",
        help="Check this provider; repeatable (default: all enabled)",
    )
    parser.add_argument(
        "--any", action="store_true",
        help="Pass when any provider has headroom, not every one",
    )
    parser.add_argument(
        "--fail-on-unknown", action="store_true",
        help="Treat a provider with no readable limit as a failure",
    )
    parser.add_argument("--quiet", action="store_true", help="Say nothing; exit code only")
    parser.add_argument("--live", action="store_true", help="Fetch instead of reading state")


def _add_best_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "best",
        help="Print the provider with the most quota left",
        description=(
            "Print the id of the provider with the most headroom, for picking a "
            "tool to start work in. Rows borrowing another account's meters are "
            "skipped, so one subscription cannot be recommended twice."
        ),
    )
    parser.add_argument(
        "--explain", action="store_true", help="Print a sentence instead of an id"
    )
    parser.add_argument("--live", action="store_true", help="Fetch instead of reading state")


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
    _add_check_parser(sub)
    _add_best_parser(sub)
    sub.add_parser("config", help="Print config file path and contents")

    args = parser.parse_args(argv)
    if args.command == "setup":
        return run_setup()
    if args.command == "status":
        return cmd_status(args)
    if args.command == "check":
        return cmd_check(args)
    if args.command == "best":
        return cmd_best(args)
    if args.command == "config":
        return cmd_show_config(args)
    if args.command == "run" or args.command is None:
        from .daemon import run_daemon

        return run_daemon(MonitorConfig.load())

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
