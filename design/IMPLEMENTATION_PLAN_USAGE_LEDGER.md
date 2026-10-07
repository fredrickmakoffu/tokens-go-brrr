# Implementation plan — usage ledger + LLM notification engine

**Implements:** `design/USAGE_ANALYTICS_AND_GUIDANCE.md` (v2)
**Branch:** `feature/usage-ledger-notifications`
**Status:** plan for review — no code written
**Baseline:** 152 tests green (`python3 -m unittest discover -s tests`), stdlib-only (`dependencies = []`), Python ≥ 3.11

This plan turns the design into ordered, independently shippable steps. Each
step states what it creates, the decisions it locks in, its tests, and how to
verify it. The design document stays the *why*; this document is the *what* and
*in what order*.

---

## 0. Ground truth re-verified on this machine

Re-checked before planning, because every harvester is a dependency on a
vendor's private store. Where the design doc and the live store disagree, the
live store wins and this plan follows it.

| Store | Verified now | Consequence for the plan |
| --- | --- | --- |
| `~/.local/share/opencode/opencode.db` (238 MB) | `session` **66 rows, 42 with `cost>0`**; exact `cost`, `tokens_input/output/reasoning/cache_read/cache_write`, `model` JSON `{"id","providerID"}`, `agent`, `directory`, `time_created/updated` (ms). `message` **2 400 rows**, `data` JSON carries per-message `cost`, `tokens{}`, `modelID`, `providerID`. `journal_mode=delete`. | Session-level is authoritative and small; message-level is the fine grain. Watermark on ms timestamps. |
| `~/.claude/projects/*/*.jsonl` | **100 files, 193 MB**. Assistant records carry `message.usage{input_tokens, cache_creation_input_tokens, cache_read_input_tokens, output_tokens, output_tokens_details.thinking_tokens}`, `message.model` (`claude-opus-5-5`), `sessionId` **and** `session_id`, `cwd`, `timestamp` (ISO Z), `entrypoint`. | Per-file byte-offset watermarks are mandatory: a full re-read of 193 MB per harvest is not acceptable. |
| `~/.codex/state_5.sqlite` | `threads` **empty** (`backfill_state`=1, `thread_sections`=1). `logs_2.sqlite` has 3 693 log rows, **no token fields**. | Codex harvester is a fail-soft no-op today; must not crash and must not invent rows. |
| `~/.cursor/ai-tracking/ai-code-tracking.db` (81 MB) | `ai_code_hashes` **183 444 rows** (`source`, `fileExtension`, `fileName`, `requestId`, `conversationId`, `timestamp`, `model`, `createdAt`); `scored_commits` 7 rows. | v2 harvester; not on the critical path for tokens. |
| `~/.local/share/opencode/auth.json` | key `opencode-go` present. | OpenCode Zen generator auth is available. |
| `~/.local/share/cursor-spend-monitor/history.db` | Percent-sample store already lives here. | Put `usage.db` **beside** it, not merged: different lifetime, different retention (90 d samples vs 90 d sessions + long-lived rollups). |

### Corrections to the design's schema (§5.1) that this plan applies

1. **`sessions` has no uniqueness key in the design.** Without one,
   re-harvesting double-counts and a live session cannot be updated as it grows.
   Add `UNIQUE(provider, external_id)` and make every harvester **UPSERT**.
   (Design rule §5.3.1 says "every write is keyed (UNIQUE constraints)"; the
   schema as written contradicts it.)
2. **`per_model` column list is untyped** in the doc (missing `INTEGER`/`REAL`).
   Fix while implementing; keep `UNIQUE(provider, model, cycle_key)`.
3. **Delta-folding `sessions` → `daily`/`hourly` is wrong when sessions are
   upserted.** A running Claude/OpenCode session's token totals change between
   harvests, so "add the delta and mark folded" double-counts. Instead:
   **recompute the affected day(s) from `sessions` with `GROUP BY`** and
   `INSERT OR REPLACE` into `daily`/`hourly`. Cheap (indexed, few thousand rows)
   and idempotent by construction. `folded` is dropped; a `harvest_state` table
   holds watermarks instead.
4. **Generated messages need a home.** The design has the engine but no store
   for the message cache / cooldown keys / `quote` and billboard source. Add a
   `messages` table to `usage.db` from the start (one migration less later).
5. **`billboard` is an additive state field.** It does not change the meaning of
   any existing field, so `state.SCHEMA_VERSION` stays `1`; the extension treats
   a missing `billboard` as "no quote" (which is exactly what an older daemon
   does).
