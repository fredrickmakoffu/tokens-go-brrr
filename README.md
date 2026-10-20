# tokens-go-brrr

Panel indicator for AI coding limits, plus a small daemon that fetches them. It shows
a GNOME Shell extension or a Plasma widget, and tracks Cursor, Claude Code, OpenCode,
Codex and Pi.

This is an independent project. It is not made by, affiliated with or endorsed by
Anthropic, OpenAI, Anysphere (Cursor), OpenCode or Pi. Their names and logos belong to
them and appear only to say which service a meter is for.

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
chmod +x install.sh && ./install.sh          # --ui=auto (GNOME, Plasma, or daemon-only)
# ./install.sh --ui=gnome | --ui=plasma | --ui=none
tokens-go-brrr setup
systemctl --user enable --now tokens-go-brrr.service
```

`install.sh` installs the daemon, Barlow fonts (`~/.local/share/fonts/tokens-go-brrr/`),
and one panel UI matched to the session (never both). GNOME needs Shell 45+ and a
log out/in; Plasma users add the `tokens-go-brrr` widget to a panel if needed.
Distro packages split the same way: `tokens-go-brrr` (core) plus
`tokens-go-brrr-gnome` or `tokens-go-brrr-plasma`.

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

**Cursor** reads the IDE login from `~/.config/Cursor/User/globalStorage/state.vscdb`. When the
access token has expired, the daemon refreshes it with Cursor's OAuth endpoint and writes the new
token back to that same database, so the IDE and the daemon stay signed in together. This is the
only place the daemon modifies another tool's files.

**Claude** reads the Claude Code OAuth token from `~/.claude/.credentials.json` and sends it
as a bearer token. The file is read, never written: Claude Code owns the refresh cycle, and
rotating the refresh token here could sign you out of the CLI. When the token has expired the
row shows *Claude login expired* until you next run `claude`, which refreshes it.

**OpenCode** reads the OpenCode Go API key from `~/.local/share/opencode/auth.json`, or from
`OPENCODE_API_KEY` when that is set. Requires a Go subscription: the free tier reports no
usage windows. Note that the OpenCode CLI itself only discovers limits reactively, from the
body of a refused request, so the console endpoint polled here is the only way to see them
before you hit one.

## Privacy

The daemon runs on your machine and has no account, server or telemetry of its own.
It contains no analytics code.

**Read locally:** the logins listed under Auth, and, for the usage ledger, the session
files those tools already keep (Claude Code transcripts, the OpenCode database, Codex
state, Pi sessions). These are never modified. The one exception is the Cursor token
refresh described under Auth. Claude, Codex and OpenCode logins are never refreshed or
written.

**Sent over the network:**

| To | What | When |
| --- | --- | --- |
| `api2.cursor.sh` | Your Cursor login, to read usage | Every poll |
| `api.anthropic.com` | Your Claude Code token, to read usage | Every poll |
| `opencode.ai` | Your OpenCode key, to read usage | Every poll |
| `chatgpt.com` | Your Codex login, to read usage | Every poll |
| `fredrickmakoffu.github.io` | A plain GET for `manifest.json`, to see whether a newer release exists | Every `update_check_hours` (default 6) |
| `github.com` | A download of the release package for your distro | Only when you press Update |
| The LLM provider you pick | Usage figures plus provider, model and project folder names, to word a notification | Only if you enable `llm_notifications` (off by default) |

Each credential goes only to the provider it belongs to. Transcript text, prompts and
file contents are never sent. With LLM wording on, project folder names are. `update_check: false` in the config
turns the update request off, and leaving `llm_notifications` off keeps the daemon
to the four provider rows.

**Updating is always your action.** Pressing Update downloads the package, checks its
sha256 against the manifest, then asks polkit (`pkexec`) to install it with `dnf` or
`apt-get`. You type your password into the desktop's own dialog; the daemon never sees
it. The package and the manifest come from the same release, so the check catches a
corrupted or swapped download, not a compromised release. Packages are not GPG-signed yet.

These usage endpoints are not documented public APIs for the most part. They can change
or disappear without notice, and when they do the affected row shows an error instead
of a number.

## Config

The panel asks for a refresh every time it opens, and the daemon drops that
request if it polled within the last 60 seconds. Opening the popover is the
cheapest way to make requests to five vendors at once, and the endpoints that
answer fastest are the ones that start refusing — Anthropic returns 429 on its
usage route long before any quota is spent. Inside the cooldown the panel is
served state that is at most a minute old, which is the same number a fresh poll
would have returned. The scheduled poll is not affected.

`~/.config/tokens-go-brrr/config.json`:

```json
{
  "poll_interval_seconds": 300,
  "instance_poll_seconds": 3,
  "alert_cooldown_hours": 6,
  "history_days": 90,
  "primary_alerts": [75, 90, 100],
  "enabled_providers": ["cursor", "claude", "opencode", "pi", "codex"],
  "primary_overrides": {}
}
```

Chip swaps persist in `primary_overrides`.

## Architecture

```text
GNOME Shell extension (status dot + popover)
        ↑  D-Bus  io.github.fredrickmakoffu.TokensGoBrrr
   UsageDaemon (poll, harvest, notify, publish)
        ├─ providers/   Cursor · Claude · OpenCode · Codex · Pi
        ├─ harvesters/  local stores → usage ledger
        ├─ ledger       sessions, rollups, messages, billboard
        └─ notify* + llm_*   digests, live notes, optional wording
