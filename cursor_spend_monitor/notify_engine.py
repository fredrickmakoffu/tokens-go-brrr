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

import json
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

# How much a message deserves to interrupt, and how long it stays worth it. The
# landing page picks one message by this order, so an actionable warning always
# outranks a curiosity, and a stale digest stops nagging on its own.
PRIORITY = {ACTIONABLE: 3, INFORMATIVE: 2, SHAREABLE: 1, FUN: 0}
FRESHNESS_HOURS = {ACTIONABLE: 6, INFORMATIVE: 24, SHAREABLE: 24, FUN: 12}

# A cheaper provider is only the story if it is doing real work. Without a
# floor, one cheap session would outrank a month of heavy use.
VALUE_SHARE_FLOOR = 0.20


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


def _epoch(now: datetime | None = None) -> int:
    try:
        return int((now or datetime.now(timezone.utc)).timestamp())
    except (OSError, OverflowError, ValueError):
        return 0


def _meta_of(row: dict[str, Any]) -> dict[str, Any]:
    """A stored message's `meta` column, parsed, or an empty dict."""
    raw = row.get("meta")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def provider_label(provider_id: str) -> str:
    """A provider id's display name, taken from the provider classes themselves.

    Not a second copy of the names: the providers are already the source of
    truth for what each one is called.
    """
    from .providers import PROVIDERS

    cls = PROVIDERS.get(provider_id)
    if cls is None:
        return provider_id
    return str(getattr(cls, "display_name", provider_id))


def _featured_meta(featured: dict[str, str] | None, **extra: Any) -> dict[str, Any]:
    """Message meta carrying who the message is about, and why."""
    meta: dict[str, Any] = dict(extra)
    if featured:
        meta["providerName"] = featured.get("name", "")
        meta["role"] = featured.get("role", "")
        meta["reason"] = featured.get("reason", "")
    return meta


def expires_at_for(kind: str, created_at: int) -> int | None:
    """When a message stops being worth interrupting for, or None."""
    hours = FRESHNESS_HOURS.get(kind)
    return created_at + _as_int(hours * 3600) if hours else None


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
    con: sqlite3.Connection,
    *,
    start: str,
    end: str,
    period: str,
    now: datetime | None = None,
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
        "streaks": ledger.streaks(con, now=now),
        "records": ledger.records(con, start_day=start, end_day=end),
        "shape": ledger.session_shape(con, start_day=start, end_day=end),
        "estimate_note": _estimate_note(con, start, end),
    }


# -- wording -----------------------------------------------------------------


def featured_provider(facts: dict[str, Any]) -> dict[str, str] | None:
    """The AI a period is really about, read out of the ledger.

    Never a fixed mapping. The featured AI is whichever provider the numbers say
    matters, decided by two questions in order: which one carried the period,
    and whether some cheaper provider did enough work to be the more interesting
    answer. "Most use for the least spend" is the thing worth telling someone,
    so a value provider wins when it clears the share floor; otherwise the
    leader does.
    """
    ranked = [row for row in (facts.get("ranked") or []) if _as_int(row.get("tokens"))]
    if not ranked:
        return None
    total = sum(_as_int(row.get("tokens")) for row in ranked) or 1
    leader = max(ranked, key=lambda row: _as_int(row.get("tokens")))

    best_value: tuple[float, dict] | None = None
    for row in ranked:
        cost = _as_float(row.get("cost_usd"))
        share = _as_int(row.get("tokens")) / total
        if cost <= 0 or share < VALUE_SHARE_FLOOR:
            continue
        ratio = _as_int(row.get("tokens")) / cost
        if best_value is None or ratio > best_value[0]:
            best_value = (ratio, row)

    if best_value is not None and best_value[1].get("provider") != leader.get(
        "provider"
    ):
        row = best_value[1]
        provider_id = str(row.get("provider") or "")
        return {
            "providerId": provider_id,
            "name": provider_label(provider_id),
            "role": "value",
            "reason": (
                f"{ledger.format_tokens(row.get('tokens'))} tokens for "
                f"{ledger.format_cost(row.get('cost_usd'))}"
            ),
        }

    provider_id = str(leader.get("provider") or "")
    return {
        "providerId": provider_id,
        "name": provider_label(provider_id),
        "role": "leading",
        "reason": (
            f"{_pct(100 * _as_int(leader.get('tokens')) / total)}% "
            "of the period's tokens"
        ),
    }


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
    facts = digest_facts(con, start=start, end=end, period="today", now=now)
    if not facts["totals"]["sessions"]:
        return None
    return Message(
        kind=INFORMATIVE,
        key=f"daily:{start}",
        body=render_digest(facts, headline="Today"),
        provider=featured["providerId"]
        if (featured := featured_provider(facts))
        else "",
        meta=_featured_meta(featured, period="daily"),
    )


