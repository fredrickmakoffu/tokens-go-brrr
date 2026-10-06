import sys

sys.path.insert(0, sys.argv[1])
from gi.repository import GLib  # type: ignore  # gi has no stubs

from cursor_spend_monitor.dbus_service import UsageService

# worst case: longest labels this codebase can produce, all at three digits
tools = [
    {
        "id": "cursor",
        "name": "Cursor",
        "icon": "cursor",
        "primary": "monthly",
        "status": "ok",
        "dashboardUrl": "https://cursor.com",
        "metrics": [
            {
                "key": "monthly",
                "label": "Monthly limit",
                "value": 100,
                "resets": "Resets in 19 days",
            },
            {
                "key": "other",
                "label": "Other models",
                "value": 100,
                "resets": "Resets in 19 days",
            },
        ],
    },
    {
        "id": "claude",
        "name": "Claude Code",
        "icon": "claude",
        "primary": "five_hour",
        "status": "ok",
        "dashboardUrl": "https://claude.ai",
        "metrics": [
            {
                "key": "five_hour",
                "label": "5-hour limit",
                "value": 100,
                "resets": "Resets in 2h",
            },
            {
                "key": "seven_day",
                "label": "Weekly",
                "value": 100,
                "resets": "Resets in 4 days",
            },
            {
                "key": "seven_day_opus",
                "label": "Opus weekly",
                "value": 100,
                "resets": "Resets in 4 days",
            },
            {
                "key": "seven_day_sonnet",
                "label": "Sonnet weekly",
                "value": 100,
                "resets": "Resets in 4 days",
            },
        ],
    },
    {
        "id": "opencode",
        "name": "OpenCode",
        "icon": "opencode",
        "primary": "rolling",
        "status": "ok",
        "dashboardUrl": "https://opencode.ai/console",
        "metrics": [
            {
                "key": "rolling",
                "label": "Rolling limit",
                "value": 100,
                "resets": "Resets in 4h 59m",
            },
            {
                "key": "weekly",
                "label": "Weekly",
                "value": 100,
                "resets": "Resets in 6h",
            },
            {
                "key": "monthly",
                "label": "Monthly",
                "value": 100,
                "resets": "Resets in 23 days",
            },
        ],
    },
]
loop = GLib.MainLoop()


def state():
    return {
        "version": "stress",
        "updated_at": "2026-09-13T15:00:00+00:00",
        "error": None,
        "tools": tools,
    }


def set_primary(pid, key):
    for t in tools:
        if t["id"] == pid:
            t["primary"] = key
    svc.emit_state(state())


svc = UsageService(
    version="stress",
    get_state=state,
    on_refresh=lambda: None,
    on_set_primary=set_primary,
    on_quit=loop.quit,
    on_name_lost=loop.quit,
)
print("stress daemon up", flush=True)
loop.run()