```

The extension holds no credentials and makes no network calls. It reads state from the
daemon and sends commands such as `Refresh`, `SetPrimary`, and `Acknowledge`.

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
`/run/user/$UID/tokens-go-brrr/state.json`. That means **no credentials, no
network call and no rate limit**, so it is safe to run as often as a status bar
redraws — about 0.1s per call, against 3.6s and one request per provider if it
has to fetch. When no daemon is running, or its state has gone stale (two missed
polls), it falls back to fetching directly and says so; `--live` forces that.

```bash
tokens-go-brrr status --json                       # full payload
tokens-go-brrr status --json --compact             # one line, for jq
tokens-go-brrr status --format "{icon} {pct}%"     # cursor 37%  claude 62%
tokens-go-brrr status --format "{name} {pct}%" --provider claude
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
tokens-go-brrr check --min 20 --provider claude || echo "wait for the reset"
tokens-go-brrr check --min 10 --any --quiet
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
$ tokens-go-brrr best --explain
Use Cursor — 63% left (Claude Code 35% left, OpenCode 20% left).
```

Rows borrowing another account's meters never vote in either command, so one
subscription cannot decide an answer twice.

## Burn rate

Every poll is recorded to `~/.local/share/tokens-go-brrr/history.db`, one
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

## Usage ledger

Alongside the live meters, the daemon keeps a local ledger of *what the spend
was spent on*: tokens per provider, model, project and hour, harvested
idempotently from each tool's own store.

```bash
tokens-go-brrr harvest                   # read every store into the ledger
tokens-go-brrr harvest --provider claude  # one provider only
tokens-go-brrr harvest --full            # ignore watermarks, re-read all
tokens-go-brrr report                    # this month, by provider
tokens-go-brrr report --week --by model  # last 7 days, by model
tokens-go-brrr report --checks           # cross-check disagreements
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
tokens-go-brrr quote                     # the latest generated message
tokens-go-brrr quote --generate --slot weekly
tokens-go-brrr quote --tweet             # SHARE: line, copied to clipboard
```

The daemon sends a digest on its schedule (daily at `notify_daily_hour`, weekly
on `notify_weekly_day`, monthly on the 1st), raises an actionable alert when a
meter crosses the warning line or its burn rate would spend it before the window
resets, and honours `notify_silent_hours`. Nothing is ever posted anywhere:
`--tweet` copies the line and stops there.

## The landing page

When there is something worth saying, the popover opens on it instead of the
provider list: one notification as a quote, the AI it is about underneath, and a
**Continue** back to the list.

It does **not** appear on every open. The daemon decides whether anything is
worth interrupting for — urgency by kind (an actionable warning outranks a
curiosity), a freshness window per kind, and a dismissal that survives a logout.
A **Latest** button in the header reopens the newest message on demand, and the
status dot carries a quiet ring while one is waiting.

The featured AI is read from the ledger, never from a fixed list: the provider
with the most tokens, or a cheaper one carrying a real share of the work ("most
use for the least spend"), or whichever has the most room when the message is
advice about where to move to.

## The LLM wording

Off by default. With `llm_notifications` enabled the wording is composed by
whichever provider has the most short-window headroom, and **falls back to the
template on every failure** — no capacity, a missing credential, a 429, an
unparseable reply.

```jsonc
{
  "llm_notifications": true,
  "llm_generator_model": "",   // "" = the cheap default for each provider
  "llm_min_headroom": 15,      // never spend capacity to warn about capacity
  "llm_log_days": 30           // days of the per-call LLM log to keep; 0 = off
}
```

**Cold notes.** The first time you open the panel after a few hours away (or
after the daemon starts), it makes one trend or insight note from your own
ledger -- cache-read share, week over week, your peak hour and busiest day,
where your tokens go, your weekday rhythm. They rotate so none repeats before
the rest have had a turn, never call a model, and wait on the landing page
instead of popping a desktop notification.

**Warm notes.** Open the panel again inside a working cycle and the daemon
catches the note up with the last couple of hours: it reads the tools' stores
once more, waits for the fresh meters, and -- only if the picture changed --
adds a note like "Last 2h: 3 sessions, 480K tokens, mostly alpha. Claude Code
5-hour limit is at 42%." A short "Catching up…" line shows while it works (never
more than four seconds), then goes. Reopening within `live_hot_minutes` of the
last one changes nothing; warm notes stop being shown two hours after the
figures they describe were read. Wording is a template, translated like the
rest.

**Quick-model wording and "ran elsewhere".** With `llm_notifications` on, a
warm note that is actually new is reworded by the cheapest model on whichever
provider has the most room (Haiku for Claude), within the same four seconds; any
refusal, timeout or spent cap leaves the template, which is a complete note.
Open-time calls are capped (`live_llm_per_hour`, `live_llm_per_day`), a provider
that answers 429 is left alone for 15 minutes, and every call -- and every skip,
with its reason -- is in the LLM log. When a rolling meter has climbed over the
last two hours while this machine recorded no session for that provider and none
is running, the note says so first: that usage came from a phone, the web or
another computer, which the local transcripts can never show.

```jsonc
{
  "live_notes": true,        // false = scheduled digests only
  "live_cold_hours": 4,      // idle hours before an open counts as cold
  "live_hot_minutes": 10,    // a warm note this recent is simply served again
  "live_llm_per_hour": 4,    // model calls made because the panel opened
  "live_llm_per_day": 24     // 0 = never reword on open
}
```

**Every model call is logged**, so you can see exactly what was sent and what
came back. One file per local day under
`~/.local/share/tokens-go-brrr/llm-calls/YYYY-MM-DD.jsonl`, one JSON
object per line: time, why it ran, provider and model, outcome (including
refusals and skips), latency, tokens, the prompt and the reply. Open it in the
panel from **About → LLM activity**. Credentials are never written.

The reply names the AI it is about (`FEATURED:`), chosen from ranked provider
facts sent in the prompt; the daemon validates it and falls back to the derived
choice, so the badge and the prose cannot disagree.

Claude's token and OpenCode's key are opened **read-only** — never refreshed, so
this cannot sign you out of either CLI.

> **Check your plan's terms before using Claude as the generator.** With Claude
> selected, the daemon sends your Claude Code login token to the Anthropic API to
> write the text. Whether a subscription login may be used by a program other than
> Claude Code is set by Anthropic's current terms, not by this project. If you are
> unsure, leave wording off or use another provider.

What travels is usage figures and names: provider and model names, and the folder
names of your most-used projects, because the notes mention them ("mostly alpha").
No transcript text, no prompt history, no file contents.

> **The default model ids may need updating.** They are the cheap end of each
> provider (`claude-haiku-4-5`, `deepseek-v4-flash`) and have not been verified
> against the live services. A wrong id is not fatal — the provider refuses and
> the template is used — but set `llm_generator_model` to pin a specific one.

## Support

The app is free. If it is useful to you, you can
[sponsor its development on GitHub](https://github.com/sponsors/fredrickmakoffu),
as a one-time amount or monthly.

## License

Application code is [MIT](LICENSE). Bundled Barlow fonts are SIL OFL-1.1
(`gnome-shell-extension/.../fonts/OFL.txt`). Provider logos are trademarks of their
owners and are not covered by the MIT license. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md). Report security problems privately, as
described in [SECURITY.md](SECURITY.md).
