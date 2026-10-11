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

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .. import ledger
from ..coerce import as_float as _as_float
from ..coerce import as_int as _as_int

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

# The temperatures of the live-notes design (design/LIVE_NOTES_AND_LLM_LOG.md).
# A cold note is a precomputed trend or digest, a warm one describes the last
# hour or two and a hot one is the warm note served again. Only the cold tier
# exists so far; the others are named here so provenance and expiry already
# speak the vocabulary the later steps will fill in.
COLD = "cold"
WARM = "warm"
HOT = "hot"

# How long a note stays worth showing, counted from when its facts were read
# (`as_of`), not from when it was stored. A warm note describes "now", so it
# stops being true quickly; a cold one is a trend and ages slowly.
TIER_FRESHNESS_HOURS = {COLD: 24, WARM: 2, HOT: 2}

# Where a note's wording came from.
SOURCE_TEMPLATE = "template"
SOURCE_LLM = "llm"

# A cheaper provider is only the story if it is doing real work. Without a
# floor, one cheap session would outrank a month of heavy use.
VALUE_SHARE_FLOOR = 0.20


# -- formatting --------------------------------------------------------------


def _pct(value: Any) -> int:
    """A percentage as a whole number, tolerating junk."""
    return _as_int(round(_as_float(value)))


def _epoch(now: datetime | None = None) -> int:
    try:
        return int((now or datetime.now(UTC)).timestamp())
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
    from tokens_go_brrr.providers import PROVIDERS

    cls = PROVIDERS.get(provider_id)
    if cls is None:
        return provider_id
    return str(getattr(cls, "display_name", provider_id))


def _tpl(template_id: str, **params: Any) -> dict[str, Any]:
    """Which template wrote a message, and the values it was filled with.

    The body stays English text, which is what the CLI prints and what a model
    rewrites. The panel renders from this instead when it can, so the same
    message reads in the user's language; a message a model reworded has no
    template to render from (see billboard_payload) and is shown as written.
    """
    return {"id": template_id, "p": params}


def _featured_meta(featured: dict[str, str] | None, **extra: Any) -> dict[str, Any]:
    """Message meta carrying who the message is about, and why."""
    meta: dict[str, Any] = dict(extra)
    if featured:
        meta["providerName"] = featured.get("name", "")
        meta["role"] = featured.get("role", "")
        meta["reason"] = featured.get("reason", "")
    return meta


def expires_at_for(
    kind: str,
    created_at: int,
    *,
    tier: str | None = None,
    as_of: int | None = None,
) -> int | None:
    """When a message stops being worth interrupting for, or None.

    The kind sets one limit (an actionable warning goes stale in hours, a digest
    in a day). A message that knows its tier has a second, counted from when its
    facts were read rather than when it was stored, and the sooner of the two
    wins: a warm note about "the last hour" must not outlive the hour because it
    happens to be an informative one.
    """
    limits: list[int] = []
    hours = FRESHNESS_HOURS.get(kind)
    if hours:
        limits.append(created_at + _as_int(hours * 3600))
    tier_hours = TIER_FRESHNESS_HOURS.get(tier or "")
    if tier_hours:
        limits.append((as_of if as_of else created_at) + _as_int(tier_hours * 3600))
    return min(limits) if limits else None


def provenance(
    *, tier: str, as_of: int, fingerprint: str = "", source: str = SOURCE_TEMPLATE
) -> dict[str, Any]:
    """Where a note came from, for its `meta`.

    `as_of` is when the facts were read, so the panel can say "as of 12 min ago"
    and expiry can count from it. `fingerprint` identifies those facts: a later
    refresh that hashes to the same value has nothing new to say. `source` is
    whether a template or a model wrote the wording.
    """
    return {
        "tier": tier,
        "asOf": as_of,
        "fingerprint": fingerprint,
        "source": source,
    }


def fingerprint_of(*parts: Any) -> str:
    """A short, stable hash of the figures a note was built from."""
    encoded = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:12]


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
    return (now or datetime.now(UTC)).astimezone(UTC)


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


