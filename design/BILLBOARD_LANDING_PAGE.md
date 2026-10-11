# The landing page — a quote at the top of the popover

**Status:** implemented — daemon `choose_billboard` / `Acknowledge`, extension
landing compare on `billboard.id`, covered by `tests/test_billboard.py`.
**Supersedes:** `USAGE_ANALYTICS_AND_GUIDANCE.md` §9 ("quote-mode panel"), which
described a simpler behaviour — a quote swapped in place of the list, dismissed
by a chevron or a 4-second timer. It had no notion of which message deserved the
interruption, no featured provider, and no memory of having been dismissed, so
it would have shown something on every open.

---

## 1. What it is

Clicking the status dot normally opens the provider list. Sometimes it should
open something else first: **one notification, blown up as a quote**, with the
AI it is about underneath (icon and name), and a **Continue** to get to the list
you actually came for.

Three kinds of message earn that interruption:

- **A recommendation to move** — "Claude 5h is at 93%; OpenCode has room."
- **A finding worth knowing** — "OpenCode did 71% of your work for $4.10."
- **Something genuinely interesting** — a streak, a cache record, a shareable
  line worth posting.

The page is **not** shown on every open. The daemon decides whether there is
something worth showing; the extension only decides when the user is looking.

---

## 2. Why the daemon decides, not the extension

Every other policy in this system lives daemon-side and the extension renders
state. This one should too:

- the daemon already holds the message history and is the only place that can
  remember a dismissal across logins and reloads;
- priority, freshness and acknowledgement are rules with edge cases, and Python
  tests for them are cheap while GNOME Shell tests are not;
- it keeps the extension's rule to a single comparison, which is the most
  reliable thing to get right in a codebase that cannot be reloaded casually.

The extension's entire routing rule becomes:

```js
const billboard = this._state?.billboard;
if (billboard && billboard.id !== this._landingShownId) showLandingPage(billboard);
```

---

## 3. State contract

Two additive fields on the payload the daemon already publishes:

```jsonc
{
  // The ONE message worth interrupting for, or null. The daemon picks it.
  "billboard": {
    "id": 42,
    "kind": "actionable",              // informative | fun | actionable | shareable
    "priority": 3,                     // actionable 3, informative 2, shareable 1, fun 0
    "text": "Claude Code 5-hour limit is at 93%, spent in about 40m. OpenCode has room — start the handoff there.",
    "share": "",                       // the SHARE: line, only for shareable
    "featured": {                      // the AI this message is about
      "providerId": "opencode",        // drives the badge icon
      "name": "OpenCode",
      "role": "suggested"              // suggested | leading | value
    },
    "createdAt": 1791288693,
    "expiresAt": 1791331893,           // freshness deadline; null = never expires
    "reason": "5-hour limit at 93%"    // short why — accessibility and devtest
  },

  // The newest stored message regardless of acknowledgement or freshness.
  // This is what the "Latest" button shows.
  "latest_message": { "...same shape..." }
}
```

Both are **additive**: `state.SCHEMA_VERSION` stays `1`, and an extension from
before this change ignores them and behaves exactly as it does today.

`billboard` is `null` far more often than not. That is the point.

### What it needs from the rest of the system

- `notify_engine.Message` already carries `provider`; **digests must start
  setting it** (currently only actionable messages do), so `featured` can name
  the leading provider for an informative or shareable message.
- `featured.role` is decided by kind: `suggested` for actionable (the provider
  to move *to*), `leading` for informative/shareable (the one doing the work).

---

## 4. How a message is chosen

`billboard_for(con, now)` picks from messages that are **unacknowledged** and
**unexpired**, ordered by `priority` descending then `created_at` descending.
One message, never a queue.

| kind | priority | freshness window | lands |
| --- | --- | --- | --- |
| `actionable` | 3 | 6 hours | on the next open, and again if a *newer* actionable arrives |
| `informative` | 2 | 24 hours | once |
| `shareable` | 1 | 24 hours | once |
| `fun` | 0 | 12 hours | only when nothing of a higher priority is pending |

