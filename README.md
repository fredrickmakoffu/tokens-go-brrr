# AI usage

GNOME Shell indicator for AI coding limits, plus a small daemon that fetches them.
Cursor, Claude Code and OpenCode are all live.

## What you see

**Top bar:** a status dot, green / amber / red by the worst primary meter across providers.

**Top bar, while you are working:** each provider with a live session adds its logo and a
session count beside the dot. The percentage joins it only once that provider reaches
caution, so an idle-but-healthy tool costs a logo and two characters.

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

## Providers

| Provider | Meters | Source |
|----------|--------|--------|
| Cursor | Monthly limit, Other models | `api2.cursor.sh` dashboard endpoints |
| Claude Code | 5-hour limit, Weekly (plus Opus and Sonnet weekly when the plan reports them) | `api.anthropic.com/api/oauth/usage` |
| OpenCode | Rolling limit, Weekly, Monthly | `opencode.ai/zen/go/v1/usage` |

## Running sessions

A session is one process you started: a terminal agent, or the desktop app. The daemon finds
them by scanning `/proc` every few seconds, which costs about 5ms for 350 processes, and each
provider declares what to look for rather than the scanner knowing about any tool:

```python
process_specs = [
    ProcessSpec(names=frozenset({"claude"}), exclude_args=("--chrome-native-host",)),
]
```

Three things the count deliberately gets right:

- **Suspended sessions do not count.** A session left in the background with Ctrl+Z consumes
  nothing until resumed, so it stays out of the panel and is reported separately in the
  provider's detail screen.
- **Helper processes do not count.** Electron spawns one process per window and per service,
  all carrying `--type=`, and Claude's browser integration runs a process that is not a
  session. Both are excluded by the specs above.
- **A session that spawns a copy of itself counts once.** Any process with an ancestor
  belonging to the same provider is treated as part of that session.

Project names never reach the top bar, only the count; the folder name appears in the detail
screen. A change has to survive two consecutive scans before it is published, so a session
that starts and exits between ticks cannot make the panel flicker.

## Auth

No browser cookies and no scraping. Each provider reuses a login that is already on disk.

**Cursor** reads the IDE login from `~/.config/Cursor/User/globalStorage/state.vscdb`.

**Claude** reads the Claude Code OAuth token from `~/.claude/.credentials.json` and sends it
as a bearer token. The file is read, never written: Claude Code owns the refresh cycle, and
rotating the refresh token here could sign you out of the CLI. When the token has expired the
row shows *Claude login expired* until you next run `claude`, which refreshes it.

**OpenCode** reads the OpenCode Go API key from `~/.local/share/opencode/auth.json`, or from
`OPENCODE_API_KEY` when that is set. Requires a Go subscription: the free tier reports no
usage windows. Note that the OpenCode CLI itself only discovers limits reactively, from the
body of a refused request, so the console endpoint polled here is the only way to see them
before you hit one.

## Config

`~/.config/cursor-spend-monitor/config.json`:

```json
{
  "poll_interval_seconds": 300,
  "instance_poll_seconds": 3,
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
