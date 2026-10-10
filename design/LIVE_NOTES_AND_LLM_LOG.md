# Live notes and the LLM call log — design

**Status:** in progress — step 1 (rolling windows, provenance, tier expiry) and
step 2 (the LLM call log) and step 3 (the cold tier and insight pool) are built;
steps 4–5 are not.
**Date:** 2026-10-10
**Builds on:** `USAGE_ANALYTICS_AND_GUIDANCE.md` (ledger + notification engine) and
`BILLBOARD_LANDING_PAGE.md` (the landing page).
**Scope:** (1) make the note shown when the popover opens reflect what is
happening *now*, not what a schedule produced hours ago; (2) record every LLM
call the product makes in a daily log the user can open from Settings.

"The note" below is the landing page: the one message the popover shows before
the provider list.

---

## 1. Why notes are stale today

Grounded in the current code:

1. **Notes are written on a clock, not on open.** `daemon._due_slot` fires a
   daily, weekly or monthly slot; `notify_engine.scheduled_messages` builds the
   messages and `ledger.store_message` keeps them. `choose_billboard` then
   shows the best unread one while it is inside `FRESHNESS_HOURS`
   (informative 24h, fun 12h, actionable 6h). Open the laptop the next morning
   and the digest is yesterday's.
2. **The ledger lags by up to an hour.** Harvesting runs every
   `harvest_deep_seconds` (3600s), so a note built from the ledger can be that
   old before it is even written.
3. **Calendar-day windows.** `day_range` and the digests talk about a calendar
   day, so work done at 17:00 is "yesterday" by 08:00 and reads as old news.
4. **Mobile and web usage is invisible to the transcripts.** The Claude
   harvester reads local files, so Claude Code on a phone never lands in the
   ledger. The provider **meters** are the exception: they come from the
   server, include every client, and are already refreshed on popover open
   (`daemon.poll`, 60s cooldown, 300s background poll).

Point 4 shapes the design: a "right now" note has to lean on meters and meter
movement, not on the transcripts.

---

## 2. Three temperatures

Opening the popover selects a tier from how long it has been since the user was
last active or last opened it. **The popover never waits to show something.**
It shows the best cached note immediately; anything slower happens behind it.

| Tier | When (defaults) | Note | Built from | LLM |
| --- | --- | --- | --- | --- |
| **Cold** | First open after ≥ 4h idle, or the daemon just started | Trends and insights: week, day and month shape, plus back-burner tips | Ledger rollups over rolling windows | No — precomputed, instant |
| **Warm** | Inside a working cycle: last open < 2h ago | A "now" note about the last 1–2h | Fresh meters, incremental harvest, meter deltas | Yes — cheapest model on the provider with room (Haiku for Claude) |
| **Hot** | < 10 min since the last warm note | The same warm note | Cache | No |

Thresholds are config values (`live_cold_hours`, `live_warm_hours`,
`live_hot_minutes`), not constants.

### 2.1 Warm flow on open

1. Show the best cached note now.
2. In the background: poll meters (existing path), run an **incremental**
   harvest of recently modified files only (not the full hourly pass).
