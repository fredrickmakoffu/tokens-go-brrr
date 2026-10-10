import sys

sys.path.insert(0, sys.argv[1])
from gi.repository import GLib  # type: ignore  # gi has no stubs

from cursor_spend_monitor.dbus_service import UsageService

tools = [
    {
        "id": "cursor",
        "name": "Cursor",
        "icon": "cursor",
        "primary": "monthly",
        "status": "ok",
        "dashboardUrl": "https://cursor.com/dashboard",
        "metrics": [
            {
                "key": "monthly",
                "label": "Monthly limit",
                "value": 74,
                "resets": "Resets in 12 days",
                "elapsed": 60,
                "kind": "monthly",
            },
            {
                "key": "other",
                "label": "Other models",
                "value": 31,
                "resets": "Resets in 12 days",
                "elapsed": 60,
                "kind": "other",
            },
        ],
        "instances": {
            "active": 2,
            "suspended": 1,
            "projects": ["web-app", "api-server"],
            "suspendedProjects": ["cursor-folder"],
            "sessions": [
                {
                    "project": "web-app",
                    "directory": "/home/u/web-app",
                    "paused": False,
                    "kind": "agent",
                    "tty": "pts/2",
                },
                {
                    "project": "api-server",
                    "directory": "/home/u/api-server",
                    "paused": False,
                    "kind": "agent",
                    "tty": "pts/3",
                },
                {
                    "project": "cursor-folder",
                    "directory": "/home/u/cursor-folder",
                    "paused": True,
                    "kind": "agent",
                    "tty": "pts/4",
                },
            ],
        },
    },
    {
        "id": "claude",
        "name": "Claude Code",
        "icon": "claude",
        "primary": "5h",
        "status": "ok",
        "dashboardUrl": "https://claude.ai",
        "metrics": [
            {
                "key": "5h",
                "label": "5-hour limit",
                "value": 42,
                "resets": "Resets in 2h 15m",
                "elapsed": 55,
                "kind": "rolling",
            },
            {
                "key": "weekly",
                "label": "Weekly",
                "value": 81,
                "resets": "Resets in 4 days",
                "elapsed": 43,
                "kind": "weekly",
            },
        ],
    },
    {
        "id": "opencode",
        "name": "OpenCode",
        "icon": "opencode",
        "primary": "5h",
        "status": "ok",
        "dashboardUrl": "https://opencode.ai",
        "metrics": [
            {
                "key": "5h",
                "label": "Rolling limit",
                "value": 15,
                "resets": "Resets in 4h 50m",
                "elapsed": 3,
                "kind": "rolling",
            },
            {
                "key": "weekly",
                "label": "Weekly",
                "value": 33,
                "resets": "Resets in 6 days",
                "elapsed": 71,
                "kind": "weekly",
            },
            {
                "key": "monthly",
                "label": "Monthly",
                "value": 23,
                "resets": "Resets in 20 days",
                "elapsed": 33,
                "kind": "monthly",
            },
        ],
    },
    # Pi borrowing OpenCode Go's meters: same numbers as the row above, marked
    # so the status dot ignores them.
    {
        "id": "pi",
        "name": "Pi",
        "icon": "pi",
        "primary": "5h",
        "status": "ok",
        "dashboardUrl": "https://pi.dev",
        "plan": "deepseek-v4-flash",
        "via": {
            "account": "opencode-go",
            "name": "OpenCode Go",
            "model": "deepseek-v4-flash",
            "providerId": "opencode",
            "metered": True,
            "borrowed": True,
            "from": "opencode",
        },
        "metrics": [
            {
                "key": "5h",
                "label": "Rolling limit",
                "value": 15,
                "resets": "Resets in 4h 50m",
                "elapsed": 3,
                "kind": "rolling",
            },
            {
                "key": "weekly",
                "label": "Weekly",
                "value": 33,
                "resets": "Resets in 6 days",
                "elapsed": 71,
                "kind": "weekly",
            },
            {
                "key": "monthly",
                "label": "Monthly",
                "value": 23,
                "resets": "Resets in 20 days",
                "elapsed": 33,
                "kind": "monthly",
            },
        ],
        "instances": {
            "active": 2,
            "suspended": 0,
            "projects": ["api-server", "mobile-app"],
            "suspendedProjects": [],
            "sessions": [
                {
                    "project": "api-server",
                    "directory": "/home/u/api-server",
                    "paused": False,
                    "kind": "session",
                    "tty": "pts/5",
                    "backend": {
                        "account": "opencode-go",
                        "name": "OpenCode Go",
                        "model": "deepseek-v4-flash",
                        "providerId": "opencode",
                        "metered": True,
                    },
                },
                {
                    "project": "mobile-app",
                    "directory": "/home/u/mobile-app",
                    "paused": False,
                    "kind": "session",
                    "tty": "pts/6",
                    "backend": {
                        "account": "xai",
                        "name": "xAI",
                        "model": "grok-4.6",
                        "providerId": "",
                        "metered": False,
                    },
                },
            ],
        },
    },
]

