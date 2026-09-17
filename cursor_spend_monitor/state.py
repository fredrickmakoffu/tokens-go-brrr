"""Read the state the daemon already published, instead of polling vendors.

The daemon writes the full panel payload to STATE_FILE on every publish, so
anything that only needs to *read* usage can read that file: no credentials, no
network, no rate limit. That matters because the callers this enables — a shell
prompt, a Waybar module, a tmux status line — run several times a second, and
five vendor requests at that rate would get the user's account throttled.

When no daemon is running the file is missing or stale, and the caller falls
back to fetching directly. Both paths go through `build_payload`, so the shape
on stdout is the same either way.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from . import config as _config

# Bumped only when a field changes meaning or disappears. Consumers pin it:
# a status-bar config that reads `tools[].metrics[].value` should be able to
# tell that it is still reading what it was written against.
SCHEMA_VERSION = 1

# Extra seconds a payload is trusted past its expected refresh, to cover a poll
# that is merely slow rather than a daemon that has stopped.
STALE_GRACE_SECONDS = 30


def build_payload(
    snapshots: list[Any],
    *,
    version: str,
    updated_at: datetime | None,
    error: str | None = None,
) -> dict[str, Any]:
    """The published shape, used by both the daemon and the CLI's live path."""
    return {
        "schema": SCHEMA_VERSION,
        "version": version,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "error": error,
        "tools": [snap.to_panel_dict() for snap in snapshots],
    }


def max_age_for(config: _config.MonitorConfig) -> int:
    """How old published state may be before it stops being worth trusting.

    Two polls: one missed refresh is a slow vendor, two in a row means nobody
    is writing the file any more.
    """
    interval = max(60, config.poll_interval_seconds)
    return 2 * interval + STALE_GRACE_SECONDS


def age_seconds(payload: dict[str, Any]) -> float | None:
    """Seconds since the payload's numbers were fetched, or None if unknown."""
    stamp = _parse_iso(payload.get("updated_at"))
    if stamp is None:
        # No usable timestamp: fall back to when the file was last written.
        try:
            mtime = _config.STATE_FILE.stat().st_mtime
        except OSError:
            return None
        stamp = datetime.fromtimestamp(mtime, tz=timezone.utc)
    return (datetime.now(timezone.utc) - stamp).total_seconds()


def read_state(
    config: _config.MonitorConfig, *, max_age_seconds: int | None = None
) -> dict[str, Any] | None:
    """The daemon's last published payload, or None if there isn't a usable one.

    None covers every "ask the vendors yourself" case: no daemon has ever run,
    the daemon died, or it is alive but no longer refreshing.
    """
    try:
        raw = _config.STATE_FILE.read_text()
    except OSError:
        return None

    try:
        payload = json.loads(raw)
    except ValueError:
        return None

    if not isinstance(payload, dict) or not isinstance(payload.get("tools"), list):
        return None

    limit = max_age_seconds if max_age_seconds is not None else max_age_for(config)
    age = age_seconds(payload)
    if age is None or age > limit:
        return None

    # A daemon from before the key existed publishes this exact shape, and a
    # consumer that branches on `schema` should not break just because the
    # daemon is a version behind the CLI reading its file.
    payload.setdefault("schema", SCHEMA_VERSION)
    return payload


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# -- reading one tool out of a payload ---------------------------------------


def primary_metric(tool: dict[str, Any]) -> dict[str, Any]:
    """The meter this tool leads with, honouring a chip swap the user made."""
    metrics = tool.get("metrics") or []
    for metric in metrics:
        if metric.get("key") == tool.get("primary"):
            return metric
    return metrics[0] if metrics else {"key": "—", "label": "—", "value": 0, "resets": "—"}


def header_of(tool: dict[str, Any]) -> str:
    """Provider line for a text listing: the dict form of Snapshot.header()."""
    via = tool.get("via")
    if via:
        return f"{tool.get('name', '')} · via {via.get('name', '')}"
    if tool.get("plan"):
        return f"{tool['name']} · {tool['plan']}"
    return str(tool.get("name", ""))


def owns_meters(tool: dict[str, Any]) -> bool:
    """False for a harness showing another account's meters.

    A borrowed row is a second view of a subscription that is already in the
    payload under its own provider, so anything that aggregates — a worst-case
    status, a headroom comparison — has to skip it or count that account twice.
    """
    via = tool.get("via")
    return not (via and via.get("borrowed"))
