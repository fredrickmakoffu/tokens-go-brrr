from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

from . import __version__, harvesters, ledger, notify_engine
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
            lines.append(
                f"{tool.get('name', '?')}: {tool.get('error') or tool.get('status')}"
            )
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
        lines.append(
            "Fetched directly; daemon not running, so sessions are not counted."
        )
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
        return (
            f"on {via.get('name', 'another account')}, counted under {via.get('from')}"
        )
    if tool.get("error"):
        return str(tool["error"])
    if not tool.get("metrics"):
        return "no limits reported"
    return str(tool.get("status", "unknown"))


def _metric_percent(tool: dict[str, Any]) -> int:
    """The primary meter's percent as an int.

    The payload is JSON written by the daemon, so `value` can be a string in a
    hand-edited or older state file. Treating that as 0 keeps `check` and
    `best` answering instead of raising on a file they did not write.
    """
    try:
        return int(primary_metric(tool).get("value", 0))
    except (TypeError, ValueError):
        return 0


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
        print(
            f"No provider matched {', '.join(sorted(set(args.provider)))}.",
            file=sys.stderr,
        )
        return 2

    known = [t for t in tools if _measurable(t)]
    unknown = [t for t in tools if t not in known]

    if not known:
        if not args.quiet:
            names = ", ".join(t.get("name", "?") for t in unknown) or "nothing enabled"
            print(f"No usable meters ({names}).", file=sys.stderr)
        return 2

    results = [(t, 100 - _metric_percent(t)) for t in known]
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

    ranked = sorted(candidates, key=_metric_percent)
    winner = ranked[0]

    if not args.explain:
        print(winner.get("id", ""))
        return 0

    headroom = 100 - _metric_percent(winner)
    others = ", ".join(
        f"{t.get('name')} {100 - _metric_percent(t)}% left" for t in ranked[1:]
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


# -- report ------------------------------------------------------------------

# Which key columns name a row for each grouping. Kept explicit so the text
# output never has to guess what a row is about.
REPORT_KEYS = {
    "provider": ("provider",),
    "project": ("project",),
    "model": ("model",),
    "provider_model": ("provider", "model"),
    "project_model": ("project", "model"),
    "day": ("day",),
    "hour": ("day", "hour"),
}


def _as_day(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"{label} must be YYYY-MM-DD, got {value!r}") from exc


def _report_days(args: argparse.Namespace) -> tuple[str, str]:
    """The inclusive day range the report covers.

    A calendar month is the default because that is the period a person
    compares; per-provider billing cycles only make sense inside one
    provider's own breakdown.
    """
    today = datetime.now(timezone.utc).date()
    if args.since or args.until:
        if not (args.since and args.until):
            raise SystemExit("Give both --since and --until, or neither.")
        start = _as_day(args.since, "--since")
        end = _as_day(args.until, "--until")
        if start > end:
            raise SystemExit("--since is after --until.")
        return start.isoformat(), end.isoformat()
    if args.week:
        start = today - timedelta(days=6)
    elif args.days:
        start = today - timedelta(days=max(1, args.days) - 1)
    else:
        start = today.replace(day=1)
    return start.isoformat(), today.isoformat()


def _format_ts(epoch: Any) -> str:
    try:
        return datetime.fromtimestamp(int(epoch), timezone.utc).strftime(
            "%Y-%m-%d %H:%M"
        )
    except (TypeError, ValueError, OSError, OverflowError):
        return "—"


def _row_label(group_by: str, row: dict[str, Any]) -> str:
    parts = [str(row.get(key, "")) for key in REPORT_KEYS[group_by]]
    if group_by == "hour":
        try:
            hour = int(row.get("hour", 0))
        except (TypeError, ValueError):
            hour = 0
        return f"{parts[0]} {hour:02d}:00"
    return " · ".join(parts)


def _render_report(
    args: argparse.Namespace,
    con: Any,
    start: str,
    end: str,
) -> str:
    totals = ledger.totals(con, start_day=start, end_day=end)
    rows = ledger.period_totals(
        con,
        start_day=start,
        end_day=end,
        group_by=args.by,
        provider=args.provider,
        limit=args.limit,
    )
    sources = ledger.sources_in(con, start_day=start, end_day=end)

    lines = [f"Usage {start} to {end}" if start != end else f"Usage {start}"]
    summary = (
        f"  {totals['sessions']} sessions · "
        f"{ledger.format_tokens(totals['tokens'])} tokens · "
        f"{ledger.format_cost(totals['cost_usd'])}"
    )
    if totals["estimated_sessions"]:
        summary += f" · {totals['estimated_sessions']} estimated"
    lines.append(summary)

    if not rows:
        lines.append("")
        lines.append("  No sessions recorded in this period.")
        return "\n".join(lines)

    lines.append("")
    width = min(34, max(len(_row_label(args.by, row)) for row in rows))
    for row in rows:
        lines.append(
            f"  {_row_label(args.by, row):<{width}}  {row['sessions']:>4} sessions"
            f"  {ledger.format_tokens(row['tokens']):>7} tokens"
            f"  {ledger.format_cost(row['cost_usd']):>9}"
        )

    if args.by == "provider":
        for kind in ("project", "model"):
            top = ledger.period_totals(
                con,
                start_day=start,
                end_day=end,
                group_by=kind,
                provider=args.provider,
                limit=1,
            )
            if top and top[0][kind]:
                lines.append("")
                lines.append(
                    f"  top {kind}: {top[0][kind]} — {top[0]['sessions']} sessions, "
                    f"{ledger.format_tokens(top[0]['tokens'])} tokens"
                )

    if "estimate" in sources:
        lines.append("")
        lines.append("  Includes estimated sessions (source: estimate).")
    return "\n".join(lines)


def _report_json(
    args: argparse.Namespace,
    con: Any,
    start: str,
    end: str,
) -> dict[str, Any]:
    return {
        "start_day": start,
        "end_day": end,
        "by": args.by,
        "provider": args.provider,
        "totals": ledger.totals(con, start_day=start, end_day=end),
        "sources": ledger.sources_in(con, start_day=start, end_day=end),
        "rows": ledger.period_totals(
            con,
            start_day=start,
            end_day=end,
            group_by=args.by,
            provider=args.provider,
            limit=args.limit,
        ),
    }


def cmd_report(args: argparse.Namespace) -> int:
    con = ledger.connect()
    try:
        if args.checks:
            rows = ledger.recent_checks(con, limit=args.limit)
            if args.json:
                print(json.dumps(rows, indent=2))
                return 0
            if not rows:
                print("No cross-checks recorded.")
                return 0
            for row in rows:
                mark = "ok  " if row["ok"] else "FAIL"
                detail = f"  {row['detail']}" if row["detail"] else ""
                print(
                    f"{mark} {_format_ts(row['checked_at'])}  "
                    f"{row['provider']}  {row['kind']}{detail}"
                )
            return 0

        start, end = _report_days(args)
        if args.json:
            print(json.dumps(_report_json(args, con, start, end), indent=2))
        else:
            print(_render_report(args, con, start, end))
        return 0
    finally:
        con.close()


# -- harvest -----------------------------------------------------------------


def _print_harvest(
    results: list[harvesters.HarvestResult], removed: dict[str, int], keep_days: int
) -> None:
    for result in results:
        if result.failed:
            print(f"{result.harvester}: {result.note or 'failed'}")
        elif result.note and not result.scanned:
            print(f"{result.harvester}: {result.note}")
        elif not result.changed:
            print(f"{result.harvester}: no change ({result.scanned} scanned)")
        else:
            bits = [f"{result.sessions} sessions"]
            if result.per_model:
                bits.append(f"{result.per_model} model rows")
            if result.folded_days:
                bits.append(f"{result.folded_days} day(s) folded")
            print(f"{result.harvester}: " + ", ".join(bits))
    if removed["sessions"]:
        print(f"pruned {removed['sessions']} sessions older than {keep_days} days")


def cmd_harvest(args: argparse.Namespace) -> int:
    """Read the tools' own stores into the ledger, then roll up."""
    config = MonitorConfig.load()
    con = ledger.connect()
    try:
        try:
            ledger.assert_writable(con)
        except ledger.LedgerTooNewError as exc:
            print(exc, file=sys.stderr)
            return 1

        readers = harvesters.build(args.provider)
        if not readers:
            wanted = ", ".join(sorted(set(args.provider or []))) or "any provider"
            print(f"No harvester reads {wanted}.", file=sys.stderr)
            return 2

        results: list[harvesters.HarvestResult] = []
        for reader in readers:
            if not reader.available():
                results.append(
                    harvesters.HarvestResult(
                        harvester=reader.id,
                        provider=reader.provider,
                        note="not installed",
                    )
                )
                continue
            try:
                results.append(reader.harvest(con, full=args.full))
            except Exception as exc:  # noqa: BLE001 - one reader must not stop the run
                results.append(
                    harvesters.HarvestResult(
                        harvester=reader.id,
                        provider=reader.provider,
                        note=str(exc),
                        failed=True,
                    )
                )

        removed = ledger.prune(con, keep_days=config.ledger_days)
        _print_harvest(results, removed, config.ledger_days)
        return 0 if not any(result.failed for result in results) else 1
    finally:
        con.close()


def _add_harvest_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "harvest",
        help="Read the tools' own stores into the usage ledger",
        description=(
            "Read each installed tool's own session store into the local usage "
            "ledger, then rebuild the daily and hourly rollups.\n\n"
            "Readers are idempotent: a second run with nothing new reports no "
            "change rather than rewriting rows. The local stores need no "
            "network; a locked store is skipped for this run."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  cursor-spend-monitor harvest\n"
            "  cursor-spend-monitor harvest --provider opencode\n"
            "  cursor-spend-monitor harvest --full\n"
        ),
    )
    parser.add_argument(
        "--provider",
        action="append",
        metavar="ID",
        help="Harvest only this provider; repeatable",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Ignore watermarks and re-read every store from the beginning",
    )


