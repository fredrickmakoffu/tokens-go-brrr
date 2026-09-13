# Cursor Spend Monitor

A GNOME panel tray applet for **Fedora / GNOME** that polls Cursor's usage API and shows your AI spend at a glance — with desktop alerts when you hit thresholds you configure.

## What you get

1. **Panel icon** (top-right, next to Wi‑Fi / Bluetooth / volume) — color and fill reflect usage:
   - Green: under 70%
   - Amber: 70–89%
   - Red: 90%+
2. **Dropdown menu** — total usage, Cursor models vs other models, billing reset countdown, on-demand status, refresh, open dashboard.
3. **Desktop notifications** — fire once per threshold per cooldown window (default 6h).

## Architecture

```
┌─────────────────────┐     GET /api/usage-summary     ┌──────────────┐
│  cursor-spend-      │ ─────────────────────────────► │  cursor.com  │
│  monitor (Python)   │     WorkosCursorSessionToken   └──────────────┘
└─────────┬───────────┘
          │ Ayatana AppIndicator
          ▼
┌─────────────────────┐
│ GNOME panel (tray)  │  ← requires AppIndicator extension
└─────────────────────┘
```

**Why Python + AppIndicator (not a pure GNOME extension)?**

- Cookie/session handling and HTTP are straightforward.
- Alert logic and polling are easy to maintain.
- Works on Fedora GNOME once `gnome-shell-extension-appindicator` is enabled.
- A future GNOME Shell extension could read `/run/user/$UID/cursor-spend-monitor/state.json` for native Quick Settings — the daemon already writes that file.

## Auth

Uses your **Cursor desktop login** — reads `cursorAuth/accessToken` from
`~/.config/Cursor/User/globalStorage/state.vscdb` and calls
`https://api2.cursor.sh` (same path as the IDE). No browser cookie required.

Stay signed in to Cursor. If the access token expires, the monitor refreshes it
with the stored refresh token.

Legacy browser-cookie setup is no longer needed (cursor.com blocks non-browser
clients with a Vercel challenge).

## Install

```bash
cd cursor-spend-monitor
chmod +x install.sh
./install.sh
cursor-spend-monitor setup
cursor-spend-monitor status
systemctl --user enable --now cursor-spend-monitor.service
```

Manual install (no sudo):

```bash
pip3 install --user .
cursor-spend-monitor setup
cursor-spend-monitor run
```

## Configuration

`~/.config/cursor-spend-monitor/config.json`:

```json
{
  "session_token": "user_…::eyJ…",
  "poll_interval_seconds": 300,
  "primary_metric": "total_percent",
  "alert_cooldown_hours": 6,
  "alerts": {
    "total_percent": [75, 90, 100],
    "api_percent": [80, 100],
    "auto_percent": [80, 100]
  }
}
```

- **`primary_metric`** — drives the tray icon percentage (`total_percent`, `api_percent`, or `auto_percent`).
- **`alerts`** — notification thresholds per metric.

## Commands

| Command | Description |
|---------|-------------|
| `cursor-spend-monitor setup` | Paste session cookie (hidden input) |
| `cursor-spend-monitor run` | Foreground tray (debug) |
| `cursor-spend-monitor status` | Print usage to terminal |
| `cursor-spend-monitor config` | Show config file |

## Troubleshooting

**No icon in panel**

- Install & enable AppIndicator: `sudo dnf install gnome-shell-extension-appindicator` then log out/in.
- Run foreground: `cursor-spend-monitor run` and check stderr.

**401 / session expired**

- Re-run `cursor-spend-monitor setup` with a fresh cookie from the browser.

**Notifications not showing**

- Ensure Do Not Disturb is off; test with `notify-send "test"`.

## Security note

Never commit or share your `WorkosCursorSessionToken`. It grants full web dashboard access to your Cursor account.
