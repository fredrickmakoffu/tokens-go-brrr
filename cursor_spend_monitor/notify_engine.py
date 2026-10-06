"""Turn the ledger into messages a person would actually want to read.

Two clocks produce them. A **schedule** (daily, weekly, monthly) reads the
rollups and writes a digest: totals, the top project, the top model, a fun fact,
an occasional shareable line. **Events** watch the live meters and speak up when
something is about to run out: a limit close to spent, a window that reset hot,
a burn rate that will exhaust before it resets.

Everything here works with **no LLM at all**. Templates are the whole wording
layer for now, which means the triggers, the mixer, the cooldowns and the
delivery can all be verified before a model is anywhere near the loop; a later
step replaces the wording and nothing else.

The rules this module will not break:

* **Numbers only, from the ledger.** No transcript text is ever assembled into a
  prompt or a message, so nothing private can leak into one.
* **Never invent a figure.** Every number in a message comes from a ledger query
  or a provider's own meter. When a period has no data, the message says so.
* **Say when a number is an estimate.** `sources_in` is consulted, and a period
  that includes an `estimate` row says so in the body.
* **A message is a notification, never an action.** Nothing here spends money,
  types into a terminal, or approves anything on the user's behalf.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from . import ledger

# Message families, matching `notify.types` in the config.
INFORMATIVE = "informative"
FUN = "fun"
ACTIONABLE = "actionable"
SHAREABLE = "shareable"

# Meters at or above this are worth an immediate message.
WARN_AT = 90
SPENT_AT = 100

# One message per (kind, key) inside this window. Long enough that a meter
# hovering at a threshold cannot repeat itself every poll.
DEFAULT_COOLDOWN_SECONDS = 6 * 3600


# -- coercion ----------------------------------------------------------------
#
# A meter's percentage and a rollup's totals come from JSON written by someone
# else, so a figure is never trusted to be the type it should be.


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _pct(value: Any) -> int:
    """A percentage as a whole number, tolerating junk."""
    return _as_int(round(_as_float(value)))


@dataclass
class Message:
    """One generated notification, ready to store and deliver."""

    kind: str
    key: str
    body: str
    share: str = ""
    provider: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


# -- ranges ------------------------------------------------------------------


def _utc_today(now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc)


def day_range(days: int, *, now: datetime | None = None) -> tuple[str, str]:
    """The last `days` UTC days, inclusive of today."""
    today = _utc_today(now).date()
    return (today - timedelta(days=max(1, days) - 1)).isoformat(), today.isoformat()


def month_range(now: datetime | None = None, *, offset: int = 0) -> tuple[str, str]:
    """A calendar month, `offset` months back, as inclusive day strings.

    The calendar month is the anchor the design settled on: it is the period a
    person compares against, and per-provider billing cycles only make sense
    inside that provider's own breakdown.
    """
    today = _utc_today(now).date()
    first = today.replace(day=1)
    for _ in range(offset):
        first = (first - timedelta(days=1)).replace(day=1)
    last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    if offset == 0:
        last = today
    return first.isoformat(), last.isoformat()


# -- facts -------------------------------------------------------------------


def _ranked_providers(con: sqlite3.Connection, start: str, end: str) -> list[dict]:
    return ledger.period_totals(con, start_day=start, end_day=end, group_by="provider")


def _top(con: sqlite3.Connection, start: str, end: str, group_by: str) -> dict | None:
    rows = ledger.period_totals(
        con, start_day=start, end_day=end, group_by=group_by, limit=1
    )
    return rows[0] if rows else None


def _estimate_note(con: sqlite3.Connection, start: str, end: str) -> str:
    sources = ledger.sources_in(con, start_day=start, end_day=end)
    return " (includes an estimate)" if "estimate" in sources else ""


def digest_facts(
    con: sqlite3.Connection, *, start: str, end: str, period: str
) -> dict[str, Any]:
    """Every number a digest is allowed to use, in one place."""
    totals = ledger.totals(con, start_day=start, end_day=end)
    ranked = _ranked_providers(con, start, end)
    return {
        "period": period,
        "start_day": start,
        "end_day": end,
        "totals": totals,
        "ranked": ranked,
        "top_project": _top(con, start, end, "project"),
        "top_model": _top(con, start, end, "model"),
        "cache": ledger.cache_share(con, start_day=start, end_day=end),
        "streaks": ledger.streaks(con),
        "records": ledger.records(con, start_day=start, end_day=end),
        "shape": ledger.session_shape(con, start_day=start, end_day=end),
        "estimate_note": _estimate_note(con, start, end),
    }


# -- wording -----------------------------------------------------------------


def _provider_share(facts: dict[str, Any]) -> str:
    ranked = facts["ranked"]
    total = facts["totals"]["tokens"]
    if not ranked or not total:
        return ""
    leader = ranked[0]
    share = _pct(100 * _as_float(leader["tokens"]) / total)
    return f" {leader['provider']} carried {share}%"


def render_digest(facts: dict[str, Any], *, headline: str) -> str:
    """The informative digest, in one or two sentences."""
    totals = facts["totals"]
    if not totals["sessions"]:
        return f"{headline}: no AI sessions recorded yet."
    parts = [
        f"{headline}: {totals['sessions']} sessions, "
        f"{ledger.format_tokens(totals['tokens'])} tokens"
    ]
    share = _provider_share(facts)
    if share:
        parts.append(share.strip())
    if facts["top_project"] and facts["top_project"]["project"]:
        project = facts["top_project"]
        parts.append(
            f"top project {project['project']} ({project['sessions']} sessions, "
            f"{ledger.format_tokens(project['tokens'])} tokens)"
        )
    if facts["top_model"] and facts["top_model"]["model"]:
        parts.append(f"most used {facts['top_model']['model']}")
    body = ". ".join(part for part in parts if part) + "."
    return body + facts["estimate_note"]


def render_fun(facts: dict[str, Any]) -> str | None:
    """One odd-but-true observation, whichever the ledger supports best."""
    cache = facts["cache"]
    if cache["tokens"] and cache["share"] >= 0.5:
        return (
            f"{_pct(cache['share'] * 100)}% of your input tokens came from "
            f"cache reads — {ledger.format_tokens(cache['cache_read_tokens'])} "
            "reused instead of re-sent."
        )
    streaks = facts["streaks"]
    if streaks["current"] >= 3:
        return (
            f"{streaks['current']} days in a row with at least one AI session. "
            f"Your longest run is {streaks['longest']}."
        )
    longest = facts["records"].get("longest_session")
    if longest and longest.get("duration_s"):
        minutes = _as_int(longest["duration_s"]) // 60
        return (
            f"Your longest single session was {minutes // 60}h {minutes % 60}m "
            f"in {longest.get('project') or 'one project'}."
        )
    return None


def render_share(facts: dict[str, Any]) -> str | None:
    """A one-line, copy-paste-ready post about the user's own work."""
    totals = facts["totals"]
    if not totals["sessions"]:
        return None
    model = facts["top_model"]["model"] if facts["top_model"] else None
    lead = (
        f"SHARE: This month I ran {totals['sessions']} AI coding sessions and "
        f"{ledger.format_tokens(totals['tokens'])} tokens"
    )
    if model:
        lead += f". {model} did most of the heavy lifting"
    return lead + "."