# Three messages to cycle through, so the landing page can be exercised without
# waiting for a real one: a recommendation, a value finding, and something
# shareable. Acknowledging advances to the next.
BILLBOARDS = [
    {
        "id": 1,
        "kind": "actionable",
        "priority": 3,
        "text": (
            "Claude Code 5-hour limit is at 93%, spent in about 40m. OpenCode "
            "has room — start the handoff there."
        ),
        "share": "",
        "featured": {
            "providerId": "opencode",
            "name": "OpenCode",
            "role": "suggested",
        },
        "createdAt": 1791288693,
        "expiresAt": None,
        "reason": "5-hour limit at 93%",
    },
    {
        "id": 2,
        "kind": "informative",
        "priority": 2,
        "text": (
            "Last week: 38 sessions, 1.9M tokens. OpenCode carried 71% — 1.4M "
            "tokens for $4.10, the cheapest work in the period."
        ),
        "share": "",
        "featured": {"providerId": "opencode", "name": "OpenCode", "role": "value"},
        "createdAt": 1791288693,
        "expiresAt": None,
        "reason": "1.4M tokens for $4.10",
    },
    {
        "id": 3,
        "kind": "shareable",
        "priority": 1,
        "text": "This month: 154 AI coding sessions and 8.4M tokens across 11 projects.",
        "share": (
            "SHARE: This month I ran 154 AI coding sessions across 11 projects. "
            "One provider did 71% of the work for $4.10."
        ),
        "featured": {"providerId": "claude", "name": "Claude Code", "role": "leading"},
        "createdAt": 1791288693,
        "expiresAt": None,
        "reason": "8.4M tokens",
    },
]
# The daemon sends seconds alongside its English label, and a template with its
# values alongside the message text, so the panel can write both in the user's
# language. Derived here rather than repeated beside every label above.
def _seconds(text):
    import re

    days = re.search(r"(\d+) days", text)
    if days:
        return int(days.group(1)) * 86400
    hm = re.search(r"(?:(\d+)h)?\s*(?:(\d+)m)?$", text.replace("Resets in ", ""))
    return int(hm.group(1) or 0) * 3600 + int(hm.group(2) or 0) * 60


for _tool in tools:
    for _metric in _tool.get("metrics", []):
        _metric["resetsSeconds"] = _seconds(_metric["resets"])

BILLBOARDS[0]["template"] = {
    "id": "actionable",
    "params": {
        "provider": "Claude Code",
        "label": "5-hour limit",
        "kind": "rolling",
        "percent": 93,
        "spent": False,
        "etaSeconds": 2400,
        "better": "OpenCode",
    },
}
BILLBOARDS[1]["template"] = {
    "id": "digest",
    "params": {
        "period": "weekly",
        "sessions": 38,
        "tokens": 1900000,
        "leader": {"name": "OpenCode", "pct": 71},
        "topProject": {"project": "api-server", "sessions": 14, "tokens": 820000},
        "topModel": "deepseek-v4-flash",
        "estimate": False,
        "vsLastMonth": None,
    },
}
BILLBOARDS[2]["template"] = {
    "id": "share",
    "params": {"sessions": 154, "tokens": 8400000, "model": "deepseek-v4-flash"},
}

_shown = 0
loop = GLib.MainLoop()


def state():
    return {
        "version": "0.4.0-mock",
        "updated_at": "2026-09-13T15:00:00+00:00",
        "error": None,
        "tools": tools,
        "billboard": BILLBOARDS[_shown] if _shown < len(BILLBOARDS) else None,
        "latestMessage": BILLBOARDS[-1],
        "recentMessages": list(reversed(BILLBOARDS)),
    }


def acknowledge(message_id):
    """Advance to the next message, so dismissal can be seen in a row."""
    global _shown
    print("mock: Acknowledge", message_id, flush=True)
    _shown = min(_shown + 1, len(BILLBOARDS))
    svc.emit_state(state())


def set_primary(pid, key):
    for t in tools:
        if t["id"] == pid:
            t["primary"] = key
    print("mock: SetPrimary", pid, key, flush=True)
    svc.emit_state(state())


def refresh():
    print("mock: Refresh", flush=True)


svc = UsageService(
    version="0.4.0-mock",
    get_state=state,
    on_refresh=refresh,
    on_set_primary=set_primary,
    on_acknowledge=acknowledge,
    on_quit=loop.quit,
    on_name_lost=loop.quit,
)
print("mock daemon up", flush=True)
loop.run()