def weekly_digest(
    con: sqlite3.Connection, *, now: datetime | None = None
) -> Message | None:
    start, end = day_range(7, now=now)
    facts = digest_facts(con, start=start, end=end, period="last 7 days", now=now)
    if not facts["totals"]["sessions"]:
        return None
    return Message(
        kind=INFORMATIVE,
        key=f"weekly:{end}",
        body=render_digest(facts, headline="Last week"),
        provider=featured["providerId"]
        if (featured := featured_provider(facts))
        else "",
        meta=_featured_meta(featured, period="weekly"),
    )


def monthly_digest(
    con: sqlite3.Connection, *, now: datetime | None = None
) -> Message | None:
    start, end = month_range(now)
    facts = digest_facts(con, start=start, end=end, period="this month", now=now)
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
        provider=featured["providerId"]
        if (featured := featured_provider(facts))
        else "",
        meta=_featured_meta(featured, period="monthly"),
    )


def fun_fact(con: sqlite3.Connection, *, now: datetime | None = None) -> Message | None:
    start, end = day_range(7, now=now)
    facts = digest_facts(con, start=start, end=end, period="last 7 days", now=now)
    body = render_fun(facts)
    if not body:
        return None
    featured = featured_provider(facts)
    return Message(
        kind=FUN,
        key=f"fun:{end}",
        body=body,
        provider=featured["providerId"] if featured else "",
        meta=_featured_meta(featured, period="fun"),
    )


def share_line(
    con: sqlite3.Connection, *, now: datetime | None = None
) -> Message | None:
    start, end = month_range(now)
    facts = digest_facts(con, start=start, end=end, period="this month", now=now)
    share = render_share(facts)
    if not share:
        return None
    return Message(
        kind=SHAREABLE,
        key=f"share:{start}",
        body=share.removeprefix("SHARE: ").strip(),
        share=share,
        provider=featured["providerId"]
        if (featured := featured_provider(facts))
        else "",
        meta=_featured_meta(featured, period="share"),
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


def _best_room(snapshots: list[Any], *, exclude: str) -> dict[str, str] | None:
    """The provider with the most room, as a featured suggestion.

    Borrowed rows are skipped: they are a second view of a subscription already
    counted under its own provider. This is read from live headroom, so the AI
    named here is whichever one actually has capacity right now.
    """
    best: tuple[float, Any] | None = None
    for snap in snapshots:
        if snap.provider_id == exclude or snap.status != "ok":
            continue
        if snap.borrowed_from is not None or not snap.metrics:
            continue
        headroom = 100.0 - _as_float(snap.primary.percent)
        if best is None or headroom > best[0]:
            best = (headroom, snap)
    if best is None:
        return None
    headroom, snap = best
    return {
        "providerId": str(snap.provider_id),
        "name": str(snap.display_name),
        "role": "suggested",
        "reason": f"{_pct(headroom)}% left",
    }


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
            featured = _best_room(snapshots, exclude=snap.provider_id)
            messages.append(
                Message(
                    kind=ACTIONABLE,
                    key=f"meter:{snap.provider_id}:{meter.key}:{_as_int(meter.percent)}",
                    provider=(featured["providerId"] if featured else snap.provider_id),
                    body=render_actionable(
                        provider=snap.display_name,
                        label=meter.label,
                        percent=meter.percent,
                        eta=eta_label,
                        better=featured["name"] if featured else "",
                    ),
                    meta=_featured_meta(
                        featured,
                        meter=meter.key,
                        percent=round(_as_float(meter.percent), 1),
                        trigger=snap.provider_id,
                    ),
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


# -- the landing page --------------------------------------------------------


def billboard_payload(row: dict[str, Any]) -> dict[str, Any]:
    """The state shape the panel renders for one stored message."""
    meta = _meta_of(row)
    kind = str(row.get("kind") or "")
    created = _as_int(row.get("created_at"))
    provider = str(row.get("provider") or "")
    featured = (
        {
            "providerId": provider,
            "name": str(meta.get("providerName") or provider_label(provider)),
            "role": str(meta.get("role") or "featured"),
        }
        if provider
        else None
    )
    return {
        "id": _as_int(row.get("id")),
        "kind": kind,
        "priority": PRIORITY.get(kind, 0),
        "text": str(row.get("body") or ""),
        "share": str(row.get("share") or ""),
        "featured": featured,
        "createdAt": created,
        "expiresAt": expires_at_for(kind, created),
        "reason": str(meta.get("reason") or ""),
    }


def choose_billboard(
    rows: list[dict[str, Any]], *, now: datetime | None = None
) -> dict[str, Any] | None:
    """The one message worth interrupting for, or None.

    Priority first, newest second, and only while the message is still fresh.
    `rows` are unacknowledged messages; acknowledgement is the database's job,
    so nothing already read can reach this point.
    """
    now_ts = _epoch(now)
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for row in rows:
        created = _as_int(row.get("created_at"))
        expires = expires_at_for(str(row.get("kind") or ""), created)
        if expires is not None and expires <= now_ts:
            continue
        candidates.append((PRIORITY.get(str(row.get("kind")), 0), created, row))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return billboard_payload(candidates[0][2])


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