def render_actionable(
    *, provider: str, label: str, percent: float, eta: str, better: str
) -> str:
    """The wind-down message: what is nearly spent, and where to go instead."""
    if percent >= SPENT_AT:
        opening = f"{provider} {label} is spent."
    else:
        opening = f"{provider} {label} is at {_pct(percent)}%"
        if eta:
            opening += f", spent in about {eta}"
        opening += "."
    if better:
        return f"{opening} {better} has room — start the handoff there."
    return opening


# -- digests -----------------------------------------------------------------


def daily_digest(
    con: sqlite3.Connection, *, now: datetime | None = None
) -> Message | None:
    start, end = day_range(1, now=now)
    facts = digest_facts(con, start=start, end=end, period="today")
    if not facts["totals"]["sessions"]:
        return None
    return Message(
        kind=INFORMATIVE,
        key=f"daily:{start}",
        body=render_digest(facts, headline="Today"),
        meta={"period": "daily"},
    )


def weekly_digest(
    con: sqlite3.Connection, *, now: datetime | None = None
) -> Message | None:
    start, end = day_range(7, now=now)
    facts = digest_facts(con, start=start, end=end, period="last 7 days")
    if not facts["totals"]["sessions"]:
        return None
    return Message(
        kind=INFORMATIVE,
        key=f"weekly:{end}",
        body=render_digest(facts, headline="Last week"),
        meta={"period": "weekly"},
    )


def monthly_digest(
    con: sqlite3.Connection, *, now: datetime | None = None
) -> Message | None:
    start, end = month_range(now)
    facts = digest_facts(con, start=start, end=end, period="this month")
    if not facts["totals"]["sessions"]:
        return None
    body = render_digest(facts, headline="This month")

    previous_start, previous_end = month_range(now, offset=1)
    previous = ledger.totals(con, start_day=previous_start, end_day=previous_end)
    if previous["tokens"]:
        change = (
            100 * (facts["totals"]["tokens"] - previous["tokens"]) / previous["tokens"]
        )
        direction = "up" if change >= 0 else "down"
        body += f" That is {direction} {abs(_pct(change))}% vs last month."
    return Message(
        kind=INFORMATIVE,
        key=f"monthly:{start}",
        body=body,
        meta={"period": "monthly"},
    )