6. **The schema needs a no-op test, or `harvest` cannot report honestly.**
   SQLite counts an `ON CONFLICT DO UPDATE` as a change even when every value is
   identical, so `total_changes` would report a phantom write on every run and
   Phase 2's "second harvest writes 0 rows" could never be shown. Add
   `sessions.content_key` / `per_model.content_key` (a hash of the mutable
   values) and a `WHERE … IS NOT excluded.content_key` on the update. **Found
   during implementation, not at plan time.**
7. **`daily.project` / `daily.model` are `NOT NULL DEFAULT ''`, not nullable.**
   A SQLite `UNIQUE` constraint does not treat two NULLs as equal, so a nullable
   key would silently admit duplicate rollup rows. **Found during
   implementation.**
8. **`period_totals` takes a grouping name from a fixed whitelist.** No column
   or table name is interpolated; each grouping is a written-out statement with
   bound values only (`COALESCE(NULLIF(?, ''), provider)` for the optional
   filter, `LIMIT -1` for "no limit").

### House style this plan follows

- **stdlib only** (urllib, sqlite3, json, argparse, threading, GLib via gi).
- Vendor readers are **fail-soft**: a locked DB, a mid-write JSONL, or a 429
  disables *that* harvester for the cycle and says so once — never the daemon
  (the `history.Recorder` tolerance discipline).
- Storage problems never stop monitoring: the panel is the product.
- Tests are `unittest`, one file per module, fakes over network, temp dirs over
  real stores.
- Docstrings say *why*, in the existing voice.

---

## Phase 1 — Ledger core (`ledger.py`)

**Status:** ✅ **done.** `cursor_spend_monitor/ledger.py`, `report` CLI in
`cursor_spend_monitor/__main__.py`, and `tests/test_ledger.py` (64 tests).
Full suite 216 green; pi-lens clean apart from two duplicate-code warnings.
Verified end to end: a second harvest of an unchanged store reports **0 rows
changed**, and `report` prints provider/project/model/day totals plus an
`includes estimated sessions` note.

**Goal:** the storage foundation exists, is idempotent, and answers period
questions — before any notification uses it.

### Step 1.1 — Schema and connection

New `cursor_spend_monitor/ledger.py`:

- `default_path()` → `~/.local/share/cursor-spend-monitor/usage.db` (respect
  `XDG_DATA_HOME`, same helper shape as `history.default_path`).
- `SCHEMA` with, from the design plus the corrections above:
  - `sessions` (`UNIQUE(provider, external_id)`, the full token-kind columns,
    `meta` JSON, indexes on `(provider, started_at)` and `(project)`),
  - `per_model` (typed),
  - `daily` and `hourly` (`UNIQUE(...)` as designed),
  - `harvest_state(harvester TEXT PRIMARY KEY, watermark TEXT, note TEXT, updated_at INTEGER)`,
  - `messages(id INTEGER PK, kind TEXT, key TEXT, created_at INTEGER, provider TEXT, body TEXT, share TEXT, UNIQUE(kind, key, created_at))`,
  - `ledger_meta(key TEXT PRIMARY KEY, value TEXT)` carrying a **format
    version** per vendor reader (`claude_jsonl=1`, `opencode_db=1`, …) so a
    vendor schema move is recorded rather than silently misread.
- `connect(path=None)` — `sqlite3` with `PRAGMA journal_mode=WAL`,
  `busy_timeout`, foreign keys off; creates dirs.
- `upsert_sessions(con, rows)`, `upsert_per_model(...)`, `record_check(con, ...)`.
- `prune(con, keep_days)` — raw `sessions` only; `daily`/`hourly` kept longer.
- An `ensure_schema` migration guard: if `ledger_meta.format_version` is newer
  than this build understands, refuse to write and say so (read-only fallback).

### Step 1.2 — Folding (recompute, not accumulate)

- `fold_days(con, days: set[str])` → for each `YYYY-MM-DD`, `DELETE` + recompute
  `daily` and `hourly` from `sessions` with `GROUP BY day/provider/project/model`
  (and hour in **local** time for `hourly`, as designed).
- `fold_all(con)` for `harvest --full`.
- `affected_days(rows)` helper so harvesters fold only what they touched.

### Step 1.3 — Query surface (`report`)

- `period_totals(con, since, until, group_by=...)` →
  provider / project / model / day / hour rollups.
