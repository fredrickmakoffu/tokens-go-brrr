import sys

sys.path.insert(0, sys.argv[1])
from gi.repository import GLib  # type: ignore  # gi has no stubs

from tokens_go_brrr.dbus_service import UsageService

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

# The longest message the generator can produce, to prove the quote wraps rather
# than being clipped.
LONG_QUOTE = (
    "Last month: 214 sessions, 8.4M tokens across 11 projects, up 22% on the "
    "month before. OpenCode Go carried 71% of the tokens for $4.10, Claude "
    "Code 26% for $20, and Cursor the remaining 3%. Your top project by tokens "
    "was tokens-go-brrr at 1.1M, and 87% of all input tokens were cache "
    "reads."
)
BILLBOARD = {
    "id": 1,
    "kind": "informative",
    "priority": 2,
    "text": LONG_QUOTE,
    "share": "",
    "featured": {"providerId": "opencode", "name": "OpenCode", "role": "value"},
    "createdAt": 1791288693,
    "expiresAt": None,
    "reason": "8.4M tokens for $4.10",
}


def state():
    return {
        "version": "stress",
        "updated_at": "2026-09-13T15:00:00+00:00",
        "error": None,
        "tools": tools,
        "billboard": BILLBOARD,
        "latestMessage": BILLBOARD,
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
    on_acknowledge=lambda _id: None,
    on_quit=loop.quit,
    on_name_lost=loop.quit,
)
print("stress daemon up", flush=True)
loop.run()