3. Hash the facts a warm note would use (meter percentages bucketed to whole
   points, session counts, today's token total) into a **fingerprint** and
   compare it with the fingerprint stored on the note being shown.
4. Same fingerprint → keep the note, nothing changes on screen.
5. Different → show a short "Catching up on the last few hours…" line and
   compose with the quick model under a **4s budget**. On timeout, 429 or any
   `LlmError`, fall back to the template wording (the engine already produces a
   correct sentence with no model). The note is then marked
   `source: template`.
6. Swap the note in. No second landing page per open (existing
   `_landingShownThisOpen` rule stands).

The loading line only appears when there is both a real gap and a real change.
Quick re-opens never wait.

### 2.2 The "something ran elsewhere" note

If a meter moved materially since the last `history.db` sample while no local
session was live, the warm note says so, e.g. *"About 18% of your Claude 5h
window went somewhere other than this machine — phone or web, probably."* This
is the only signal available for mobile use and needs no new harvester.

### 2.3 Cold insights

*Built.* The daemon treats each panel open as cold when it is the first since
start or comes `live_cold_hours` after the previous one, and then stores one
insight (no model, no desktop notification) unless an unread one is already
waiting. Rotation is read from the messages table: an insight's key carries the
day (`insight:<id>:<date>`) so a return is a new row that an old acknowledgement
cannot hide, and the newest key under each prefix says when it last had a turn.
Between `live_cold_hours` and the warm window an open is simply "not cold" until
step 4 defines warm and hot.

A rotating pool of insights computed from the ledger over **rolling** windows
(last 7 / 30 days), each with a `last_shown_at` so one does not repeat until the
rest have had a turn. Initial pool:

- cache-read share of tokens this month, with a tip when it is high
- this week vs the previous week
- peak hours and busiest weekday
- project concentration (share of tokens in the top project)
- the existing cheaper-model-did-real-work comparison (`VALUE_SHARE_FLOOR`)
- daily / weekly / monthly shape ("how your day looks")

Every figure comes from a ledger query or a meter. Cold notes never call a
model.

---

## 3. Data-model changes

- **Rolling windows.** Add `rolling_range(hours)` beside `day_range`; the
  digests and warm notes use it. "Last 24h" replaces "yesterday".
- **Message provenance.** Messages gain `as_of` (epoch seconds the facts were
  read), `tier` (`cold` | `warm` | `hot`), `fingerprint`, and
  `source` (`template` | `llm`). Stored in the existing `meta` JSON, so no
  schema break in `usage.db`.
- **Tier-based expiry.** `expires_at_for` takes the tier into account: a warm
  note stops being worth showing after `live_warm_hours`, a cold one after the
  cold window. Kind-based `FRESHNESS_HOURS` stays for scheduled messages that
  keep the old behaviour.
- **Popover shows age.** The note carries "as of N min ago" so a stale note
  describes itself honestly.
- **Insight bookkeeping.** A small table (or `meta` rows) for each insight's
  `last_shown_at`.

---

## 4. Guardrails for open-time LLM calls

- Only call when the fingerprint changed and the tier is warm.
- Cap calls per hour (`live_llm_per_hour`, default 4) and per day
  (`live_llm_per_day`, default 24). Over the cap → template wording.
- Reuse `llm_composer.choose` for routing (capacity first, never the provider
  that is in trouble) and `DEFAULT_MODELS` for the cheap end.
- Respect `LlmRateLimited`: back off that provider for the cooldown, fall back
  to template, and log the refusal (see §5).
- Existing opt-in (`llm_notifications`) still gates everything. Off means no
  warm LLM wording; warm notes fall back to templates.
- A model only rewords figures it was given; the "never invent a figure" rule in
  `notify_engine` is unchanged.

---

## 5. The LLM call log

Every call the product makes to a language model is recorded, and the user can
read the record from Settings. This is for transparency: what was sent, where,
how much it cost, and what came back.

### 5.1 What is a "call"

Every request made through `llm_composer.generate` (and anything built on it:
`rewrite`, scheduled digests, event messages, the new warm composer). Failed
and refused requests are logged too — those are the ones people most want to
see.

### 5.2 What is recorded

One entry per call:

| Field | Meaning |
| --- | --- |
| `ts` | Timestamp, ISO 8601 with offset, local time |
| `trigger` | Why it ran: `open`, `scheduled:daily`, `event:meter`, `manual`, … |
| `tier` | `warm` / scheduled slot name |
| `provider`, `model` | Who was asked |
| `outcome` | `ok` / `rate_limited` / `error` / `timeout` / `skipped` (with reason, e.g. `over_cap`) |
| `latency_ms` | Round trip |
| `tokens_in`, `tokens_out` | From the provider's usage block when present |
| `prompt` | The prompt text sent (it is built only from ledger figures and meter values — no file contents, paths or credentials) |
| `reply` | The text returned |
| `message_kind`, `message_key` | The note this call was for. The note has no row id yet when the call is made, so the `(kind, key)` pair that identifies it is logged instead |
| `error` | Error class and a short message, never a token or header |

The prompt is logged in full because the point is transparency. It is already
constrained to aggregate figures by `build_prompt`; the log must never gain
fields that the prompt does not already contain. Auth headers and tokens are
never logged.

### 5.3 Storage: a daily log, keyed by timestamp

- One file per local day: `llm-calls/YYYY-MM-DD.jsonl` under the data directory
  next to `usage.db` (`~/.local/share/cursor-spend-monitor/`), one JSON object
  per line, appended in time order. JSONL keeps writes atomic and cheap, needs
  no migrations and is trivially greppable.
- Every line leads with its `ts`, and lookups are by timestamp: the Settings
  viewer opens a day and scrolls its entries in order, and a note can link to
  the exact call (`message_kind`/`message_key` ↔ `ts`).
- Files are append-only and written under the daemon's existing lock, one
  writer. A crash loses at most the line being written.
- **Retention:** `llm_log_days` (default 30), pruned alongside
  `ledger.prune`. `0` disables the log entirely; the Settings screen says so.
- Failure to write the log must never fail the call or the note: log errors are
  swallowed with a single stderr line.

### 5.4 Settings screen

A new **"LLM activity"** entry. The panel's "Settings" button opens the config
file outside the popover, so the entry lives on the **About** screen, which is
the in-panel settings-like page:

- Opens to **today**, newest first, with prev/next day and a day picker limited
  to days that have a file.
- Each row: time, trigger, provider/model, outcome, latency, tokens. Tap to
  expand the prompt and the reply.
- Header line with the day's totals: calls, tokens in/out, failures.
- A "Clear log" action and a link showing where the files live on disk.
- Strings go through the existing catalogs (`locales.js`, en / fr / pt-BR);
  `tests/test_locales.py` keeps them in step.

The daemon exposes the log over D-Bus (`LlmLog(day) → json` with the day list,
the day's summary and its entries, and `ClearLlmLog()`), so the extension never
reads files itself. An older daemon without the methods makes the screen say so
rather than fail.

---

## 6. Config

New keys (all with defaults, so existing configs keep working):

| Key | Default | Purpose |
| --- | --- | --- |
| `live_notes` | `true` | Master switch for tiers; off keeps today's behaviour |
| `live_cold_hours` | `4` | Idle gap that makes the next open cold |
| `live_warm_hours` | `2` | Window in which an open is warm |
| `live_hot_minutes` | `10` | Reuse the last warm note inside this |
| `live_llm_per_hour` | `4` | Open-time LLM cap |
| `live_llm_per_day` | `24` | Open-time LLM cap |
| `llm_log_days` | `30` | Retention for the call log; `0` = off |

---

## 7. Build order

1. **Rolling windows, provenance fields, tier expiry.** Pure engine work, no
   LLM, and it removes most of the staleness.
2. **LLM call log** (§5): writer, retention, D-Bus methods, Settings screen.
   Built before any new model call so the new calls are visible from day one.
3. **Cold tier and the insight pool.**
4. **Warm tier:** open-time refresh, incremental harvest, fingerprint diff,
   template note, loading line.
5. **Quick-model composition for warm notes** with the caps in §4, and the
   "ran elsewhere" note.

Stop after each step and try it on a real working day before the next.

---

## 8. Tests

- `rolling_range` boundaries and tier expiry (frozen `now`).
- Tier selection from idle gap (cold / warm / hot edges).
- Fingerprint stability (bucketing) and change detection.
- Warm flow fallbacks: timeout, `LlmRateLimited`, over-cap, `llm_notifications`
  off — each yields a template note, never an error on screen.
- Call log: one line per call including failures; day rollover at local
  midnight; retention prune; log failure does not break the call; no auth
  material in any entry.
- D-Bus log methods and the Settings viewer against `mock_daemon.py`.
- Locale parity for the new strings.

---

## 9. Open questions

- Is 4h the right "cold" threshold for a normal working day, or should it key
  off the first open of the local day instead?
- Should the call log include the prompt in full by default, or show only
  metadata with the prompt behind an "expand" (current proposal: stored in
  full, hidden until expanded)?
- Do we want a "refresh now" affordance on the note for a user who wants a warm
  note outside the 2h window?
