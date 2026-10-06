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
                "kind": "monthly",
            },
            {
                "key": "other",
                "label": "Other models",
                "value": 31,
                "resets": "Resets in 12 days",
                "kind": "other",
            },
        ],
        "instances": {
            "active": 2,
            "suspended": 1,
            "projects": ["maarifa-project", "optimus"],
            "suspendedProjects": ["cursor-folder"],
            "sessions": [
                {
                    "project": "maarifa-project",
                    "directory": "/home/u/maarifa-project",
                    "paused": False,
                    "kind": "agent",
                    "tty": "pts/2",
                },
                {
                    "project": "optimus",
                    "directory": "/home/u/optimus",
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
                "kind": "rolling",
            },
            {
                "key": "weekly",
                "label": "Weekly",
                "value": 81,
                "resets": "Resets in 4 days",
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
                "kind": "rolling",
            },
            {
                "key": "weekly",
                "label": "Weekly",
                "value": 33,
                "resets": "Resets in 6 days",
                "kind": "weekly",
            },
            {
                "key": "monthly",
                "label": "Monthly",
                "value": 23,
                "resets": "Resets in 20 days",
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
                "kind": "rolling",
            },
            {
                "key": "weekly",
                "label": "Weekly",
                "value": 33,
                "resets": "Resets in 6 days",
                "kind": "weekly",
            },
            {
                "key": "monthly",
                "label": "Monthly",
                "value": 23,
                "resets": "Resets in 20 days",
                "kind": "monthly",
            },
        ],
        "instances": {
            "active": 2,
            "suspended": 0,
            "projects": ["optimus", "sundeskv2"],
            "suspendedProjects": [],
            "sessions": [
                {
                    "project": "optimus",
                    "directory": "/home/u/optimus",
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
                    "project": "sundeskv2",
                    "directory": "/home/u/sundeskv2",
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
loop = GLib.MainLoop()


def state():
    return {
        "version": "0.4.0-mock",
        "updated_at": "2026-09-13T15:00:00+00:00",
        "error": None,
        "tools": tools,
    }


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
    on_quit=loop.quit,
    on_name_lost=loop.quit,
)
print("mock daemon up", flush=True)
loop.run()