- `top(con, ...)`, `streaks(con)` (consecutive days with ≥1 session),
  `records(con)` (max tokens in a day, longest session, most expensive session),
  `cache_share(con, day)`, `session_shape(con)` (duration buckets + hour buckets),
  `model_split(con, provider)`.
- Each returns plain dicts; **every** result carries `sources` so an aggregate
  can say "includes 1 estimate" (design §5.3.2).

### Step 1.4 — CLI surface

- `cursor-spend-monitor harvest [--full] [--provider ID]…` — run harvesters,
  fold, prune; print one line per harvester (`opencode: +12 sessions`,
  `codex: no local data (probe only)`). **Deferred to Phase 2**, where it has
  harvesters to run; shipping a command that can only say "nothing registered"
  would be worse than not shipping it yet.
- ✅ `cursor-spend-monitor report [--days N | --week | --month | --since
  --until | --checks] [--by GROUP] [--provider ID] [--limit N] [--json]` —
  shipped. Answers the historical questions from the ledger alone, with no
  credentials and no network.

### Step 1.5 — Tests (`tests/test_ledger.py`)

- schema created once; `connect` twice is stable;
- upsert same session twice → one row, updated values;
- fold is idempotent and recomputes when a session grows;
- `prune` keeps rollups, drops old raw sessions;
- report totals for a synthetic two-provider/two-project month;
- a newer on-disk format version makes the writer refuse, not corrupt.

**DoD:** `harvest` twice changes nothing; `report --month` gives provider,
project, model and cost totals from real data; `python -m unittest discover -s tests` green.

---

## Phase 2 — Harvesters (`harvesters/`)

**Goal:** accurate tokens for the three sources that matter, honest labels for
the two that do not, all idempotent and fail-soft.

**Status:** ✅ **done — all five readers.** `harvesters/` now holds `base.py`
(the contract), `opencode_db.py`, `claude_transcripts.py`, `dashboard_usage.py`
(Cursor), `codex_state.py` and `pi_sessions.py`, plus the `harvest` CLI and six
test modules. Full suite **321 green**.

One `harvest` against every real store on this machine:

```text
opencode:     66 sessions, 15 day(s) folded
claude_jsonl: 76 sessions, 22 day(s) folded
cursor_api:   0 sessions, 7 model rows
codex_state:  no change (0 scanned)
pi_sessions:  2 sessions, 1 day(s) folded
```

Second run: every reader `no change`. `report` then reads **144 sessions and
2B tokens** across Claude, OpenCode and Pi. `pi_sessions` records **0 tokens** —
correctly, because Pi persists none.

**Corrections the live data forced (the design's assumptions were partly wrong):**

- **Claude records duplicate each response.** 1 296 usage records stand for 691
  responses in the largest transcript; summing lines inflates a session ~1.9×.
  Dedupe is by `message.id`, held in a new `transcript_messages` table so it
  survives a byte offset — a re-read cannot double-count.
- **Claude writes subagent transcripts separately** (25 of them here, at
  `<sessionId>/subagents/agent-*.jsonl`), all billed to the parent session. The
  reader walks the whole tree and attributes them to the parent.
- **Cursor's endpoint needed probing.** `GetAggregatedUsageEvents` returns `{}`
  for an empty body; `startDate`/`endDate` must be **epoch milliseconds** (an
  ISO string is rejected); a range beyond ~a quarter answers HTTP 500; token
  fields are **strings**. `modelIntent` does carry real model names.
- **Cursor's slow-pool flag does not exist.** `GetUsageLimitPolicyStatus`
  returns only `canConfigureSpendLimit` and `creditRequestButtonHidden`. The
  design's slow-pool trigger has no source, and the reader records that as a
  cross-check rather than pretending otherwise.
- **Cursor's cost unit is unverified.** `totalCents` is taken as USD cents, and
  every run records a `cost_unit` cross-check comparing the row sum against the
  plan's own figures so a wrong unit shows up as a visible disagreement.
- **Pi's residual estimate is not derivable** and was dropped (decision D-2 was
  approved, then found impossible): the meters are percentages of a limit, and
  no provider publishes that limit in tokens, so there is no absolute quantity
  to subtract other tools' usage from. Pi contributes sessions, models, projects
  and durations, with zero tokens and no estimate.

**Decisions taken during implementation, with reasons:**

- The reader is `harvesters/opencode_db.py`, not `harvesters/opencode.py`.
  Pyright could not resolve a relative import to a sibling module literally
  named `opencode` in this package (`.base` resolved, `.opencode` did not;
  absolute failed too), and `opencode_db` names what the reader reads. Later
  readers follow `<vendor>_<source>.py` (`claude_transcripts.py`,
  `cursor_api.py`).