Rules, in the order they are applied:

1. **Acknowledged messages never land again.** Persisted, so it survives a
   logout and an extension reload.
2. **Expired messages never land.** They still exist — `latest_message` and
   `quote` can still show them — they just stop interrupting.
3. **Priority first, newest second.** A new meter warning outranks yesterday's
   fun fact; two fun facts resolve to the newer.
4. **`fun` is the floor.** A curiosity never interrupts while anything
   actionable or informative is pending.
5. **Silent hours do not suppress the landing page.** They suppress *desktop
   notifications*, which arrive uninvited. The landing page only appears when
   the user opens the menu, so it is never an interruption in the same sense.
   *(Decision 4.)*

`latest_message` is deliberately not filtered: "show me the most recent thing"
should work even months later, from `quote` or from the panel.

---

## 4b. How the featured AI is chosen

The featured AI is **read out of the ledger**, never looked up from a list. Two
questions decide it, in order:

1. **Which provider carried the period?** The one with the most tokens. That is
   the default answer, with the role `leading`.
2. **Did a cheaper one do enough work to be the better story?** If a provider
   with a real share of the period (at least 20% of its tokens) moved more
   tokens per dollar than the leader, it becomes the answer with the role
   `value` — "most use for the least spend" is the thing actually worth telling
   someone. A provider with no recorded cost cannot win this way: its
   tokens-per-dollar is unknown, not infinite.

For an **actionable** message the question is different, because the point is
where to go next: the featured AI is the provider with the most live headroom,
role `suggested`. The provider in trouble is kept in `meta.trigger`, so the
message can name both, and the advice is about capacity rather than history.

Display names come from the provider classes themselves
(`PROVIDERS[id].display_name`), so there is no second copy of "Claude Code" to
drift out of date.

### The LLM has to name it too

When the wording comes from a model (Phase 5), the prompt must ask for the
featured provider as well as the sentence. Otherwise the panel renders a badge
for whoever the ledger ranked first while the prose talks about someone else.
The generation contract therefore gains a second line:

```text
FEATURED: <provider id>
```

with the ranked provider facts in the prompt, so the model chooses from real
numbers instead of guessing. The daemon validates the returned id against the
providers it knows, and an unknown or missing one falls back to
`notify_engine.featured_provider` — so a bad answer degrades to the derived
choice rather than losing the badge. Templates already behave this way, which is
what keeps the LLM an upgrade rather than a dependency.

## 5. Acknowledgement

A dismissal has to outlive the session, so the daemon stores it.

**New D-Bus method** on the existing interface:

```xml
<method name="Acknowledge">
  <arg type="u" direction="in" name="id"/>
</method>
```

**Storage.** `messages` gains `seen_at INTEGER`.

**Migration.** `CREATE TABLE IF NOT EXISTS` cannot add a column to a table that
already exists, so `ledger.connect` gains a guarded, idempotent step: read
`PRAGMA table_info(messages)`; if `seen_at` is missing, `ALTER TABLE messages
ADD COLUMN seen_at INTEGER`. Both directions stay safe — an older daemon simply
never reads the column, and a newer daemon upgrades an older store in place.
`FORMAT_VERSION` stays `1`.

Note this is the first *additive* schema change since the ledger shipped, and it
is exactly the case the format-version guard was written for: it must not
require a `harvest --full` or a fresh database.

**When the extension calls it.** On **Continue** from a fresh landing page —
that is the user saying "seen it, take me to the list". Reading it again via
**Latest** acknowledges it too if it was not already, because the user has now
demonstrably read it.

---

## 6. Extension behaviour

### A new screen

`_screen` gains `"landing"`, dispatched from `_render` beside `list`, `detail`,
`sessions`, `guide` and `about`. The existing `_navigate(screen)` and the entry
animation are reused unchanged.

### When it opens

The existing `open-state-changed` handler currently forces `_navigate("list")`
whenever the screen is not the list. That becomes:

```js
if (open) {
    this._ext.refresh();
    const billboard = this._state?.billboard;
    if (billboard && billboard.id !== this._landingShownId) {
        // Record it as shown *now*, not on Continue: closing without pressing
        // Continue must not mean it nags on the next open.
        this._landingShownId = billboard.id;
        this._landingMode = "fresh";
        this._navigate("landing");
    } else if (this._screen !== "list") {
        this._navigate("list");
    } else {
        this._beginEntry();
    }
}
```

`_landingShownId` is per-session, in memory. That is deliberate: it means the
page appears at most once per message per login even if the user never
acknowledges, while a genuinely new message still gets through.

### The page

```text
┌────────────────────────────────────────────┐
│  AI usage                Latest  Guide  About│   Latest appears only when a message exists
│                                             │
│   ❝                                         │
│   Claude Code 5-hour limit is at 93%,       │   the quote, large and wrapped
│   spent in about 40m. OpenCode has room —   │
│   start the handoff there.                  │
│                                             │
│   ┌──┐  OpenCode                            │   the featured AI: badge + name
│   │◧ │  has room                             │   + what its role means here
│   └──┘                                      │
│                                             │
│              [   Continue   ]               │   primary → the list
└────────────────────────────────────────────┘
```

- **Quote** — `wrappedLabel(billboard.text, "tokens-go-brrr-landing-quote")`. There is
  no quote styling in the extension today; it is new CSS, not a reuse.
- **Featured AI** — `icons.badge(featured.providerId)` (the same badge stack the
  session chips use) plus `featured.name`, and one line of role copy:
  `suggested` → "has room", `leading` → "doing the heavy lifting",
  `featured` → "worth a look".
- **Continue** — a focusable `St.Button`, the primary action, `_navigate("list")`
  plus `Acknowledge`. This is the "option to continue so we go back to our
  current view".
- **Copy** — only when `share` is set: an `St.Clipboard` copy of the `SHARE:`
  line. The in-panel equivalent of `quote --tweet`.
- **Skip** — the footer chevron already used by the window picker, kept as a
  second, quieter way back to the list.

### Coming back to it later

The header gains a **Latest** button (beside Guide and About) that appears only
when `latest_message` exists. It opens the same screen in `"latest"` mode:

- no `Acknowledge` unless unacked (see §5);
- if the message is past its freshness window it is labelled "Earlier" so it is
  clear this is not a fresh interruption;
- this is the "option for them to see the most current one" without leaving the
  menu open all day.

### A hint that something is waiting

When `billboard` is non-null, the status dot gains a `has-update` class — a
subtle ring or accent — so the interruption is discoverable rather than
surprising. *(Decision 6.)*

---

## 7. Styles

New classes in `stylesheet.css`, all namespaced `tokens-go-brrr-landing-*`:
`tokens-go-brrr-landing`, `-quote`, `-share`, `-featured`, `-name`, `-role`,
`-continue`, `-skip`, plus `tokens-go-brrr-dot.has-update`.

Reused as-is: `tokens-go-brrr-badge`, `tokens-go-brrr-badge-icon`, `tokens-go-brrr-chevron`,
`tokens-go-brrr-header-btn`, `tokens-go-brrr-screen`, and the existing entry animation
(`ROW_EASE`) so the quote settles the same way a row does.

The quote should follow the type scale already in `stylesheet.css` — larger
than `tokens-go-brrr-name`, wrapped to at most three or four lines, and never
truncated: a message that has to be ellipsised is too long, and the generator's
own limit is three sentences.

---

## 8. Edge cases