def fun_fact(con: sqlite3.Connection, *, now: datetime | None = None) -> Message | None:
    start, end = day_range(7, now=now)
    facts = digest_facts(con, start=start, end=end, period="last 7 days")
    body = render_fun(facts)
    if not body:
        return None
    return Message(kind=FUN, key=f"fun:{end}", body=body)


def share_line(
    con: sqlite3.Connection, *, now: datetime | None = None
) -> Message | None:
    start, end = month_range(now)
    facts = digest_facts(con, start=start, end=end, period="this month")
    share = render_share(facts)
    if not share:
        return None
    return Message(
        kind=SHAREABLE,
        key=f"share:{start}",
        body=share.removeprefix("SHARE: ").strip(),
        share=share,
    )


def scheduled_messages(
    con: sqlite3.Connection, *, slot: str, now: datetime | None = None
) -> list[Message]:
    """The messages one scheduled slot should produce.

    The mixer from the design: a digest is always the point of the slot; a fun
    fact and a shareable line ride along at the cadences they suit.
    """
    builders = {
        "daily": [daily_digest, fun_fact],
        "weekly": [weekly_digest, fun_fact],
        "monthly": [monthly_digest, share_line],
    }
    messages: list[Message] = []
    for builder in builders.get(slot, []):
        message = builder(con, now=now)
        if message is not None:
            messages.append(message)
    return messages


# -- events ------------------------------------------------------------------


def _best_headroom(snapshots: list[Any], *, exclude: str) -> str:
    """The provider with the most room, as a name worth naming.

    Borrowed rows are skipped: they are a second view of a subscription that is
    already counted under its own provider.
    """
    best: tuple[float, str] | None = None
    for snap in snapshots:
        if snap.provider_id == exclude or snap.status != "ok":
            continue
        if snap.borrowed_from is not None or not snap.metrics:
            continue
        headroom = 100.0 - _as_float(snap.primary.percent)
        if best is None or headroom > best[0]:
            best = (headroom, snap.display_name)
    return best[1] if best else ""


def event_messages(
    snapshots: list[Any], *, wind_down_hours: float = 2.0
) -> list[Message]:
    """Actionable messages for the meters that need one right now.

    Two triggers: a meter at or past the warning line, and a burn-rate ETA that
    lands before the window resets. Percent alone is not enough — a meter at 80%
    with two hours left in the window is fine, and one at 40% burning fast is
    not, which is exactly what the ETA is for.
    """
    messages: list[Message] = []
    for snap in snapshots:
        if snap.status != "ok" or snap.borrowed_from is not None:
            continue
        for meter in snap.metrics:
            eta_seconds = meter.eta_seconds
            burning_out = (
                eta_seconds is not None
                and eta_seconds <= max(0.0, wind_down_hours) * 3600
            )
            if meter.percent < WARN_AT and not burning_out:
                continue
            eta_label = _eta_label(eta_seconds)
            messages.append(
                Message(
                    kind=ACTIONABLE,
                    key=f"meter:{snap.provider_id}:{meter.key}:{_as_int(meter.percent)}",
                    provider=snap.provider_id,
                    body=render_actionable(
                        provider=snap.display_name,
                        label=meter.label,
                        percent=meter.percent,
                        eta=eta_label,
                        better=_best_headroom(snapshots, exclude=snap.provider_id),
                    ),
                    meta={
                        "meter": meter.key,
                        "percent": round(_as_float(meter.percent), 1),
                    },
                )
            )
    return messages


def _eta_label(eta_seconds: float | None) -> str:
    if not eta_seconds or eta_seconds <= 0:
        return ""
    minutes = _as_int(eta_seconds) // 60
    if minutes < 60:
        return f"{max(1, minutes)}m"
    hours, rem = divmod(minutes, 60)
    return f"{hours}h {rem}m" if rem else f"{hours}h"


# -- cooldowns ---------------------------------------------------------------


def due(con: sqlite3.Connection, message: Message, *, cooldown_seconds: int) -> bool:
    """True when this `(kind, key)` has not been said inside the cooldown."""
    age = ledger.last_message_age(con, kind=message.kind, key=message.key)
    if age is None:
        return True
    return age >= max(0, cooldown_seconds)


def keep(
    con: sqlite3.Connection, messages: list[Message], *, cooldown_seconds: int
) -> list[Message]:
    """Store the messages and return only the ones worth delivering now."""
    fresh: list[Message] = []
    for message in messages:
        if not due(con, message, cooldown_seconds=cooldown_seconds):
            continue
        ledger.store_message(
            con,
            kind=message.kind,
            key=message.key,
            body=message.body,
            provider=message.provider or None,
            share=message.share or None,
            meta=message.meta or None,
        )
        fresh.append(message)
    return fresh