- `provider` is the **tool** (`opencode`); the billing account (`opencode-go`,
  or a bring-your-own-key provider) is kept in `meta.account`. Splitting the
  tool into one ledger provider per account would give every digest two rows for
  what the panel calls one provider.
- `turns` comes from a correlated `COUNT(*)` over OpenCode's `message` table,
  with a second static query for older stores that lack that table.
- `ledger_days` and `harvest_deep_seconds` landed early (planned for Step 3.3)
  because `harvest` and `report` need the first of them now.
- A pre-existing defect found on the way: `MonitorConfig.load()` raised on a
  corrupt or hand-edited config file, taking down the daemon and every CLI
  command with it. It now falls back to defaults and says so once.

New package `cursor_spend_monitor/harvesters/` with a shared contract:

```python
class Harvester(Protocol):
    id: str                       # "opencode" | "claude" | "cursor_api" | ...
    def available(self) -> bool: ...
    def harvest(self, con, *, full: bool = False) -> HarvestResult: ...
```

`HarvestResult`: `{rows, sessions, folded_days, watermark, note, disabled}`
— used verbatim by the `harvest` CLI and by tests.

### Step 2.1 — `harvesters/opencode_db.py` (first: exact, easy, local) ✅

- Open `~/.local/share/opencode/opencode.db` **read-only** (`mode=ro`, *not*
  `immutable=1` — the TUI writes it live). `SQLITE_BUSY`/`locked` → skip this
  cycle, note it once.
- Read `session` rows where `time_updated > watermark` (ms). Parse `model` JSON
  → `model` + `model_family` (downcased, de-versioned), `provider` =
  `providerID` (`opencode-go` → provider id `opencode`), `project` =
  `basename(directory)`, `started_at = time_created/1000`,
  `ended_at = time_updated/1000`, `duration_s`, all five token kinds, `cost`,
  `agent` into `meta`. `external_id = session.id`.
- Upsert; fold affected days; persist `time_updated` as the watermark.
- Optional (behind `--full`): also roll `message` rows for finer grain later.

### Step 2.2 — `harvesters/claude.py` (richest, needs byte offsets)

- Enumerate `~/.claude/projects/*/*.jsonl`. For each file keep
  `(path, size, mtime, offset)` in `harvest_state` (JSON watermark).
- **Tail only new bytes**: seek to the stored offset, discard a partial first
  line if the seek landed mid-line, parse complete lines only, store the new
  offset. A file that shrank (rotation/rewrite) resets its offset to 0 and is
  recorded as a re-read.
- Aggregate assistant records into one row per `sessionId`: sum
  `input_tokens`, `cache_creation_input_tokens` → `tokens_cache_write`,
  `cache_read_input_tokens`, `output_tokens`,
  `output_tokens_details.thinking_tokens` → `tokens_reasoning`; take `model`,
  `cwd` → `project`/`directory`, first/last `timestamp` → `started_at`/
  `ended_at`/`duration_s`, count turns, `entrypoint` into `meta`.
- Upsert by `external_id = sessionId` (a running session is re-read on later
  harvests and its row grows). `source = "local-transcript"`.
- Guard the reader with `ledger_meta.claude_jsonl=1`; a record missing `usage`
  is skipped, not an error.

### Step 2.3 — `harvesters/cursor_api.py` (cycle-level, not per session)

- **Begin with a probe step:** one authenticated `GetAggregatedUsageEvents` call
  through the existing `CursorUsageClient._connect_json`, dumping the raw
  response to `harvest_state` and a `report --probe` output. Field names in the
  design (`aggregations[].modelIntent/inputTokens/outputTokens/cacheWriteTokens/cacheReadTokens/totalCents/tier`)
  are accepted only once the live payload confirms them — same discipline as
  Codex. If the shape differs, the reader is written against the payload and the
  version bumped.
- Write `per_model` rows keyed `(provider='cursor', model, cycle_key)` where
  `cycle_key` is the billing-cycle end. **Do not** fabricate sessions —
  Cursor gives cycle-level only, and the design says so.
- Cross-check: `Σ per_model.cost` vs `GetCurrentPeriodUsage.planUsage` spend →
  a `checks` row when they disagree beyond a tolerance; never silently
  "correct" a number (design §5.3.3).