# -- quote -------------------------------------------------------------------


def _copy_to_clipboard(text: str) -> bool:
    """Best-effort clipboard copy, so a failed copy never fails the command."""
    for command in (["wl-copy"], ["xclip", "-selection", "clipboard"]):
        if shutil.which(command[0]) is None:
            continue
        try:
            subprocess.run(command, input=text.encode(), check=True, timeout=5)
            return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


def cmd_quote(args: argparse.Namespace) -> int:
    """Print the newest generated message, for a status line or a post.

    Reads the local ledger only. `--generate` builds a fresh digest first, which
    is what makes the command useful before the daemon has run a full day.
    """
    con = ledger.connect()
    try:
        if args.generate:
            messages = notify_engine.scheduled_messages(con, slot=args.slot)
            notify_engine.keep(con, messages, cooldown_seconds=0)
        message = ledger.latest_message(con)
        if message is None:
            print(
                "No message yet. Run `cursor-spend-monitor quote --generate` "
                "or wait for the daemon.",
                file=sys.stderr,
            )
            return 1
        if args.json:
            print(json.dumps(message, indent=2))
            return 0
        if args.tweet:
            line = message.get("share") or ""
            if not line:
                # The newest message may be a fun fact. A share line is a
                # different thing, so one is built rather than reusing prose.
                generated = notify_engine.share_line(con)
                if generated is not None:
                    notify_engine.keep(con, [generated], cooldown_seconds=0)
                    line = generated.share
            if not line:
                line = message.get("body") or ""
            print(line)
            if not args.no_copy and _copy_to_clipboard(line):
                print("(copied to the clipboard)", file=sys.stderr)
            return 0
        print(message.get("body") or "")
        return 0
    finally:
        con.close()


