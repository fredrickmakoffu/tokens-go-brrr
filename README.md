# AI usage

GNOME Shell indicator for AI coding limits, plus a small daemon that fetches them.
Cursor is live; OpenCode and Claude Code are next.

## What you see

**Top bar:** a status dot, green / amber / red by the worst primary meter across providers.

**Popover** (click the dot) — built from `design/menu-bar-concept.html`:

- **List** — each provider with its primary percentage, a thin bar, and a chip that swaps in the secondary metric
- **Detail** — every meter with reset copy, plus Open dashboard
- **Guide** — Healthy / Caution / Critical legend
- **About** — daemon version, last refresh, manual refresh

## Install

```bash
chmod +x install.sh && ./install.sh
cursor-spend-monitor setup
systemctl --user enable --now cursor-spend-monitor.service
```

Log out and back in so GNOME Shell picks up the extension. Needs GNOME Shell 45 or newer.

## Auth

Reads the Cursor IDE login from `~/.config/Cursor/User/globalStorage/state.vscdb`. No browser cookies.

## Config

`~/.config/cursor-spend-monitor/config.json`:

```json
{
  "poll_interval_seconds": 300,
  "alert_cooldown_hours": 6,
  "primary_alerts": [75, 90, 100],
  "enabled_providers": ["cursor"],
  "primary_overrides": {}
}
```

Chip swaps persist in `primary_overrides`.

## Architecture

```
GNOME Shell extension (status dot + popover)
        ↑  io.github.fredrickmakoffu.AIUsage on the session bus
   daemon (poll, alert, publish)
        ↑
  ProviderSnapshot[] ← providers/cursor (+ opencode, claude later)
```

The extension holds no credentials and makes no network calls. It reads state from the
daemon and sends back two commands: `Refresh` and `SetPrimary`.

## Commands

| Command | Description |
|---------|-------------|
| `setup` | Verify Cursor login |
| `run` | Foreground daemon |
| `status` | Print meters |
| `config` | Show config path |

## Development

`design/menu-bar-concept.html` is the reference mockup; the extension stylesheet mirrors its
values one to one. To test without a live login, run a mock daemon and a nested shell — see
`gnome-shell-extension/README.md`.