- Probe `GetUsageLimitPolicyStatus`; on success store the slow-pool flag in
  `harvest_state` and expose it for the event trigger (Phase 4).

### Step 2.4 — `harvesters/codex.py` (honest no-op)

- Read `~/.codex/state_5.sqlite.threads` if non-empty (target fields
  `tokens_used`, `model`, `model_provider`, `cwd`, `created_at/updated_at`);
  today it is empty on this machine.
- Record the **raw usage-endpoint payload shape** once into `harvest_state`
  (this is the design's "spend one v1 task capturing the raw payload"). If
  absolute token windows ever appear, emit `source: "codex-api"` rows; until
  then emit nothing and a note.
- Must never crash on a missing/empty/migrated DB.

### Step 2.5 — `harvesters/pi.py` (sessions without tokens)

- Sessions from the existing `/proc` scan + `pi_backend` resolver (model,
  project, directory), duration from `agent-summary{durationMs}` in the session
  log, `source = "local-db"`, all token columns 0/NULL — **not** zero-cost rows
  that pretend to be measured.
- Optional labelled residual estimate (design §4.5): only when Pi was the sole
  active consumer of that account in the interval; `source = "estimate"`,
  flagged, never silently blended. **Gated on the decision in §D-2 below.**

### Step 2.6 — Replay, cross-check, retention

- `harvest --full` rebuilds every harvester from scratch and refolds all days.
- Cross-check rows for Claude (transcript Σ vs usage buckets) and Cursor
  (above); surfaced by `report --checks`.
- Wire `prune(keep_days=config.ledger_days)` into every harvest.

**DoD:** on this machine, one `harvest` writes ~42 OpenCode sessions with exact
cost, the Claude sessions from 100 transcripts, and Cursor `per_model` rows; a
second `harvest` writes **0** rows; Codex reports "no local data" and exits 0;
Claude/OpenCode numbers match the vendors' own dashboards within tolerance.

---

## Phase 3 — Daemon integration

**Goal:** the ledger fills itself without a user command, and can never take the
daemon down.

**Status:** ✅ **done.** `LedgerRecorder` was added in Phase 1 and is now wired
into `UsageDaemon`: a `_harvest_tick` timer at `harvest_deep_seconds` runs every
reader on a worker thread (the first run of a process may backfill, later ones
are strictly incremental), then prunes to `ledger_days`. A reader that raises is
logged and skipped — it can never stop the daemon. `ledger_days` and
`harvest_deep_seconds` are config fields.

**Deviation:** Cursor's per-model spend is a *cycle* aggregate, so the reader
asks for one billing cycle and, on a first or `--full` run, the equal-length
window before it — which is the previous cycle exactly when cycles are of equal
length. That recovered a real **7 rows / $475.74** that would otherwise have
waited a month.

### Step 3.1 — Deep harvest timer

- Add `LedgerRecorder` (fail-soft wrapper, mirroring `history.Recorder`) plus a
  GLib timer at `harvest_deep_seconds` (default 3600) in `UsageDaemon`. First
  run at idle after startup.
- Run the heavy harvesters on a worker thread (`threading.Thread`, as `poll`
  already does) and write on the GLib thread; never block the panel.

### Step 3.2 — Cheap event / session-end harvest

- When the instance scan sees a provider's session set shrink, schedule a
  targeted harvest for that provider (a session just ended — its row is final).

### Step 3.3 — Config

- `ledger_days` (90), `harvest_deep_seconds` (3600) into `MonitorConfig` +
  `save()`; `config` command prints them.

### Step 3.4 — Tests

- a harvester that raises disables itself once and the daemon still publishes;
- the timer is scheduled at the configured interval;
- a session-set shrink triggers one targeted harvest.

**DoD:** daemon runs for an hour, `usage.db` grows by itself, no unhandled
exception when `opencode.db` is locked concurrently.

---

## Phase 4 — Notification engine, templates first

**Goal:** every trigger and every message type works end-to-end **without** an
LLM, so the LLM is an upgrade, not a dependency.

**Status:** ✅ **done, templates only.** Shipped as **one module**,
`cursor_spend_monitor/notify_engine.py`, rather than a package: the pieces share
one small vocabulary (`Message`, the cooldown, the ranges) and a single file is
easier to hold in the head than six that import each other. It covers the
trigger set, the mixer (daily = digest + fun fact, weekly = digest, monthly =
digest + share line), the wording for every catalog row it ships, the
cooldown/cache through the `messages` table, quiet hours, and delivery.

Surfaces: `quote` (`--generate`, `--slot`, `--tweet`, `--json`) reads the ledger
and copies a `SHARE:` line to the clipboard with nothing posted anywhere; the
daemon sends scheduled digests on a timer and event alerts from the live meters,
and publishes a `billboard` field in state for the panel to quote.

`tests/test_notifications.py` (27 tests) pins the properties that matter: an
empty ledger produces no digest, a period containing an `estimate` says so, no
fun fact or share line is invented from nothing, a borrowed row is never counted
twice, and a cooldown holds a `(kind, key)` and releases it after the window.

**Not yet done here:** the LLM wording (Phase 5) and the panel's rendering of
`billboard` (Phase 6, second half). Everything works without both.

### Step 4.1 — `events.py` (triggers)

From snapshots + `burn.eta_seconds`, emit events: threshold crossing, burn ETA
`< wind_down_hours`, meter ≥ 100, reset-landed-hot (Claude 5h resets > 50%),
Cursor slow-pool flag, Pi estimate flip. Each event has
`(kind, key, provider, facts)` and is deduped by the message cache.

### Step 4.2 — `schedule.py` (two clocks)

- GLib timers for daily (default 18:00 local), weekly (Monday), monthly (1st),
  all configurable, honouring `notify.silent_hours`.
- Scheduled slots are generated ahead and cached; a generation timestamp +
  `(kind, key)` row prevents regeneration inside the cooldown.

### Step 4.3 — `mixer.py` (§8.5)

- daily: 1 informative digest + 1 fun fact + 1 rotating SHARE line;
  weekly: digest + project spotlight + session-shape; monthly: digest + MoM
  delta + records; events: actionable only.
- `shareable_share` biases scheduled slots; `notify.types` gates families.

### Step 4.4 — `digest.py` (ledger → facts)

One function per §8 row, each a thin call into `ledger.py` queries. No raw
transcripts ever enter a prompt — numbers only.

### Step 4.5 — `templates.py` (fallback wording)

Deterministic sentences for every kind, used when the LLM is off, over its
quota, or below the headroom floor. The trigger/ledger path is identical, so
turning the LLM on changes wording only.

### Step 4.6 — Delivery + config

- Desktop `notify.send`, `cursor-spend-monitor quote [--tweet]` printing the
  latest message (clipboard for `--tweet`; no auto-post),
  `messages` cache in `usage.db`.
- Config additions from §10: `wind_down_hours`, the whole `notify` block,
  `llm_notifications` (default false in this phase).
- Tests: cooldown suppression, quiet hours, each event trigger, each catalog
  query against a seeded ledger.

**DoD:** with `llm_notifications: false`, a seeded ledger produces a weekly
digest, a fun fact and a SHARE line; a forced 92% meter produces an actionable
template; `quote` prints the latest; nothing repeats inside its cooldown.

---

## Phase 5 — LLM routing + generation

**Goal:** swap wording for an LLM chosen by capacity, with hard floors and
template fallback.

**Status:** ✅ **done.** Shipped as **one module**, `llm_composer.py`, rather than
`routing.py` + `generators/` + `prompt.py`. Those three are one pipeline sharing
one vocabulary, and a single file keeps the whole contract in view — the same
reasoning that turned Phase 4's package into `notify_engine.py`.
`tests/test_llm_composer.py` adds 40 tests; the suite is at 391.

What it does: picks the writer by short-window headroom (weekly/rolling, with
monthly only a tiebreak and the trigger provider excluded outright), asks for the
wording **and** for `FEATURED: <id>` chosen from a ranked list of real provider
facts, validates that id and falls back to the derived one, and returns the
template on every failure — no generator with room, a missing credential, a 429,
an unparseable reply. Credentials are opened read-only for both providers, and a
test asserts the file's bytes and mtime are unchanged afterwards.

Wired into the daemon through `_compose`, which runs on a **worker thread**
because a network call on the main loop would freeze the panel, and delivers back
through `GLib.idle_add`. `_deliver` owns the sending so both the scheduled and
the event path share it.

**Not verified here:** no live call was made, so the two endpoints and the
default model ids are unproven against the real services. A wrong model id
degrades to the template, which is exactly why that is survivable.

### Step 5.1 — `routing.py` (§6.2)

- Score providers with usable meters: rolling/weekly headroom primary, monthly
  tiebreak, trigger provider excluded outright, generator pool `{claude,
  opencode}`, floor `llm_min_headroom`.
- `choose(config, snapshots, trigger)` → `(provider, model)` or `None`.

### Step 5.2 — `generators/` (two verified endpoints)

- `anthropic.py`: `POST https://api.anthropic.com/v1/messages`, headers
  `anthropic-version` + `oauth-2025-04-20`, token read **read-only** from
  `~/.claude/.credentials.json` (never refreshed, ever — the "signed you out of
  the CLI" bug class).
- `opencode_zen.py`: `POST https://opencode.ai/zen/v1/chat/completions`
  (OpenAI-compatible), key read read-only from `~/.local/share/opencode/auth.json`
  (`opencode-go.key`).
- Shared `HTTPTransport`: 30 s timeout, 429 backoff, `max_tokens ≈ 200`,
  `temperature ≈ 0.4`, no retries that spend twice.
- Tests stub `urllib.request.urlopen`; assertions include **credential file
  bytes/mtime unchanged** after generation.

### Step 5.3 — `prompt.py` (§6.3)

- Assemble state + ledger facts into the JSON context shown in the design;
  instruct ≤ 3 sentences, one concrete action when actionable, never invent
  numbers, and the `SHARE:` one-liner (≤ 200 chars) when a shareable variant is
  requested.
- **Ask for the featured provider too.** The reply carries `FEATURED: <id>`
  alongside the sentence, chosen from the ranked provider facts in the prompt.
  Without it the panel renders a badge for whoever the ledger ranked first
  while the prose talks about someone else. Validate the id against the
  providers we know and fall back to `notify_engine.featured_provider` — see
  `design/BILLBOARD_LANDING_PAGE.md` §4b.

### Step 5.4 — Wire into the mixer

- Try the chosen generator; on any failure or below-floor headroom, fall back to
  `templates.py` from Phase 4. Cache by `(kind, key)`+cooldown.
- `llm_notifications` default false until this phase ships; `LLM_GENERATOR_*`
  config from §10.

**DoD:** a forced event with healthy generator headroom yields a 1–3 sentence
LLM message containing only ledger numbers; with headroom below the floor it
yields the template; a 429 yields the template; credential files are untouched.

---

## Phase 6 — The landing page (the only UI change)

**Authoritative design:** `design/BILLBOARD_LANDING_PAGE.md`. This phase is the
implementation order for it; read that document for the routing rules, the state
contract and the open decisions.

**Status:** ✅ **implemented** — daemon, protocol, extension and fixtures — with
one piece of QA outstanding (it has not been seen on a real screen yet).

What shipped: `messages.seen_at` plus the ledger's first additive migration;
`notify_engine` priority/freshness/`featured_provider`/`choose_billboard`;
`billboard` and `latestMessage` in state; `Acknowledge` on D-Bus; the `landing`
screen with Continue, Copy and a Latest header button; a `has-update` ring on the
dot; the `ai-usage-landing-*` styles; and fixtures in both devtest daemons.
`tests/test_billboard.py` adds 26 tests, and the suite is at 349.

The featured AI is **derived from the ledger** rather than mapped, per §4b: the
leader by tokens (`leading`), or a cheaper provider with a real share of the
work (`value`), or the provider with the most live headroom for an actionable
message (`suggested`).

The panel gains one screen: a notification blown up as a quote, with the AI it is
about underneath (icon and name) and a **Continue** back to the provider list. It
does **not** appear on every open — the daemon decides whether anything is worth
interrupting for, and remembers a dismissal so it survives a logout.

> The design's own note applies here: the earlier §9 of the analytics doc
described a weaker version (a quote swapped in place of the list, dismissed by a
chevron or a timer) with no way to tell which message deserved the interruption
and no memory of being dismissed. That is why it would have shown on every open.

### Step 6.1 — Routing policy, in the daemon

- `notify_engine`: a `PRIORITY` per kind and a freshness window per kind;
  `expires_at` on `Message`; **digests start setting `provider`** (only
  actionable messages set it today), plus the `role` the landing page renders.
- `ledger`: `messages.seen_at`, plus a **guarded, idempotent** `ALTER TABLE`
  migration. This is the first additive schema change since the ledger shipped,
  so it has to upgrade an existing `usage.db` in place rather than demanding a
  fresh one. Also `mark_message_seen(id)`; `latest_message()` stays agnostic to
  acknowledgement and expiry.
- `billboard_for(con, now)`: unacknowledged and unexpired, priority then newest,
  one message or `None`.

### Step 6.2 — Publish and acknowledge

- State gains `billboard` (the one message to show, or `null`) and
  `latest_message` (newest regardless of ack or expiry). Additive, so
  `state.SCHEMA_VERSION` stays `1` and an older extension behaves as it does now.
- D-Bus gains `Acknowledge(id)`, wired through `dbus_service` to the daemon, so a
  dismissal is durable across logins and extension reloads.

### Step 6.3 — Extension

- A `landing` screen dispatched beside `list`/`detail`/`sessions`/`guide`/`about`;
  the open-flow routes to it on a per-session `_landingShownId`.
- Continue (acknowledge, then the list), a quieter Skip chevron, and Copy for
  `SHARE:` lines via `St.Clipboard`.
- A **Latest** header button, shown only when a message exists, and a subtle
  `has-update` marker on the status dot.

### Step 6.4 — Styles and devtest

- `ai-usage-landing-*` classes in `stylesheet.css`. There is no quote styling to
  reuse today; this is new CSS.
- `devtest/mock_daemon.py` gains a `billboard` and a way to cycle to the next
  message; `stress_daemon.py` gains a maximum-length quote to prove wrapping.

**DoD, against the mock daemon:** open → quote → Continue → list; reopen → list
with no repeat; Latest → quote; a new mock message lands again; an acknowledged
message never lands; `billboard` is `null` on an empty ledger. Plus the Python
routing tests in `tests/test_billboard.py`, including that the migration is a
no-op the second time it runs.

---

## Phase 7 — Docs, version, and release hygiene

**Status:** ✅ **done.** README consolidated (two earlier appends had left the
ledger section duplicated) and extended with the landing page and the LLM
wording, including the note that the default generator model ids are unverified.
Version bumped to **0.5.0** in `pyproject.toml` and `__init__.py`.

`design/UI_TEST_GUIDE.md` is new: the panel tested by clicking, with commands
that make the daily/weekly/monthly clocks and the actionable alert fire on
demand rather than being waited for.

**Deliberately not done:** `metadata.json`'s integer `version` is left at `1`.
GNOME Shell refuses to hot-reload an extension whose version changed while
unloaded ("you need to log out"), and the live-reload workflow depends on being
able to swap the running extension without a logout. That integer only matters
for extensions.gnome.org.

---

## Phase 8 — Tune against real data

- Run a week of real harvests; inspect `report --checks` for cross-check drift;
  tune `shareable_share`, digest hour, quiet hours; confirm each §8 catalog row
  reads truthfully from real numbers.

---

## Dependency order at a glance

```text
1 ledger core ──► 2 harvesters ──► 3 daemon ──► 4 templates ──► 5 LLM
                                                      │            │
                                                      └──► 6 billboard ◄┘
                                                                   │
                                                      7 docs ──► 8 tune
```

Phase 4 is deliberately before Phase 5: triggers, routing inputs, caching and
delivery are all testable with templates, so the LLM cannot become a hidden
dependency of the schedule.

---

## Decisions — confirmed

| # | Decision | Confirmed | Affects |
| --- | --- | --- | --- |
| D-1 | v1 harvester set | **opencode + claude + cursor_api** now; Codex probe-only; Pi sessions with the D-2 estimate | Phase 2 |
| D-2 | Pi token figures | **Include the labelled residual estimate**, `source="estimate"`, shown as an estimate in every aggregate | 2.5, §8 digests |
| D-3 | Digest cadence / quiet hours | **daily 18:00, weekly Monday, monthly 1st**, all configurable; default silent hours 22:00–07:00 | Phase 4 |
| D-4 | Month anchor | calendar month for digests; per-provider billing cycle only inside per-provider breakdowns | Phase 4 |
| D-5 | SHARE delivery | **No auto-post**; `quote --tweet` copies to clipboard | 4.6, 8.4 |
| D-6 | Billboard placement | popover open-time only, shown once per message; no extra desktop notification | Phase 6 |

---

## Risks carried into implementation

1. **Format drift** — every reader is versioned in `ledger_meta`, fail-soft, and
   probe-first where the shape is unconfirmed (Cursor aggregations, Codex).
2. **Live-store locking** — OpenCode's DB is written by the TUI; read-only +
   busy-skip + note-once.
3. **193 MB of Claude transcripts** — byte-offset watermarks are not an
   optimisation, they are required; a full re-read is the failure mode to test.
4. **Upsert/fold double-counting** — the reason folding recomputes days instead
   of accumulating deltas.
5. **Generator quota irony / privacy / notification fatigue** — floors, caching,
   cooldowns, quiet hours, numbers-only prompts (design §12).
