# Usage ledger + LLM notification engine — design & feasibility (v2)

**Status:** proposal for review — nothing implemented
**Date:** 2026-10-04 (v2 — supersedes the v1 analytics doc: storage-first, notifications as the product, minimal UI)
**Scope:** (1) store accurately how the user's AI spend is actually used — tokens
per provider, per model, per project, across time; (2) periodically prompt an
LLM — intelligently routed to the provider with the most capacity, judged
mostly on rolling/weekly limits — to compose useful, fun, informative, and
Twitter-shareable notifications; (3) optionally let the existing GNOME panel
act as a rotating billboard that shows one of those messages in quote form
instead of the provider list, with Next / 4-second fallback.

What we are deliberately *not* building: analytics dashboards, per-provider
token charts, a usage UI. The ledger is written to be read by the notification
engine, not by eyeballs. The only UI change is the quoting billboard on the
existing popover.

Everything below is grounded in what I audited on this machine and against the
live provider APIs — every "we can / we can't" is a statement about a real
store.

---

## 1. The product in three lines

1. **Store.** A local SQLite ledger (`usage.db`) records every AI session we can
   see — provider, model, project, tokens by kind, cost, duration, timestamp —
   harvested cheaply and idempotently from the tools' own data stores.
2. **Route.** On a schedule and on events, the daemon picks the LLM account with
   the most capacity (rolling/weekly limits primarily, monthly secondarily,
   never the provider that is itself in trouble).
3. **Speak.** That LLM receives a tight prompt of real figures and returns a
   short human message — personal, fun, or shareable — which we deliver as a
   desktop notification, to the terminal, and/or to the panel billboard.

---

## 2. Verdict in one table

| Requirement | Feasible? | Primary source |
| --- | --- | --- |
| Accurate storage: tokens per provider across a period | ✅ **Cursor, Claude, OpenCode**; ⚠️ Codex (live probe needed); ❌ Pi (estimate only) | Cursor `GetAggregatedUsageEvents` API; Claude local transcripts; OpenCode `opencode.db` |
| Storage: tokens per **session** | ✅ Claude (by `sessionId`), ✅ OpenCode (`session` table), ⚠️ Cursor (cycle-level only, no session split), ⚠️ Codex, ❌ Pi | local transcripts / sqlite |
| Storage: **model** within provider (deepseek/gwen/gpt/opus…) | ✅ Cursor API per-model rows; OpenCode `session.model`; Claude `message.model`; ⚠️ Codex; Pi: model *names* yes, tokens no | see column 2 |
| Storage: **project** + time-of-day + duration | ✅ Claude/OpenCode/Pi logs carry `cwd` + timestamps; duration = first→last message | ledger |
| Intelligently route the notification LLM by capacity (rolling/weekly first) | ✅ rolling/weekly meters exist for Claude & OpenCode; `codex` window exists; cursor monthly is secondary; routing table in §6.2 | existing meters |
| Periodically prompt that LLM → user-facing notification | ✅ Gemini-free: Claude via Anthropic Messages API (OAuth token we already read) and OpenCode via Zen chat endpoints; capped, cached, opt-in | `api.anthropic.com/v1/messages`, `opencode.ai/zen/v1/chat/completions` |
| Fun / informative / Twitter-shareable content from the ledger | ✅ every candidate in §8 is a plain SQL aggregation plus one LLM call | ledger |

Honest gaps (unchanged from v1, they decide what we *can* notify about):

- **Pi** persists no token/cost history — sessions/models/projects/durations
  are stored; token figures for Pi are only an **estimate** (`source:
  "estimate"`), or omitted.
- **Codex on this machine** has no local session data and the usage endpoint
  refuses non-browser clients half the time — the Codex harvester is
  schema-probing and fail-soft; if the endpoint ever yields absolute token
  windows we start recording immediately.

---

## 3. Audit of today (what we extend)

Verified in code:

