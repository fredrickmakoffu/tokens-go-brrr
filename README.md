# AI usage

GNOME Shell indicator for AI coding limits, plus a small daemon that fetches them.
Cursor, Claude Code, OpenCode and Pi are all live.

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
| ---------- | -------- | -------- |
| Cursor | Monthly limit, Other models | `api2.cursor.sh` dashboard endpoints |
| Claude Code | 5-hour limit, Weekly (plus Opus and Sonnet weekly when the plan reports them) | `api.anthropic.com/api/oauth/usage` |
| OpenCode | Rolling limit, Weekly, Monthly | `opencode.ai/zen/go/v1/usage` |
| Codex | Monthly limit | `chatgpt.com/backend-api/codex/usage` |
| Pi | Borrowed from the account its sessions are on | `~/.pi/agent`, no network call |

## Harnesses

Most tools here own the subscription they report on. Pi does not: it is a harness
that spends against whichever LLM account the session selected — OpenCode Go, Codex,
xAI, or a custom endpoint such as Cline. So Pi ships no meters of its own.

What it does instead: every live Pi session names the account it bills to, read
from `~/.pi/agent/sessions/<cwd>/…jsonl` (the last `model_change` line, falling
back to `settings.json`'s default). When that account is one another provider here
already polls, Pi's row **borrows** that provider's meters rather than fetching
them again:

```text
OpenCode   74%  ▓▓▓▓▓▓▓░░░
Pi  via OpenCode Go   74%  ▓▓▓▓▓▓▓░░░   deepseek-v4-flash
```

Borrowed meters are marked as such, so:

- **The status dot counts a subscription once.** Only a row that owns its meters
  votes on green / amber / red; a borrowed copy would give one account two votes.
- **Alerts fire once.** The account's own provider notifies; the harness does not.
- **The top bar composes the logos.** Pi's chip carries the backend's mark in its
  corner, so the bar says both what you are running and whose quota it is spending.

**When the backend cannot be metered** — xAI publishes no usage endpoint, and
Cline reports a credit balance rather than a window — the row still appears with
its sessions and names the account, and shows no bar and no percentage. A session
you are running is worth showing whether or not its limit is knowable, and an
empty bar at 0% would read as "plenty left" rather than "unknown".

Sessions are resolved individually, so two Pi sessions on different accounts each
show their own model in the detail screen; the row's headline follows whichever
account most of them are on. Session logs reach several MB and the scan runs every
few seconds, so only the tail is read, and only when the log's mtime has moved.

## Running sessions

A session is one process you started: a terminal agent, or the desktop app. The daemon finds
them by scanning `/proc` every few seconds, which costs about 5ms for 350 processes, and each
provider declares what to look for rather than the scanner knowing about any tool:

```python
process_specs = [
    ProcessSpec(names=frozenset({"claude"}), exclude_args=("--chrome-native-host",)),
]
```

Things the count deliberately gets right:

- **Suspended sessions do not count.** A session left in the background with Ctrl+Z consumes
  nothing until resumed, so it stays out of the panel and is reported separately in the
  provider's detail screen.
- **Helper processes do not count.** Electron spawns one process per window and per service,
  all carrying `--type=`, and Claude's browser integration runs a process that is not a
  session. Cursor's `worker-server` helpers and `--print` (headless / Task) agents are
  excluded the same way.
- **A session that spawns a copy of itself counts once.** Any process with an ancestor
  belonging to the same provider is treated as part of that session, including when
  unmatched Electron helpers sit between the desktop app and an IDE-spawned agent.
- **One terminal is one session.** Sibling agents that share a controlling TTY (for
  example several jobs under the same shell) collapse to a single count.
- **Paused means Ctrl+Z.** Those sessions stay out of the top-bar ×N and show as
  *paused* in the provider detail list until you resume them (`fg`).
- **Focused project (GNOME Terminal / Ptyxis only).** When the focused terminal's
  title shows a provider process (agent / claude / opencode), that provider's chip
  shows the project. OpenCode often resolves immediately (one session). Cursor
  agent titles usually omit the folder, so the chip probes which agent pid woke
  up on the tab focus. A plain shell in the same repo stays icon + ×N.

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

The panel asks for a refresh every time it opens, and the daemon drops that
request if it polled within the last 60 seconds. Opening the popover is the
cheapest way to make requests to five vendors at once, and the endpoints that
answer fastest are the ones that start refusing — Anthropic returns 429 on its
usage route long before any quota is spent. Inside the cooldown the panel is
served state that is at most a minute old, which is the same number a fresh poll
would have returned. The scheduled poll is not affected.

`~/.config/cursor-spend-monitor/config.json`:

```json
{
  "poll_interval_seconds": 300,
  "instance_poll_seconds": 3,
  "alert_cooldown_hours": 6,
  "history_days": 90,
  "primary_alerts": [75, 90, 100],
  "enabled_providers": ["cursor"],
  "primary_overrides": {}
}
```

Chip swaps persist in `primary_overrides`.

## Architecture

```text
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
| --------- | ------------- |
| `setup` | Verify Cursor login |
| `run` | Foreground daemon |
| `status` | Print meters, as text, JSON or a template |
| `check` | Exit non-zero when quota is running low |
| `best` | Print the provider with the most quota left |
| `config` | Show config path |

## Status bars and scripts

`status` reads the state the daemon already published to
`/run/user/$UID/cursor-spend-monitor/state.json`. That means **no credentials, no
network call and no rate limit**, so it is safe to run as often as a status bar
redraws — about 0.1s per call, against 3.6s and one request per provider if it
has to fetch. When no daemon is running, or its state has gone stale (two missed
polls), it falls back to fetching directly and says so; `--live` forces that.

```bash
cursor-spend-monitor status --json                       # full payload
cursor-spend-monitor status --json --compact             # one line, for jq
cursor-spend-monitor status --format "{icon} {pct}%"     # cursor 37%  claude 62%
cursor-spend-monitor status --format "{name} {pct}%" --provider claude
```

Template fields: `{id}` `{name}` `{icon}` `{plan}` `{status}` `{pct}` `{label}`
`{resets}` `{sessions}` `{paused}` `{via}` `{error}`. Providers are joined by
`--separator` (two spaces by default).

`{pct}` renders `—`, never `0`, whenever there is no real meter to report — a
provider that needs signing in, or a harness on a backend that publishes no
limits. Zero would read as plenty left.

The JSON carries `"schema": 1`; it is bumped only when a field changes meaning,
so a bar config can tell it is still reading what it was written against. It also
carries `"source": "daemon"` or `"live"` — a live payload counts no running
sessions, because nothing scanned `/proc` for it.

Exit codes: `0` every provider shown is fine, `1` at least one needs attention,
`2` the `--provider` filter matched nothing.

## Before a long run

`check` turns the same state into an exit code, for shell aliases, agent hooks
and Makefiles — so a two-hour run does not start at 97%.

```bash
cursor-spend-monitor check --min 20 --provider claude || echo "wait for the reset"
cursor-spend-monitor check --min 10 --any --quiet
```

| Exit | Meaning |
| ------ | --------- |
| `0` | There is headroom |
| `1` | A provider is below the threshold |
| `2` | Nothing could be measured — no daemon, signed out, no meters |

"Could not tell" is deliberately not a pass and not a failure. A stale login
should not green-light a long run, and it should not fail a build that had
nothing to do with quota. Providers reporting no usable limit are skipped rather
than failed, unless `--fail-on-unknown`. By default every selected provider must
have headroom; `--any` passes when one does.

`best` answers the question that comes with paying for four subscriptions:

```console
$ cursor-spend-monitor best --explain
Use Cursor — 63% left (Claude Code 35% left, OpenCode 20% left).
```

Rows borrowing another account's meters never vote in either command, so one
subscription cannot decide an answer twice.

## Burn rate

Every poll is recorded to `~/.local/share/cursor-spend-monitor/history.db`, one
row per meter, kept for `history_days` (90 by default; `0` turns recording off).
From that series each meter gets a time-to-exhaustion:

```text
Claude Code · Pro
  ★ 5-hour limit      62%  Resets in 3h 28m  ·  spent in 41m
```

The fit is deliberately reluctant. A confident wrong estimate is worse than
none — someone reads "4h left", starts the run and is cut off in twenty minutes
— so it reports nothing at all unless there are at least 3 samples spanning 5
minutes, the slope is positive, and the line explains the spread (R² ≥ 0.5). An
ETA that lands after the window resets is withheld too: warning about a limit
the rollover reaches first describes something that cannot happen.

A rollover is found in the meter rather than the clock. Tagging each sample with
the reset it was counting towards is the obvious approach and does not survive
contact with the providers: Claude returns the same reset with microsecond
jitter (`15:00:00.653206`, then `15:00:00.933186`), and OpenCode's rolling window
slides forward on every poll by design. Either one turns a continuous series
into a pile of one-sample groups that can never be fitted. Since a meter only
climbs within its window, the series is instead walked back from the newest
sample and cut where the meter was higher earlier than it is now, or where the
gap is too long to have been one continuous watch.

Only providers that own their meters are recorded; a harness gets its ETA along
with the meters it borrows.

History is a nice-to-have, so a locked or unwritable database disables recording
for the session and says so once, rather than stopping the daemon.

## Development

`design/menu-bar-concept.html` is the reference mockup; the extension stylesheet mirrors its
values one to one. To test without a live login, run a mock daemon and a nested shell — see
`gnome-shell-extension/README.md`.

## Usage ledger and notifications

Beyond the live meters, the daemon keeps a local ledger of what the AI spend was
actually spent on — tokens per provider, model, project and hour — read from the
tools' own stores. Nothing leaves the machine.

```bash
cursor-spend-monitor harvest                 # read every store into the ledger
cursor-spend-monitor harvest --provider claude --full
cursor-spend-monitor report                  # this month: provider / project / model
cursor-spend-monitor report --week --by model
cursor-spend-monitor report --checks         # cross-check disagreements
cursor-spend-monitor quote                   # the latest generated message
cursor-spend-monitor quote --generate --slot weekly
cursor-spend-monitor quote --tweet           # SHARE: line, copied to the clipboard
```

| Source | What it gives | Fidelity |
| --- | --- | --- |
| `~/.local/share/opencode/opencode.db` | exact cost and every token kind per session | measured |
| `~/.claude/projects/**/*.jsonl` | exact usage per response, incl. cache and thinking tokens | measured |
| Cursor dashboard API | per-model spend for one billing cycle | measured, cost unit unverified |
| `~/.codex/state_5.sqlite` | nothing yet on this machine — the reader probes and records why | absent |
| Pi sessions | sessions, models, projects, durations | **no token data exists** |

Every row is keyed and every write is idempotent: a second `harvest` with
nothing new reports `no change`. Rows carry a `source`, and an aggregate that
includes an estimate says so in the message rather than presenting a guess as a
measurement.

Digests and alerts run without any language model. With `llm_notifications`
enabled and a generator configured, the wording is composed by whichever
provider has the most capacity left, and falls back to the templates whenever it
cannot.

## Usage ledger

Alongside the live meters, the daemon keeps a local ledger of *what the spend
was spent on*: tokens per provider, model, project and hour, harvested
idempotently from each tool's own store.

```bash
cursor-spend-monitor harvest                  # read every store into the ledger
cursor-spend-monitor report                   # this month, by provider
cursor-spend-monitor report --week --by model # last 7 days, by model
cursor-spend-monitor report --checks          # cross-check disagreements
cursor-spend-monitor harvest --full           # ignore watermarks, re-read all
```

| Source | What it gives | Fidelity |
| --- | --- | --- |
| `~/.local/share/opencode/opencode.db` | exact cost and every token kind per session | measured |
| `~/.claude/projects/**/*.jsonl` | exact usage per response, including the cache split and thinking tokens | measured |
| Cursor dashboard API | per-model spend for one billing cycle | measured; cost unit still unverified |
| `~/.codex/state_5.sqlite` | nothing on this machine — the reader probes and records why | none yet |
| Pi sessions | sessions, models, projects, durations | **no token data exists** |

Every row is keyed and every write is idempotent: a second `harvest` with
nothing new reports `no change`. A row carries a `source`, and an aggregate that
includes an estimate says so rather than presenting a guess as a measurement.
`report --checks` shows where two authorities disagree — the disagreement is
recorded, never silently reconciled.

## Notifications

Digests and alerts are composed from the ledger, and **work with no LLM
configured**: the wording is a template until a generator is enabled.

```bash
cursor-spend-monitor quote                     # the latest generated message
cursor-spend-monitor quote --generate --slot weekly
cursor-spend-monitor quote --tweet             # SHARE: line, copied to clipboard
```

The daemon sends a digest on its schedule (daily at `notify_daily_hour`, weekly
on `notify_weekly_day`, monthly on the 1st), raises an actionable alert when a
meter crosses the warning line or its burn rate would spend it before the window
resets, and honours `notify_silent_hours`. Nothing is ever posted anywhere:
`--tweet` copies the line and stops there.