| Case | Behaviour |
| --- | --- |
| No messages at all | no billboard, no Latest button, dot unchanged — exactly today's panel |
| Message acked, then a newer one generated | the new one lands; the acked one never does |
| Two actionable messages pending | the newer lands; the older stays reachable via Latest |
| Billboard arrives while the popover is open | it waits — routing happens on open, never by replacing what the user is reading |
| Message longer than the panel | wraps; the generator's ≤ 3 sentence contract is the real guard |
| Provider for `featured` is unknown to `BADGE_FILES` | falls back to the cursor badge, as the existing badge code already does |
| Daemon restarts mid-session | `_landingShownId` survives (extension memory); acked state survives (database) |
| Older extension, newer daemon | ignores both new fields; panel behaves as it does today |

---

## 9. Config

```jsonc
{
  "billboard_enabled": true,
  "billboard_auto_advance_seconds": 0,   // 0 = wait for Continue
  "billboard_freshness_hours": 24        // ceiling; per-kind windows are in §4
}
```

*(Decision 3: `0` means Continue is the only way out, which respects the user's
"then the option to continue". An 8-second safety net is the alternative.)*

---

## 10. What changes, by file

| File | Change |
| --- | --- |
| `ledger.py` | `messages.seen_at`; guarded `ALTER TABLE` migration; `mark_message_seen(id)`; `latest_message` unchanged; `pending_messages()` for routing |
| `notify_engine.py` | `PRIORITY` map and per-kind freshness; `expires_at` on `Message`; digests set `provider` and `role` |
| `daemon.py` | publish `billboard` and `latest_message`; `acknowledge(id)` handler; `billboard_enabled` respected |
| `dbus_service.py` | `Acknowledge` in the interface XML, in `_method_call`, and a new constructor callback |
| `extension.js` | `landing` screen; open-flow routing; `_landingShownId`; Continue / Skip / Copy; Latest header button; dot marker |
| `stylesheet.css` | the `tokens-go-brrr-landing-*` classes and `has-update` |
| `config.py` | the three settings above |
| `devtest/mock_daemon.py` | a `billboard` and `latest_message`, plus a way to cycle to the next one |
| `devtest/stress_daemon.py` | a maximum-length quote, to prove wrapping |
| `tests/test_billboard.py` | routing, expiry, priority, ack, migration |

### Tests worth writing first

The routing rules are the part with edge cases, and they are pure Python:

- priority ordering, and newest-wins within a priority;
- `fun` never lands while an `informative` is pending;
- an acked message never lands, even when it is the highest priority;
- an expired message never lands but still appears as `latest_message`;
- `billboard` is `null` on an empty ledger and after everything is acked;
- the migration adds `seen_at` to a pre-existing `messages` table, and running
  it twice is a no-op.

The extension side is verified against `devtest/mock_daemon.py`: open → quote →
Continue → list; reopen → list; Latest → quote; a second mock message → lands
again.

---

## 11. Decisions to audit

| # | Decision | Proposal |
| --- | --- | --- |
| 1 | Where dismissal is remembered | daemon/database, so it survives logout and reload |
| 2 | Once per session even without pressing Continue | yes — closing must not mean it nags next open; it re-lands once at next login if still fresh |
| 3 | Auto-advance | **off** by default; Continue is the only way out. An 8s safety net is the alternative |
| 4 | Silent hours | do **not** suppress the landing page (user-initiated); they still suppress desktop notifications |
| 5 | Featured AI semantics | **Resolved:** derived from the ledger (§4b) — `leading` = most tokens, `value` = most tokens per dollar with a real share, `suggested` = most live headroom for an actionable message |
| 6 | Unread marker on the dot | yes, subtle — discoverability |
| 7 | Latest button placement | header, beside Guide and About |
| 8 | In-panel Copy for `SHARE:` lines | yes, via `St.Clipboard`, alongside `quote --tweet` |
| 9 | Older unacked actionable when a newer lands | newer wins; the older stays available via Latest |

---

## 12. What this is not

- Not a notification centre. There is no list of past messages in the panel, no
  unread count, no inbox. Latest shows **one** message — the newest.
- Not a second notification channel. The desktop notification and the landing
  page are two renderings of the same stored message, not two messages.
- Not LLM-dependent. Every message on the landing page works from the templates
  that already exist; the LLM only changes the wording inside them.