- **Meters** (percent-of-limit per provider): Cursor (monthly, other), Claude
  (5h / weekly / opus / sonnet), OpenCode Go (rolling / weekly / monthly),
  Codex (window / monthly), Pi (borrows its backend's meters). Resets included.
- **Live sessions**: `/proc` scan every 3 s → active/suspended counts, projects,
  per-session backend+model for Pi.
- **History**: `history.db` — percent samples only → burn-rate ETAs
  (`burn.py`, deliberately conservative).
- **Alerts**: desktop notifications at percent thresholds, cooldown-gated.
- **CLI**: `status` / `check` / `best` / `config` / `setup` / `run`.

What's missing (the gaps this design fills):

1. No absolute quantities — everything is a percent; nothing records *tokens*.
2. No event ledger — cannot say "this month: X sessions, Y tokens, top model,
   top project".
3. No persistence of *which model, which project, when* over time.
4. No LLM in the loop — notifications are fixed templates.

---

## 4. Data availability (verified; the storage foundation)

### 4.1 Cursor — ✅ exact monthly per-model tokens via API

- **API** `api2.cursor.sh` DashboardService (already authenticated, Connect RPC):
  - `GetCurrentPeriodUsage` *(used)* — cycle spend in cents (`planUsage`,
    `spendLimitUsage`).
  - **`GetAggregatedUsageEvents`** *(new)* → `aggregations[]`: `modelIntent`,
    `inputTokens`, `outputTokens`, `cacheWriteTokens`, `cacheReadTokens`,
    `totalCents`, `tier` — the same numbers the Cursor dashboard table shows;
    per model, per billing cycle. Server-cached (minutes stale, fine for us).
  - `GetUsageLimitPolicyStatus` *(⚠️ undocumented response — probe)* — slow-pool
    / feature gates / allowed models. Slow pool is Cursor's hidden limiter:
    over-limit users silently drop to weaker models. If the probe succeeds it
    becomes a first-class notification trigger.
- **Local** `~/.cursor/ai-tracking/ai-code-tracking.db` (present): per-suggestion
  rows (`source`: composer/tab/cli, `model`, `createdAt`) → daily suggestion and
  model-frequency stats; `scored_commits` (`aiPercentage`).

### 4.2 Claude Code — ✅ richest, all local

`~/.claude/projects/<cwd-slug>/*.jsonl` assistant records carry:
`usage{input_tokens, cache_creation_input_tokens, cache_read_input_tokens,
output_tokens, output_tokens_details.thinking_tokens}`, `message.model`,
`sessionId`, `timestamp`, `cwd`, `entrypoint` (cli/ide), `permissionMode`.

⇒ per session: tokens by kind, model, project, duration, turns, weekday & hour.
The claude.ai usage page is a strict subset of these files.

⚠️ Files reach tens of MB — read incrementally with per-file byte-offset
watermarks (same pattern as `pi_backend.py`). API
(`api.anthropic.com/api/oauth/usage`, used) is percent buckets only — limits
live there, usage lives in the transcripts; they complement each other.

### 4.3 OpenCode — ✅ asset-grade: exact tokens & $ per session

`~/.local/share/opencode/opencode.db` (249 MB + WAL). `session` table:
`cost`, `tokens_input/output/reasoning/cache_read/cache_write`, `model` JSON
(`{id, providerID}` — e.g. `deepseek-v4-flash` / `opencode-go`), `agent`
(build/plan), `directory`, `time_created/updated/compacting/archived`. `message`
table adds per-message cost/tokens/modelID and `time.{created,completed}`.

⚠️ 250 MB — open **read-only**, query by `time_updated` watermark, never hold
locks. Only the OpenCode **TUI** writes here (Pi sessions don't land here).

### 4.4 Codex — ⚠️ partial on this machine

- Local: `state_5.sqlite.threads` **empty**, `logs_2.sqlite` has no token data,
  no JSONL transcripts — **no local session history available today**. Target
  fields when it appears: `tokens_used`, `model`, `model_provider`, `cwd`,
  `created_at/updated_at`.
- API: `chatgpt.com/backend-api/codex/usage` (already polled; percent windows
  - `allowed`; frequently answers the anti-bot HTML page — handled). Whether
  the payload carries absolute token `used`/`limit` per window: capture from a
  live daemon run and record.

Design stance: **schema-probing, fail-soft** — record whatever exists, mark
`source`, never guess.

### 4.5 Pi — ❌ no token/cost persisted; everything else yes

- Logs contain `model_change`, `agent-summary{durationMs, commands}` — **zero
  token/cost fields** (verified across all sessions). Footer totals are
  in-memory.
- Persisted: backend account + model, cwd, start/end, duration.
  `models-store.json` has exact per-model $/MTok tables.
- We store Pi sessions (model/project/duration) and **optionally** an
  account-residual **estimate**: `account total (from meters) − Σ attributed
  tool sessions` when Pi was the only active consumer on that account. Always
  labelled `estimate`, never guessed when attribution is ambiguous.

---

## 5. The ledger (`usage.db`) — storage first

### 5.1 Schema

```sql
-- One row per tool-session (written when a session ends, or on deep harvest).
CREATE TABLE sessions (
  provider       TEXT NOT NULL,          -- cursor | claude | opencode | codex | pi
  source         TEXT NOT NULL,          -- api | local-transcript | local-db | estimate
  external_id    TEXT NOT NULL,          -- tool's own id (sessionId / ses_… / pid…)
  model          TEXT,                   -- model id as the tool names it
  model_family   TEXT,                   -- downcased, de-versioned: deepseek-v4-flash, gpt-5
  project        TEXT,                   -- basename of cwd; NULL when unknown
  directory      TEXT,
  started_at     INTEGER,                -- epoch s (UTC)
  ended_at       INTEGER,
  duration_s     INTEGER,
  tokens_input   INTEGER DEFAULT 0,
  tokens_output  INTEGER DEFAULT 0,
  tokens_reasoning INTEGER DEFAULT 0,
  tokens_cache_read  INTEGER DEFAULT 0,
  tokens_cache_write INTEGER DEFAULT 0,
  cost_usd       REAL,
  turns          INTEGER,
  meta           TEXT,                   -- json: agent kind, entrypoint, plan, tier…
  folded         INTEGER DEFAULT 0       -- folded into rollups; set by harvesters
);
CREATE INDEX idx_sessions_provider_start ON sessions(provider, started_at);
CREATE INDEX idx_sessions_project ON sessions(project);

-- Cursor's cycle-level per-model rows (do not decompose into sessions).
CREATE TABLE per_model (
  provider  TEXT NOT NULL,
  model     TEXT NOT NULL,
  cycle_key TEXT NOT NULL,               -- billing-cycle end timestamp
  tokens_input, tokens_output,
  tokens_cache_read, tokens_cache_write INTEGER DEFAULT 0,
  cost_usd REAL,
  UNIQUE(provider, model, cycle_key)
);

-- Per-day-per-provider totals — the fastest path to "token usage vs projects
-- across a period of time", and the input to every digest.
CREATE TABLE daily (
  day      TEXT NOT NULL,                -- YYYY-MM-DD (UTC)
  provider TEXT NOT NULL,
  project  TEXT,
  model    TEXT,
  sessions INTEGER DEFAULT 0,
  minutes  INTEGER DEFAULT 0,
  tokens   INTEGER DEFAULT 0,
  cost_usd REAL DEFAULT 0,
  UNIQUE(day, provider, project, model)
);

-- Hourly rollup for time-of-day / weekday facts (local timezone).
CREATE TABLE hourly (
  day  TEXT NOT NULL, hour INTEGER NOT NULL,
  provider TEXT, model TEXT,
  minutes INTEGER DEFAULT 0, tokens INTEGER DEFAULT 0,
  cost_usd REAL DEFAULT 0, session_count INTEGER DEFAULT 0,
  UNIQUE(day, hour, provider, model)
);
```

`daily` and `hourly` are **incremental** — harvesters fold new `sessions` rows
and mark `folded`, so "this month across providers/projects/models" is a few
indexed `SUM`s over `daily`, never a scan of 90 days of events. A `report`
command recomputes any period on demand.

### 5.2 Harvesters (idempotent, fail-soft, cheap, versioned)

| Harvester | Source | Writes |
| --- | --- | --- |
| `harvesters/opencode.py` | `opencode.db` read-only, `time_updated` watermark | `sessions` (exact cost+tokens+model JSON), folds `daily`/`hourly` |
| `harvesters/claude.py` | `~/.claude/projects/*/*.jsonl` incremental tails | `sessions` per `sessionId` (tokens, model, project, duration, turns) |
| `harvesters/cursor_api.py` | `GetAggregatedUsageEvents` (+ `GetCurrentPeriodUsage` cents) | `per_model` per cycle; slow-pool flag to state |
| `harvesters/codex.py` | endpoint raw dump + any local threads found | rows with `source: codex-api` when data exists, else nothing |
| `harvesters/pi.py` | session scanner + `agent-summary` duration + backend resolver | `sessions` (no tokens) + optional labelled residual estimate |
| `harvesters/cursor_local.py` (v2) | `ai-code-tracking.db` incremental rowid | suggestion counts per model/day |

Contracts: re-running never double-counts (byte offsets / `time_updated` /
rowids / cycle keys); a locked DB, mid-write JSONL, or 429 disables *that*
harvester for the cycle and says so once — never the daemon (same tolerance
discipline as `history.Recorder`); readers carry a format version and degrade
gracefully when a vendor moves the schema (Claude JSONL fields, Codex sqlite
migrations, OpenCode schema all move).

### 5.3 Accuracy rules (the "store accurately" bar)

1. **Idempotency** — every write is keyed (`UNIQUE` constraints) and
   watermarked; double harvest == no change.
2. **Source honesty** — `source` per row: exact tool data vs `estimate`.
   Aggregations carry the same label at the provider level.
3. **Cross-checks** — where a second authority exists, verify: Cursor
   `aggregations[]` Σ should ≈ `planUsage` spend × plan; OpenCode `session` Σ
   is authoritative (it is the tool's own billing record); Claude transcripts
   are authoritative locally. Mismatches surface as a check row, not as
   corrected numbers.
4. **Retention** — raw `sessions` pruned past `history_days` (default 90);
   `daily`/`hourly` kept longer (they are tiny) so "this month vs last month"
   always works.
5. **Replay** — a `harvest --full` flag rebuilds `daily`/`hourly` from raw when
   needed, so a schema change never loses history.

---

## 6. The notification engine — the product

### 6.1 Cadence: two clocks

| Clock | When | What it produces | Example |
| --- | --- | --- | --- |
| **Scheduled** | daily (configurable hour) + weekly (e.g. Monday 9:00) + monthly | digest-grade notification built from `daily`/`hourly` | "This month: 41 sessions, 1.8M tokens, top project x, top model y" |
| **Event-driven** | meter crosses threshold / burn ETA crosses `wind_down_hours` / Cursor slow-pool / Claude 5h resets high / Pi estimate flips | actionable, routed immediately | "Claude 5h at 92% → hand over to opencode (deepseek-v4-flash, 3% used)" |

Scheduled messages are generated ahead of time (spread out, cached); event ones
are generated at trigger time with the same guards. A generation timestamp +
`(kind, key)` cache prevents re-generating within the cooldown.

### 6.2 Routing: LLM with the most capacity, rolling/weekly first

Score every provider with a usable meter for *generation* (never the provider
that triggered the message):

```text
score = headroom%                       # primary focus: rolling & weekly windows
        + bonus if another window also healthy   # e.g. opencode rolling+weekly both low
        + monthly headroom as a tiebreak         # cursor/codex monthly usage
        − penalty if generator is the trigger provider (excluded outright)
```

- Claude: 5-hour + weekly windows decide (in that order).
- OpenCode: rolling + weekly decide.
- Cursor/Codex: monthly-only → tiebreak weight only (they are also the weakest
  *generator* endpoints anyway, §7).
- Generator pool for v1: **{claude, opencode}** — both have cheap capable
  models and endpoints we can already authenticate to. Model choice: cheapest
  on that provider (`llm_generator_model` or auto = haiku/flash class),
  `max_tokens` ~200, temperature ~0.4.
- Floor: never generate when the chosen generator's own summary headroom
  < `llm_min_headroom` (default 15) — don't spend capacity to warn about
  missing capacity; fall back to templates.

### 6.3 Generation contract (prompt in → message out)

The prompt is assembled from **state + ledger only, numbers only — no raw
transcripts**:

- Meters for every provider: label, %, reset, burn ETA.
- The trigger (scheduled digest: period + headline figures; event: which
  provider, why, how much runway).
- Ledger facts: top provider, top model, top project, totals for the period,
  an interesting/odd counter from §8.
- Output contract: ≤ 3 sentences; one concrete action if actionable; tone
  (`calm` default); never invent numbers; if `sharable` variant requested, end
  with a one-line tweet (≤ 200 chars) on its own line prefixed `SHARE:`.

Example assembled context:

```jsonc
{
  "kind": "weekly_digest",
  "trigger": { "period": "last 7 days" },
  "rank": [ { "provider": "opencode", "tokens": 1180000, "sessions": 27 },
            { "provider": "claude", "tokens": 340000, "sessions": 11 },
            { "provider": "cursor", "tokens": 0, "sessions": 0 } ],
  "top_model": "deepseek-v4-flash",
  "top_project": "opencode",
  "fun_fact": "peak cache-use day was Thursday (87% of input from cache)"
}
```

### 6.4 Delivery

- Desktop notification (existing `notify.send`, cooldown-respecting).
- Terminal: `cursor-spend-monitor quote` — prints the latest generated message;
  ideal for shell prompts/status lines.
- Panel billboard (§9): the popover occasionally shows the message instead of
  the provider list.
- Everything is **a notification, never an action** — no auto-typing into
  terminals, no approved spend, nothing executed on the user's behalf.

---

## 7. Generator endpoints (feasibility verified)

| Generator | Endpoint | Auth we already hold | Notes |
| --- | --- | --- | --- |
| **Claude** ✅ | `POST api.anthropic.com/v1/messages` (`anthropic-version` + `oauth-2025-04-20`) | Claude Code OAuth token (`~/.claude/.credentials.json`, read-only policy already in the daemon) | counts against the Claude plan — only used when *another* provider is in trouble |
| **OpenCode Zen** ✅ | `POST opencode.ai/zen/v1/chat/completions` (OpenAI-compatible) or `/zen/v1/messages` | `~/.local/share/opencode/auth.json` `opencode-go.key` | pay-as-you-go; deepseek-flash/qwen-flash/haiku-class are the cheap picks |
| **Codex** ❌ v1 | internal `backend-api/codex/...` flow | heavy, version-churning | out |
| **Cursor** ❌ v1 | no clean public inference API | — | out |

Read-only token discipline holds for the generator too: no refresh, no writes
to the credentials files, 30 s timeouts, 429 backoff. We never rotate — that
is the "signed you out of the CLI" bug class.

---

## 8. Notification content catalog — useful / fun / informative / shareable

Every row below is a real aggregation over the ledger (§5). The engine picks a
mix: scheduled digests (informative) + a rotating "fun fact" + event-driven
(actionable) + occasional *shareable* variants for the billboard and terminal.

### 8.1 Informative (why the user should read it)

| Notification | Ledger query | Example body |
| --- | --- | --- |
| Weekly digest | Σ sessions/tokens/cost by provider + top project + top model, trailing 7 days | *"Last week: 38 AI sessions, 1.9M tokens. OpenCode carried 71% (deepseek-v4-flash); Claude 26%. Top project: opencode — 14 sessions, 2h 40m."* |
| Monthly digest | same over calendar month + MoM Δ | *"October: 154 sessions, 8.4M tokens across 11 projects. Up 22% vs September. Most used: OpenCode Go ($4.10); least: Codex ($0.12, 3 sessions)."* |
| Project spotlight | top project by tokens/$ with its split | *"cursor-spend-monitor ate 1.1M tokens this week — 87% Claude opus, 13% deepseek. It is your most expensive project right now."* |
| Session shape reality-check | duration buckets + hour heatmap | *"Only 6 of your 41 sessions this week ran 8–5 on weekdays. 22 were evening bursts under 15m — that is where most cache misses are."* |
| Model split inside provider | GROUP BY provider, model | *"On OpenCode you use deepseek-v4-flash 9× more than deepseek-v4-pro — but v4-pro is 41% of spend."* |

### 8.2 Fun (engagement, streaks, records)

| Notification | Query | Example |
| --- | --- | --- |
| Streak | consecutive days ≥1 session | *"7 days in a row with at least one AI session — your longest streak this year."* |
| Records | max tokens in a day / max session duration / max turns | *"New record: 214K tokens in one day (Tue). Previous best: 178K."* (or: longest run, most expensive session — "$0.42 on deepseek-v4-pro, one session") |
| Cache hero | day with max cache-read share | *"Thursday: 87% of your input tokens came from cache. Your future self says thanks."* |
| Humour hooks | turns counts, repeated models, odd hours | *"You asked the LLM to explain itself 1,240 times this month. Healthy scepticism."* / *"Your Sunday 2am sessions are 3× more token-hungry than Tuesday's."* |

### 8.3 Actionable (the original ask: wind down & hand over)

| Notification | Trigger | Example |
| --- | --- | --- |
| Limit incoming | meter crosses threshold or burn ETA < `wind_down_hours` | *"Claude 5-hour limit at 92% — spent in ~40m at this pace. OpenCode Go is at 3%; your usual there is deepseek-v4-flash. Start the handoff now."* |
| Hard limit | meter ≥ 100 | *"Claude 5h cap reached. OpenCode rolling is at 4% — continue the task there; instrument your handoff notes."* |
| Reset landed hot | Claude 5h resets and immediately > 50% | *"Your 5h window just reset — and you're already at 61%. Pace this one; or route the next task to OpenCode."* |
| Slow pool (probe) | Cursor `GetUsageLimitPolicyStatus` | *"Cursor moved you to the slow pool. That is why responses feel slower — your monthly plan is spent. Cooldown applies; OpenCode weekly is at 2%."* |

### 8.4 Shareable — Twitter-ready (the breakdown you asked for)

These read like a person posting about their own work, not like telemetry. Each
is generated with the `SHARE:` one-liner so it is copy-paste ready, and the
notification body is the tweet:

| Family | Data behind it | Example SHARE: line (≤ 200 chars) |
| --- | --- | --- |
| Stat card | month totals + top model + top project | *"SHARE: This month I ran 154 AI coding sessions, 8.4M tokens, across 11 projects. DeepSeek V4 Flash did most of the heavy lifting. My AI pair programming, in one number: …"* |
| Streak/milestone | session #100, #1000; 30-day streak | *"SHARE: 100th AI-assisted session this month. Still faster than typing it myself."* |
| Efficiency flex | cache-read ratio, cost-per-1M-tokens trend | *"SHARE: 71% of my AI input tokens now come from cache reads. Reuse beats re-read — and it costs ~40× less."* |
| Work-vs-life | weekday-8-5 share vs evening/weekend | *"SHARE: 62% of my AI usage happens after 5pm. The best code of my week ships at 11pm."* |
| Provider opinion (neutral, data-driven) | tokens-per-$ ranking | *"SHARE: My monthly LLM bill across 4 providers: OpenCode $4.10 / Claude $20 / Cursor $20 / Codex $0.12. The cheapest option is doing 71% of the work."* |
| Curiosity | odd-but-true single number | *"SHARE: My longest single AI session was 3h 41m. It outlasted my lunch, my coffee, and my self-control."* |
| Learning signal | top project token share | *"SHARE: One project ate 13% of my tokens this month. You can guess which one I'm rewriting."* |

Publishing is **not** in scope (no auto-post) — but the format is: one `SHARE:`
line, no hashtag slog, real numbers only. A future `quote --tweet` command can
copy it. If the user wants, the scheduled configure can bias the mixer toward
shareable variants daily and actionable/informative otherwise.

### 8.5 Mixer (which kind, how often)

```text
daily:   1 informative digest (short)  + 1 fun fact + 1 SHARE line (rotating)
weekly:  weekly digest + top project spotlight + session-shape reality-check
monthly: monthly digest + MoM delta + records rundown
events:  actionable only, LLM-composed, routed by capacity (§6.2)
```

Config: `notify.schedule { daily_hour, weekly_day, shareable_share }`,
`notify.types { informative, fun, actionable, shareable }` (all on by default),
cooldown per kind.

---

## 9. The quote-mode panel (billboard) — optional, minimal

> **Superseded in detail by `design/BILLBOARD_LANDING_PAGE.md`.** That document
> keeps this intent — a quote shown instead of the provider list, dismissible —
> and settles what this section left open: which message earns the interruption,
> the featured AI shown under the quote, a dismissal that survives a logout, and
> a way to read the latest one on demand. Where the two differ, the newer
> document wins.

The existing GNOME Shell popover keeps its provider list. New behavior — when
state publishes a fresh generated message (`billboard` field), the popover
opens showing the **quote in the billboard style** instead of the list:

- render the message as a quote (icon + text, styled like the design mockup's
  footer);
- two affordances: a **Next** chevron (the same chevrons the window-picker
  already ships) to dismiss early, and a **4-second countdown** after which it
  auto-advances to the normal list — so the list is always one glance or one
  click away;
- if the user opens the popover again within the cooldown, straight to the
  list — billboard only shows for fresh messages once;
- no new panel section, no analytics UI — one `billboard` string in state.

This is the "wait 4 seconds and the panel with the list comes on" behavior,
plus the manual skip. It is a pure presentational change in the extension; the
daemon just publishes `billboard` with the last generated notification
(personal, fun, or shareable depending on the mixer).

---

## 10. Config additions (summary)

```jsonc
{
  "ledger_days": 90,              // raw session retention (daily/hourly kept longer)
  "harvest_deep_seconds": 3600,   // deep harvest cadence for heavy stores
  "wind_down_hours": 2,           // event trigger: burn ETA under this
  "notify": {
    "enabled": true,
    "daily_hour": 18,             // 18:00 local digest
    "weekly_day": "monday",       // weekly digest
    "types": ["informative", "fun", "actionable", "shareable"],
    "shareable_share": 0.25       // share of scheduled slots that are SHARE: style
  },
  "llm_notifications": true,      // master switch for LLM-composed messages
  "llm_generator_provider": "",   // claude | opencode | "" (auto = most headroom)
  "llm_generator_model": "",
  "llm_max_output_tokens": 200,
  "llm_min_headroom": 15,         // generator floor; below it → templates
  "quote_panel": true             // billboard on the popover
}
```

---

## 11. Feasibility verdicts, restated for the new shape

1. **Store tokens per provider per period** — ✅ Cursor (API), Claude
   (transcripts), OpenCode (DB, exact incl. cache splits); ⚠️ Codex
   (probe-dependent); ⚠️ Pi (labelled estimate or omitted).
2. **Store per session / per model / per project / per time-of-day** — ✅ as in
   §2; the ledger schema makes every one of these a GROUP BY.
3. **Route the notification LLM by capacity, rolling/weekly first** — ✅
   Claude and OpenCode expose exactly those windows today; table in §6.2.
4. **Periodically prompt + notify** — ✅ two verified endpoints, one of which
   is always the healthy one; costs a few cents-worth of tokens per message.
5. **Fun / informative / shareable content** — ✅ §8 is all plain aggregations;
   the LLM does the wording, we supply the numbers.
6. **Quote billboard with Next / 4s fallback** — ✅ trivial extension change;
   daemon publishes one string.

---

## 12. Risks and decisions

**Risks** (unchanged in spirit from v1, re-scoped)

1. **Format drift** — every source is an undocumented interface that moves
   (Claude JSONL fields, Codex sqlite migrations, OpenCode schema, Cursor RPC).
   → versioned, fail-soft, schema-probing readers; never let a harvester kill
   the daemon.
2. **Double-counting / shared-account ambiguity** — TUI + Pi on the same
   opencode-go account can't be cleanly split. → `source` label on every row;
   estimates shown as estimates; month digest shows attributed vs unattributed.
3. **Generator quota irony** — the "most capacity" provider is chosen
   precisely to avoid this; the floor + max_tokens + per-key caching cap it;
   templates are the fallback.
4. **Privacy of prompts** — numbers only (no raw transcripts); opt-in switch;
   document that the prompt goes to a provider the user already pays and its
   retention policy.
5. **Notification fatigue** — cooldowns per kind, scheduler honors quiet hours
   (config `notify.silent_hours`), shareable variants are low-frequency.

**Decisions to confirm**

- **Digest cadence & hour**: daily 18:00 + weekly Monday + monthly 1st, all
  configurable — OK? Quiet hours?
- **Month anchor**: calendar month for digests; per-provider billing cycle only
  inside per-provider breakdowns (recommended).
- **Pi estimates**: include the labelled residual estimate (recommended) or
  omit Pi token figures entirely?
- **Twitter**: no auto-posting (recommended); deliver the `SHARE:` line to the
  clipboard via `quote --tweet` so the user posts manually. Agree?
- **Billboard placement**: popover open-time only (recommended) vs also a
  notification when a quote is scheduled.
- **Codex probe**: spend one v1 task capturing the raw usage payload from a
  live daemon run before deciding Codex's notification weight.

---

## 13. Suggested implementation order (after your review)

1. **Ledger + harvesters that matter first**: `usage.db` schema, `harvest`,
   `report` commands, tests. Harvesters: opencode → claude → cursor_api.
   (Storage accuracy before any notification exists.)
2. **Cross-check + `harvest --full` replay** (the "store accurately" bar, §5.3)
   and a `report --month` CLI that answers the historical questions.
3. **Notification engine**: scheduler (daily/weekly/monthly), mixer §8.5,
   template fallbacks (ship templates first — the LLM can be added later
   without changing the triggers).
4. **LLM routing + generation**: capacity routing §6.2, prompt contract §6.3,
   Claude-first generator, then OpenCode; caching + floors + fallbacks.
5. **Delivery surfaces**: `quote` CLI, desktop notifications, then the panel
   billboard (§9).
6. **Fun/shareable mixer tuning** with real ledger data; adjust `shareable_share`.

Each step ships and is testable against the existing mock daemon
(`gnome-shell-extension/devtest/mock_daemon.py`).

---

## Appendix A — evidence checked on this machine

- `opencode.db`: `session` columns verified incl. `cost`, `tokens_input/output/
  reasoning/cache_read/cache_write`, `model` JSON, `directory`, timestamps;
  2 268 rows carry cost/token data; sample `deepseek-v4-flash` @ `opencode-go`.
- Claude transcripts: 1 274 assistant records in one 19 MB project file, all
  with `usage{input, cache_creation, cache_read, output, thinking}` + `model`
  (`claude-opus-5`) + `sessionId` + `cwd` + `timestamp`.
- Codex: `state_5.sqlite.threads` empty; no JSONL transcripts; usage endpoint
  returned the anti-bot HTML page to a bare curl (already handled by the
  daemon).
- Pi: logs contain `model_change` and `agent-summary{durationMs, commands}`,
  zero token/cost fields; `models-store.json` has per-model $/MTok tables.
- Cursor: `ai-code-tracking.db` present; `state.vscdb` has `cursorDiskKV`/
  `ItemTable`; dashboards are built on `GetAggregatedUsageEvents` per
  OpenUsage/OpenTokenUsage documentation of the live API.

## Appendix B — dashboard ↔ data source map

| Dashboard page | Shows | Our equivalent |
| --- | --- | --- |
| cursor.com/dashboard/spending | cycle spend, per-model tokens | `GetCurrentPeriodUsage` + `GetAggregatedUsageEvents` (same numbers via API) |
| claude.ai/settings/usage | messages + tokens per model, week/month | local transcripts (superset: per-session, per-message, exact cache splits) |
| opencode.ai console | balance, limits, sessions | `zen/go/v1/usage` (limits) + `opencode.db` (sessions, exact tokens/$, models) |
| chatgpt.com Codex | window percents | `backend-api/codex/usage` (already polled); token-detail ⚠️ probe |