def _add_quote_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "quote",
        help="Print the latest generated message",
        description=(
            "Print the newest message the notification engine produced. Reads "
            "the local ledger only: no credentials, no network.\n\n"
            "With --tweet the shareable line is printed and copied to the "
            "clipboard; nothing is posted anywhere."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  cursor-spend-monitor quote\n"
            "  cursor-spend-monitor quote --generate --slot weekly\n"
            "  cursor-spend-monitor quote --tweet\n"
        ),
    )
    parser.add_argument(
        "--slot",
        default="daily",
        choices=["daily", "weekly", "monthly"],
        help="Which scheduled digest --generate should build (default: daily)",
    )
    parser.add_argument(
        "--generate", action="store_true", help="Build a fresh message before printing"
    )
    parser.add_argument(
        "--tweet", action="store_true", help="Print the SHARE: line and copy it"
    )
    parser.add_argument(
        "--no-copy",
        action="store_true",
        help="With --tweet, do not touch the clipboard",
    )
    parser.add_argument("--json", action="store_true", help="Print the message as JSON")


def _add_report_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "report",
        help="Summarise the usage ledger over a period",
        description=(
            "Summarise recorded AI usage over a period.\n\n"
            "Reads the local ledger only: no credentials, no network. Populate it "
            "with `harvest` first. Defaults to the current calendar month."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  cursor-spend-monitor report\n"
            "  cursor-spend-monitor report --week --by model\n"
            "  cursor-spend-monitor report --since 2026-10-01 --until 2026-10-31 --json\n"
            "  cursor-spend-monitor report --checks\n"
        ),
    )
    parser.add_argument(
        "--days", type=int, metavar="N", help="Last N days, including today"
    )
    parser.add_argument("--week", action="store_true", help="The last 7 days")
    parser.add_argument(
        "--month", action="store_true", help="The current calendar month (default)"
    )
    parser.add_argument("--since", metavar="YYYY-MM-DD", help="First day to include")
    parser.add_argument("--until", metavar="YYYY-MM-DD", help="Last day to include")
    parser.add_argument(
        "--by",
        default="provider",
        choices=sorted(ledger.GROUPINGS),
        metavar="GROUP",
        help="Group by provider | project | model | provider_model | project_model | day | hour",
    )
    parser.add_argument("--provider", metavar="ID", help="Limit to one provider")
    parser.add_argument(
        "--limit", type=int, default=10, metavar="N", help="Rows to show (default: 10)"
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON")
    parser.add_argument(
        "--checks",
        action="store_true",
        help="Show recent cross-checks instead of totals",
    )


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
        "--min",
        type=int,
        default=10,
        metavar="PCT",
        help="Percent of the limit that must remain (default: 10)",
    )
    parser.add_argument(
        "--provider",
        action="append",
        metavar="ID",
        help="Check this provider; repeatable (default: all enabled)",
    )
    parser.add_argument(
        "--any",
        action="store_true",
        help="Pass when any provider has headroom, not every one",
    )
    parser.add_argument(
        "--fail-on-unknown",
        action="store_true",
        help="Treat a provider with no readable limit as a failure",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Say nothing; exit code only"
    )
    parser.add_argument(
        "--live", action="store_true", help="Fetch instead of reading state"
    )


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
    parser.add_argument(
        "--live", action="store_true", help="Fetch instead of reading state"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cursor-spend-monitor",
        description="tokens-go-brrr daemon for the GNOME Shell indicator",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="Verify provider logins (Cursor IDE)")
    sub.add_parser("run", help="Start the usage daemon (foreground)")
    _add_status_parser(sub)
    _add_check_parser(sub)
    _add_best_parser(sub)
    _add_harvest_parser(sub)
    _add_report_parser(sub)
    _add_quote_parser(sub)
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
    if args.command == "harvest":
        return cmd_harvest(args)
    if args.command == "report":
        return cmd_report(args)
    if args.command == "quote":
        return cmd_quote(args)
    if args.command == "config":
        return cmd_show_config(args)
    if args.command == "run" or args.command is None:
        from .daemon import run_daemon

        return run_daemon(MonitorConfig.load())

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