def rolling_range(hours: int, *, now: datetime | None = None) -> tuple[int, int]:
    """The last `hours` hours as inclusive epoch seconds, ending now.

    The calendar-day ranges above answer "this UTC day"; this answers "the last
    24 hours", which is what a person means by recent.
    """
    until = _epoch(now)
    return until - max(1, _as_int(hours)) * 3600, until


# -- facts -------------------------------------------------------------------


def _ranked_providers(con: sqlite3.Connection, start: str, end: str) -> list[dict]:
    return ledger.period_totals(con, start_day=start, end_day=end, group_by="provider")


def _top(con: sqlite3.Connection, start: str, end: str, group_by: str) -> dict | None:
    rows = ledger.period_totals(con, start_day=start, end_day=end, group_by=group_by, limit=1)
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


def rolling_facts(
    con: sqlite3.Connection,
    *,
    hours: int,
    period: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """`digest_facts` for the last `hours` hours instead of a day range.

    The totals, ranking, top project and model, cache share and estimate note
    come from the rolling window. Records, shape and streaks are about days, so
    they keep reading the UTC days that cover the window.
    """
    since, until = rolling_range(hours, now=now)
    start, end = day_range(hours // 24 + 2, now=now)
    facts = digest_facts(con, start=start, end=end, period=period, now=now)
    totals = ledger.rolling_totals(con, since=since, until=until)

    def top(group_by: str) -> dict | None:
        rows = ledger.rolling_period_totals(
            con, since=since, until=until, group_by=group_by, limit=1
        )
        return rows[0] if rows else None

    facts.update(
        {
            "since": since,
            "until": until,
            "totals": totals,
            "ranked": ledger.rolling_period_totals(
                con, since=since, until=until, group_by="provider"
            ),
            "top_project": top("project"),
            "top_model": top("model"),
            "cache": {
                "tokens": totals["tokens"],
                "cache_read_tokens": totals["cache_read_tokens"],
                "share": (
                    totals["cache_read_tokens"] / totals["tokens"] if totals["tokens"] else 0.0
                ),
            },
            "estimate_note": (" (includes an estimate)" if totals["estimated_sessions"] else ""),
        }
    )
    return facts


def digest_fingerprint(facts: dict[str, Any]) -> str:
    """The figures a digest was built from, hashed."""
    totals = facts["totals"]
    return fingerprint_of(
        facts["period"],
        totals["sessions"],
        totals["tokens"],
        [(r["provider"], r["tokens"]) for r in facts["ranked"]],
    )


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

    if best_value is not None and best_value[1].get("provider") != leader.get("provider"):
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
        "reason": (f"{_pct(100 * _as_int(leader.get('tokens')) / total)}% of the period's tokens"),
    }


def _provider_share(facts: dict[str, Any]) -> str:
    ranked = facts["ranked"]
    total = facts["totals"]["tokens"]
    if not ranked or not total:
        return ""
    leader = ranked[0]
    share = _pct(100 * _as_float(leader["tokens"]) / total)
    return f" {leader['provider']} carried {share}%"


def digest_params(
    facts: dict[str, Any], *, period: str, vs_last_month: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The values render_digest puts in its sentence, for a translated rendering."""
    totals = facts["totals"]
    ranked = facts["ranked"]
    leader = None
    if ranked and totals["tokens"]:
        leader = {
            "name": provider_label(str(ranked[0]["provider"])),
            "pct": _pct(100 * _as_float(ranked[0]["tokens"]) / totals["tokens"]),
        }
    project = facts["top_project"] if facts["top_project"] else None
    model = facts["top_model"] if facts["top_model"] else None
    return {
        "period": period,
        "sessions": _as_int(totals["sessions"]),
        "tokens": _as_int(totals["tokens"]),
        "leader": leader,
        "topProject": (
            {
                "project": project["project"],
                "sessions": _as_int(project["sessions"]),
                "tokens": _as_int(project["tokens"]),
            }
            if project and project["project"]
            else None
        ),
        "topModel": model["model"] if model and model["model"] else None,
        "estimate": bool(facts["estimate_note"]),
        "vsLastMonth": vs_last_month,
    }


def fun_params(facts: dict[str, Any]) -> dict[str, Any] | None:
    """Which fun fact render_fun picked, and its values, as a template."""
    cache = facts["cache"]
    if cache["tokens"] and cache["share"] >= 0.5:
        return _tpl(
            "fun.cache",
            pct=_pct(cache["share"] * 100),
            tokens=_as_int(cache["cache_read_tokens"]),
        )
    streaks = facts["streaks"]
    if streaks["current"] >= 3:
        return _tpl(
            "fun.streak",
            current=_as_int(streaks["current"]),
            longest=_as_int(streaks["longest"]),
        )
    longest = facts["records"].get("longest_session")
    if longest and longest.get("duration_s"):
        return _tpl(
            "fun.longest",
            minutes=_as_int(longest["duration_s"]) // 60,
            project=longest.get("project") or "",
        )
    return None


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


def render_actionable(*, provider: str, label: str, percent: float, eta: str, better: str) -> str:
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


def daily_digest(con: sqlite3.Connection, *, now: datetime | None = None) -> Message | None:
    """The last 24 hours, not the calendar day.

    A calendar day made work done at 17:00 "yesterday" by the next morning, so
    the note read as old news; a rolling window keeps it true until it ages out.
    """
    facts = rolling_facts(con, hours=24, period="last 24 hours", now=now)
    if not facts["totals"]["sessions"]:
        return None
    today = day_range(1, now=now)[0]
    return Message(
        kind=INFORMATIVE,
        key=f"daily:{today}",
        body=render_digest(facts, headline="Last 24h"),
        provider=featured["providerId"] if (featured := featured_provider(facts)) else "",
        meta=_featured_meta(
            featured,
            period="daily",
            tpl=_tpl("digest", **digest_params(facts, period="daily")),
            **provenance(
                tier=COLD,
                as_of=_epoch(now),
                fingerprint=digest_fingerprint(facts),
            ),
        ),
    )


def weekly_digest(con: sqlite3.Connection, *, now: datetime | None = None) -> Message | None:
    start, end = day_range(7, now=now)
    facts = digest_facts(con, start=start, end=end, period="last 7 days", now=now)
    if not facts["totals"]["sessions"]:
        return None
    return Message(
        kind=INFORMATIVE,
        key=f"weekly:{end}",
        body=render_digest(facts, headline="Last week"),
        provider=featured["providerId"] if (featured := featured_provider(facts)) else "",
        meta=_featured_meta(
            featured,
            period="weekly",
            tpl=_tpl("digest", **digest_params(facts, period="weekly")),
            **provenance(
                tier=COLD,
                as_of=_epoch(now),
                fingerprint=digest_fingerprint(facts),
            ),
        ),
    )


def monthly_digest(con: sqlite3.Connection, *, now: datetime | None = None) -> Message | None:
    start, end = month_range(now)
    facts = digest_facts(con, start=start, end=end, period="this month", now=now)
    if not facts["totals"]["sessions"]:
        return None
    body = render_digest(facts, headline="This month")

    previous_start, previous_end = month_range(now, offset=1)
    previous = ledger.totals(con, start_day=previous_start, end_day=previous_end)
    vs_last_month = None
    if previous["tokens"]:
        change = 100 * (facts["totals"]["tokens"] - previous["tokens"]) / previous["tokens"]
        direction = "up" if change >= 0 else "down"
        body += f" That is {direction} {abs(_pct(change))}% vs last month."
        vs_last_month = {"dir": direction, "pct": abs(_pct(change))}
    return Message(
        kind=INFORMATIVE,
        key=f"monthly:{start}",
        body=body,
        provider=featured["providerId"] if (featured := featured_provider(facts)) else "",
        meta=_featured_meta(
            featured,
            period="monthly",
            tpl=_tpl(
                "digest",
                **digest_params(facts, period="monthly", vs_last_month=vs_last_month),
            ),
            **provenance(
                tier=COLD,
                as_of=_epoch(now),
                fingerprint=digest_fingerprint(facts),
            ),
        ),
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
        meta=_featured_meta(featured, period="fun", tpl=fun_params(facts)),
    )


def share_line(con: sqlite3.Connection, *, now: datetime | None = None) -> Message | None:
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
        provider=featured["providerId"] if (featured := featured_provider(facts)) else "",
        meta=_featured_meta(
            featured,
            period="share",
            tpl=_tpl(
                "share",
                sessions=_as_int(facts["totals"]["sessions"]),
                tokens=_as_int(facts["totals"]["tokens"]),
                model=(facts["top_model"] or {}).get("model") or "",
            ),
        ),
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


# -- tiers and the cold insight pool ----------------------------------------


def tier_for(
    idle_seconds: float | None,
    *,
    cold_hours: float = 4.0,
    hot_minutes: float = 10.0,
    last_warm_age: float | None = None,
) -> str:
    """Which temperature an open of the popover is.

    `idle_seconds` is the time since the popover was last opened, or None when
    it never has been in this daemon's life. A first open and a long absence are
    both cold: what the person needs is the shape of their usage, not the last
    hour of it. Inside a working cycle an open is warm, and hot when a warm note
    was made `hot_minutes` ago or less -- the figures cannot have moved enough to
    be worth another look, so the last warm note is served as it is.
    """
    if idle_seconds is None or idle_seconds >= max(0.0, cold_hours) * 3600:
        return COLD
    if last_warm_age is not None and 0 <= last_warm_age < max(0.0, hot_minutes) * 60:
        return HOT
    return WARM


# The insights, in the order ties are broken. Each looks at a trailing window
# and returns nothing when there is too little data for the claim to mean
# anything: a percentage of three sessions is not an insight.
INSIGHT_IDS = ("cache", "week", "peak", "focus", "rhythm")
INSIGHT_WINDOW_DAYS = 30
MIN_INSIGHT_TOKENS = 100_000
MIN_INSIGHT_SESSIONS = 10
HIGH_CACHE_SHARE = 60
FLAT_WEEK_PCT = 5

WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def _insight(
    insight_id: str,
    body: str,
    params: dict[str, Any],
    *,
    now: datetime | None,
    fingerprint_parts: Any,
) -> Message:
    """A cold-tier message for one insight, keyed by the day it was made."""
    today = day_range(1, now=now)[0]
    return Message(
        kind=INFORMATIVE,
        key=f"{INSIGHT_KEY_PREFIX}{insight_id}:{today}",
        body=body,
        meta={
            "period": "insight",
            "insight": insight_id,
            "tpl": _tpl(f"insight.{insight_id}", **params),
            **provenance(
                tier=COLD,
                as_of=_epoch(now),
                fingerprint=fingerprint_of(insight_id, fingerprint_parts),
            ),
        },
    )


INSIGHT_KEY_PREFIX = "insight:"


def insight_cache(con: sqlite3.Connection, *, now: datetime | None = None) -> Message | None:
    start, end = day_range(INSIGHT_WINDOW_DAYS, now=now)
    cache = ledger.cache_share(con, start_day=start, end_day=end)
    if cache["tokens"] < MIN_INSIGHT_TOKENS:
        return None
    pct = _pct(100 * cache["share"])
    high = pct >= HIGH_CACHE_SHARE
    body = f"{pct}% of your tokens in the last {INSIGHT_WINDOW_DAYS} days were cache reads."
    if high:
        body += (
            " That is the cheap kind, but a long thread re-reads its whole history"
            " every turn; a fresh session per task keeps it down."
        )
    else:
        body += " Staying on one task within a session lets the cache do more of the work."
    return _insight(
        "cache",
        body,
        {"pct": pct, "high": high, "days": INSIGHT_WINDOW_DAYS},
        now=now,
        fingerprint_parts=[pct, high],
    )


def insight_week(con: sqlite3.Connection, *, now: datetime | None = None) -> Message | None:
    start, end = day_range(7, now=now)
    before_end = (datetime.fromisoformat(start) - timedelta(days=1)).date().isoformat()
    before_start = (datetime.fromisoformat(start) - timedelta(days=7)).date().isoformat()
    this = ledger.totals(con, start_day=start, end_day=end)["tokens"]
    before = ledger.totals(con, start_day=before_start, end_day=before_end)["tokens"]
    if before < MIN_INSIGHT_TOKENS // 10 or this <= 0:
        return None
    change = 100 * (this - before) / before
    pct = abs(_pct(change))
    if pct < FLAT_WEEK_PCT:
        direction = "flat"
        body = (
            f"Your last 7 days were steady: within {FLAT_WEEK_PCT}% of the 7 before."
            " Same rhythm as last week."
        )
    elif change > 0:
        direction = "up"
        body = (
            f"You used {pct}% more tokens in the last 7 days than in the 7 before."
            " Worth a glance at which project drove it."
        )
    else:
        direction = "down"
        body = (
            f"You used {pct}% fewer tokens in the last 7 days than in the 7 before. A lighter week."
        )
    return _insight(
        "week",
        body,
        {"dir": direction, "pct": pct, "limit": FLAT_WEEK_PCT},
        now=now,
        fingerprint_parts=[direction, pct],
    )


def insight_peak(con: sqlite3.Connection, *, now: datetime | None = None) -> Message | None:
    start, end = day_range(INSIGHT_WINDOW_DAYS, now=now)
    shape = ledger.session_shape(con, start_day=start, end_day=end)
    if shape["sessions"] < MIN_INSIGHT_SESSIONS:
        return None
    hour = max(range(24), key=lambda h: (shape["hours"][h], -h))
    counts = ledger.weekday_counts(con, start_day=start, end_day=end)
    weekday = max(range(7), key=lambda d: (counts[d], -d))
    return _insight(
        "peak",
        f"Most of your AI work happens around {hour:02d}:00, and {WEEKDAYS[weekday]}"
        f" is your busiest day. Plan the heavy sessions for then.",
        {"hour": hour, "weekday": weekday},
        now=now,
        fingerprint_parts=[hour, weekday],
    )


def insight_focus(con: sqlite3.Connection, *, now: datetime | None = None) -> Message | None:
    start, end = day_range(INSIGHT_WINDOW_DAYS, now=now)
    total = ledger.totals(con, start_day=start, end_day=end)["tokens"]
    top = _top(con, start, end, "project")
    if total < MIN_INSIGHT_TOKENS or not top or not top["project"]:
        return None
    pct = _pct(100 * _as_float(top["tokens"]) / total)
    return _insight(
        "focus",
        f"{top['project']} took {pct}% of your tokens over the last"
        f" {INSIGHT_WINDOW_DAYS} days. That is where your usage actually goes.",
        {"project": top["project"], "pct": pct, "days": INSIGHT_WINDOW_DAYS},
        now=now,
        fingerprint_parts=[top["project"], pct],
    )


def insight_rhythm(con: sqlite3.Connection, *, now: datetime | None = None) -> Message | None:
    start, end = day_range(INSIGHT_WINDOW_DAYS, now=now)
    shape = ledger.session_shape(con, start_day=start, end_day=end)
    if shape["sessions"] < MIN_INSIGHT_SESSIONS:
        return None
    pct = _pct(100 * shape["work_hours_share"])
    return _insight(
        "rhythm",
        f"{pct}% of your sessions run on weekdays between 08:00 and 18:00."
        " The rest is evenings and weekends.",
        {"pct": pct},
        now=now,
        fingerprint_parts=[pct],
    )


_INSIGHT_BUILDERS = {
    "cache": insight_cache,
    "week": insight_week,
    "peak": insight_peak,
    "focus": insight_focus,
    "rhythm": insight_rhythm,
}


def insight_candidates(con: sqlite3.Connection, *, now: datetime | None = None) -> list[Message]:
    """Every insight there is enough data to say, in tie-break order."""
    found: list[Message] = []
    for insight_id in INSIGHT_IDS:
        message = _INSIGHT_BUILDERS[insight_id](con, now=now)
        if message is not None:
            found.append(message)
    return found


def next_insight(con: sqlite3.Connection, *, now: datetime | None = None) -> Message | None:
    """The insight that has waited longest, so none repeats before the rest.

    Rotation is read from the messages table itself: each insight's key carries
    the day it was made, and the newest one under its prefix says when it last
    had a turn. One that never has, goes first.
    """
    candidates = insight_candidates(con, now=now)
    if not candidates:
        return None

    def last_turn(message: Message) -> int:
        prefix = f"{INSIGHT_KEY_PREFIX}{message.meta['insight']}:"
        stamp = ledger.last_generated_at(con, kind=message.kind, key_prefix=prefix)
        return -1 if stamp is None else stamp

    # sorted() is stable, so equal turns keep INSIGHT_IDS order.
    return sorted(candidates, key=last_turn)[0]


def has_pending_insight(rows: list[dict[str, Any]], *, now: datetime | None = None) -> bool:
    """Whether an unread, still-fresh insight is already waiting on the page.

    A person who has not read the last one does not need another, and without
    this every open after a long absence would pile a new one on top.
    """
    now_ts = _epoch(now)
    for row in rows:
        if not str(row.get("key") or "").startswith(INSIGHT_KEY_PREFIX):
            continue
        expires = _expires_of(row)
        if expires is None or expires > now_ts:
            return True
    return False


def cold_note(con: sqlite3.Connection, *, now: datetime | None = None) -> Message | None:
    """The note for a cold open: the next insight, unless one is waiting unread."""
    if has_pending_insight(ledger.pending_messages(con), now=now):
        return None
    return next_insight(con, now=now)


# -- the warm note ----------------------------------------------------------

# A warm note describes the last couple of hours. Its token count is bucketed
# when fingerprinted so a few hundred tokens of drift is not "something new".
WARM_WINDOW_HOURS = 2
WARM_TOKEN_BUCKET = 10_000
WARM_KEY_PREFIX = "warm:"

# "Ran elsewhere": a meter that rose this many points over the window while this
# machine recorded no session for that provider. The baseline must be at least
# this old, or two polls a minute apart would read as movement.
ELSEWHERE_MIN_POINTS = 8
ELSEWHERE_MIN_AGE_SECONDS = 300


def tightest_short_meter(snapshots: list[Any]) -> dict[str, Any] | None:
    """The fullest rolling-window meter among providers that own one.

    The 5-hour kind of limit is the one that moves within a working session, so
    it is the meter a note about "now" can honestly mention. Borrowed meters are
    skipped: they are another account's number shown on a harness.
    """
    best: dict[str, Any] | None = None
    for snap in snapshots:
        if snap.status != "ok" or snap.borrowed_from is not None:
            continue
        for meter in snap.metrics:
            if meter.kind != "rolling":
                continue
            if best is None or meter.percent > best["raw"]:
                best = {
                    "raw": meter.percent,
                    "providerId": snap.provider_id,
                    "provider": snap.display_name,
                    "key": meter.key,
                    "label": meter.label,
                    "kind": meter.kind,
                }
    if best is None:
        return None
    best["pct"] = _pct(best.pop("raw"))
    return best


def find_elsewhere(
    con: sqlite3.Connection,
    snapshots: list[Any],
    samples: dict[tuple[str, str], list[tuple[float, float]]],
    *,
    now: datetime | None = None,
    hours: int = WARM_WINDOW_HOURS,
) -> dict[str, Any] | None:
    """Usage that moved a meter without leaving a trace on this machine.

    The transcripts only see this machine; the meters see every client. So a
    rolling meter that climbed while the ledger recorded no session for that
    provider is usage from somewhere else -- a phone, the web, another computer.
    `samples` is the history series per (provider, meter), read by the caller
    because the history store belongs to the main loop's connection.

    Silent unless the claim is safe: the baseline must be a few minutes old, the
    climb must be real, and no session of that provider may be live now (a
    session still being written has not reached the ledger yet).
    """
    until = _epoch(now)
    since = until - max(1, _as_int(hours)) * 3600
    best: dict[str, Any] | None = None
    for snap in snapshots:
        if snap.status != "ok" or snap.borrowed_from is not None:
            continue
        instances = getattr(snap, "instances", None)
        if instances is not None and getattr(instances, "active", None):
            continue
        for meter in snap.metrics:
            if meter.kind != "rolling":
                continue
            series = [
                (ts, pct)
                for ts, pct in samples.get((snap.provider_id, meter.key), [])
                if ts >= since
            ]
            if not series:
                continue
            base_ts, base_pct = series[0]
            if until - base_ts < ELSEWHERE_MIN_AGE_SECONDS:
                continue
            points = _as_float(meter.percent) - base_pct
            if points < ELSEWHERE_MIN_POINTS:
                continue
            local = ledger.rolling_period_totals(
                con, since=int(base_ts), until=until, group_by="provider"
            )
            if any(row["provider"] == snap.provider_id and row["sessions"] for row in local):
                continue
            if best is None or points > best["points"]:
                best = {
                    "providerId": snap.provider_id,
                    "provider": snap.display_name,
                    "label": meter.label,
                    "points": points,
                    "since": int(base_ts),
                }
    if best is not None:
        best["points"] = _pct(best["points"])
    return best


def warm_facts(
    con: sqlite3.Connection,
    snapshots: list[Any],
    *,
    hours: int = WARM_WINDOW_HOURS,
    samples: dict[tuple[str, str], list[tuple[float, float]]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Every figure a warm note may use: the recent window and the live meter."""
    since, until = rolling_range(hours, now=now)
    totals = ledger.rolling_totals(con, since=since, until=until)
    projects = ledger.rolling_period_totals(
        con, since=since, until=until, group_by="project", limit=1
    )
    top = projects[0] if projects and projects[0]["project"] else None
    return {
        "hours": hours,
        "sessions": _as_int(totals["sessions"]),
        "tokens": _as_int(totals["tokens"]),
        "project": top["project"] if top else None,
        "meter": tightest_short_meter(snapshots),
        "elsewhere": (
            find_elsewhere(con, snapshots, samples, now=now, hours=hours) if samples else None
        ),
    }


def warm_fingerprint(facts: dict[str, Any]) -> str:
    """The figures a warm note was built from, bucketed to what is noticeable."""
    meter = facts["meter"]
    return fingerprint_of(
        facts["sessions"],
        facts["tokens"] // WARM_TOKEN_BUCKET,
        facts["project"],
        [meter["providerId"], meter["key"], meter["pct"]] if meter else None,
        [facts["elsewhere"]["providerId"], facts["elsewhere"]["points"]]
        if facts.get("elsewhere")
        else None,
    )


def render_warm(facts: dict[str, Any]) -> str:
    """The warm note's English wording, which is also the fallback text."""
    hours = facts["hours"]
    parts: list[str] = []
    away = facts.get("elsewhere")
    if away:
        since = datetime.fromtimestamp(away["since"]).strftime("%H:%M")
        parts.append(
            f"About {away['points']} points of your {away['provider']} "
            f"{away['label']} went somewhere other than this machine since "
            f"{since}: phone or web, probably."
        )
    if facts["sessions"]:
        body = (
            f"Last {hours}h: {facts['sessions']} sessions, "
            f"{ledger.format_tokens(facts['tokens'])} tokens"
        )
        if facts["project"]:
            body += f", mostly {facts['project']}"
        parts.append(body + ".")
    else:
        parts.append(f"No sessions in the last {hours}h.")
    meter = facts["meter"]
    if meter:
        parts.append(f"{meter['provider']} {meter['label']} is at {meter['pct']}%.")
    return " ".join(parts)


def warm_note(
    con: sqlite3.Connection,
    snapshots: list[Any],
    *,
    samples: dict[tuple[str, str], list[tuple[float, float]]] | None = None,
    now: datetime | None = None,
) -> Message | None:
    """A note about the last couple of hours, from the freshest figures there are.

    Template wording only; nothing here reaches a model. None when there is
    neither recent activity nor a meter to speak of.
    """
    facts = warm_facts(con, snapshots, samples=samples, now=now)
    if not facts["sessions"] and not facts["meter"] and not facts["elsewhere"]:
        return None
    fingerprint = warm_fingerprint(facts)
    meter = facts["meter"]
    return Message(
        kind=INFORMATIVE,
        key=f"{WARM_KEY_PREFIX}{fingerprint}",
        body=render_warm(facts),
        provider=(
            facts["elsewhere"]["providerId"]
            if facts["elsewhere"]
            else (meter["providerId"] if meter else "")
        ),
        meta={
            "period": "warm",
            "tpl": _tpl(
                "warm",
                hours=facts["hours"],
                sessions=facts["sessions"],
                tokens=facts["tokens"],
                project=facts["project"],
                elsewhere=(
                    {
                        "provider": facts["elsewhere"]["provider"],
                        "label": facts["elsewhere"]["label"],
                        "points": facts["elsewhere"]["points"],
                        "since": facts["elsewhere"]["since"],
                    }
                    if facts["elsewhere"]
                    else None
                ),
                meter=(
                    {
                        "provider": meter["provider"],
                        "label": meter["label"],
                        "kind": meter["kind"],
                        "pct": meter["pct"],
                    }
                    if meter
                    else None
                ),
            ),
            **provenance(
                tier=WARM,
                as_of=_epoch(now),
                fingerprint=fingerprint,
            ),
        },
    )


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


def event_messages(snapshots: list[Any], *, wind_down_hours: float = 2.0) -> list[Message]:
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
                eta_seconds is not None and eta_seconds <= max(0.0, wind_down_hours) * 3600
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
                        tpl=_tpl(
                            "actionable",
                            provider=snap.display_name,
                            label=meter.label,
                            kind=meter.kind,
                            percent=_pct(meter.percent),
                            spent=meter.percent >= SPENT_AT,
                            etaSeconds=_as_int(eta_seconds) if eta_seconds else None,
                            better=featured["name"] if featured else "",
                        ),
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


def _template_of(meta: dict[str, Any]) -> dict[str, Any] | None:
    tpl = meta.get("tpl")
    if not isinstance(tpl, dict) or not tpl.get("id") or meta.get("composed_by"):
        return None
    return {"id": str(tpl["id"]), "params": dict(tpl.get("p") or {})}


def _expires_of(row: dict[str, Any]) -> int | None:
    """When a stored message stops being worth showing, from its own meta."""
    meta = _meta_of(row)
    return expires_at_for(
        str(row.get("kind") or ""),
        _as_int(row.get("created_at")),
        tier=str(meta.get("tier") or "") or None,
        as_of=_as_int(meta.get("asOf")) or None,
    )


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
        "expiresAt": _expires_of(row),
        "tier": str(meta.get("tier") or ""),
        "asOf": _as_int(meta.get("asOf")) or created,
        "source": str(meta.get("source") or SOURCE_TEMPLATE),
        "reason": str(meta.get("reason") or ""),
        # What the panel renders in the user's language. Absent once a model has
        # reworded the message: its prose is the message, and there is nothing
        # to re-render from.
        "template": _template_of(meta),
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
        expires = _expires_of(row)
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
