import sys
sys.path.insert(0, sys.argv[1])
from gi.repository import GLib
from cursor_spend_monitor.dbus_service import UsageService

tools = [
    {"id": "cursor", "name": "Cursor", "icon": "cursor", "primary": "monthly", "status": "ok",
     "dashboardUrl": "https://cursor.com/dashboard",
     "metrics": [{"key": "monthly", "label": "Monthly limit", "value": 74, "resets": "Resets in 12 days"}],
     "instances": {
         "active": 2, "suspended": 1,
         "projects": ["maarifa-project", "optimus"],
         "suspendedProjects": ["cursor-folder"],
         "sessions": [
             {"project": "maarifa-project", "directory": "/home/u/maarifa-project", "paused": False, "kind": "agent", "tty": "pts/2"},
             {"project": "optimus", "directory": "/home/u/optimus", "paused": False, "kind": "agent", "tty": "pts/3"},
             {"project": "cursor-folder", "directory": "/home/u/cursor-folder", "paused": True, "kind": "agent", "tty": "pts/4"},
         ],
     }},
    {"id": "claude", "name": "Claude Code", "icon": "claude", "primary": "5h", "status": "ok",
     "dashboardUrl": "https://claude.ai",
     "metrics": [{"key": "5h", "label": "5-hour limit", "value": 42, "resets": "Resets in 2h 15m"},
                 {"key": "weekly", "label": "Weekly", "value": 81, "resets": "Resets in 4 days"}]},
    {"id": "opencode", "name": "OpenCode", "icon": "opencode", "primary": "5h", "status": "ok",
     "dashboardUrl": "https://opencode.ai",
     "metrics": [{"key": "5h", "label": "5-hour limit", "value": 15, "resets": "Resets in 4h 50m"},
                 {"key": "weekly", "label": "Weekly", "value": 33, "resets": "Resets in 6 days"}]},
]
loop = GLib.MainLoop()
def state():
    return {"version": "0.4.0-mock", "updated_at": "2026-09-13T15:00:00+00:00", "error": None, "tools": tools}
def set_primary(pid, key):
    for t in tools:
        if t["id"] == pid:
            t["primary"] = key
    print("mock: SetPrimary", pid, key, flush=True)
    svc.emit_state(state())
def refresh():
    print("mock: Refresh", flush=True)
svc = UsageService(version="0.4.0-mock", get_state=state, on_refresh=refresh,
                   on_set_primary=set_primary, on_quit=loop.quit, on_name_lost=loop.quit)
print("mock daemon up", flush=True)
loop.run()
