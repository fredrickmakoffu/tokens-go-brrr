# Handover — usage ledger, notifications, landing page

**Historical.** Snapshot from the 0.5.0 ledger ship. Prefer the tree, `AGENTS.md`,
and `.cursor/rules/` for current behaviour. CI runs on PRs (`make test` /
`make lint`); billboard landing is implemented.

---

## 1. What shipped

| piece | file | the contract it keeps |
| --- | --- | --- |
| Ledger | `tokens_go_brrr/ledger.py` | `usage.db`; keyed upserts, so writing the same session twice changes nothing; `daily`/`hourly` recomputed from sessions rather than incremented |
| Harvesters | `harvesters/` (five) | Read each tool's own store, fail-soft: a reader that breaks must not stop the daemon |
| Notification engine | `notify_engine.py` | Templates first. Digests, fun facts, share lines, events, cooldowns, quiet hours |
| LLM composer | `llm_composer.py` | Rewords a template when a provider has headroom; **every** failure returns the template |
| Landing page | `extension.js` + `stylesheet.css` | A message worth reading opens the popover; acknowledgement is durable in `messages.seen_at` |

Two invariants worth protecting, because everything else assumes them:

- **No number is invented.** Unknown values are absent, not zero. Estimates are
  labelled `source="estimate"` and can be excluded from a report.
- **Storage never stops the panel.** Every ledger call is fail-soft and says so once.

## 2. Running it

```bash
python3 -m unittest discover -s tests -q          # 412 tests
./gnome-shell-extension/devtest/layout-smoke.sh   # 6 screens + landing shape, headless
./gnome-shell-extension/devtest/live-reload.sh    # stage a revision, then Alt+F2 → lg → paste
./gnome-shell-extension/devtest/live-reload-reset.sh   # back to the canonical extension
```

```bash
tokens-go-brrr harvest                  # second run must say "no change" for every reader
tokens-go-brrr report --checks          # what the numbers were, not what we assumed
tokens-go-brrr quote                    # the newest message
tokens-go-brrr quote --generate --slot daily|weekly|monthly
```

- **Install:** `./install.sh` — its first step wants `sudo` for `dnf`. To skip that
  (the packages are already there), `pip3 install --user --force-reinstall --no-deps .`
  then `systemctl --user restart tokens-go-brrr`.
- **Ledger:** `~/.local/share/tokens-go-brrr/usage.db`. It is **WAL**, so the
  `.db` mtime lies — read `harvest_state.updated_at` or the `-wal` file to see freshness.
- **Live state:** `/run/user/$UID/tokens-go-brrr/state.json` (`billboard`,
  `latestMessage`, `tools[].metrics`).
- **Logs:** `journalctl --user -u tokens-go-brrr`. A successful harvest logs
  nothing; only failures print.

## 3. What is left

### 3.1 The desktop checklist — 46 unticked boxes

`design/UI_TEST_GUIDE.md`. By design only a person at a live desktop can close them.
Sections A1–A9 are the panel by hand; B1–B5 are the clocks, driven by commands.

Already covered elsewhere, so do not redo them by eye: **B1, B2, B3** (the three
periodic paths) and the landing page's *shape* — two quote marks, the mark-text-mark
row, a centred non-expanding Continue, and no **Latest** on the landing page are all
asserted by `layout-smoke.sh`, which fails if any of them regress.

What is genuinely untouched: quiet hours actually silencing at 22:00, cooldown spacing
between two messages, the desktop notification visibly arriving, and the A8/A9 mock
and stress daemons.

### 3.2 The soak — due around 2026-10-15

The daemon has harvested on its own schedule since 2026-10-08. Review with:

```bash
tokens-go-brrr report --checks          # no FAIL rows; cost_unit should read ok
tokens-go-brrr report --week --by provider
```

Then tune these, which were reasoned rather than observed:

| knob | where | now |
| --- | --- | --- |
| `VALUE_SHARE_FLOOR` | `notify_engine.py` | `0.20` — share needed to call a provider the value pick |
| `notify_shareable_share` | config | `0.25` — share needed for a shareable line |
| `notify_daily_hour` | config | `18` |
| `notify_silent_hours` | config | `[22, 7]` |

Ask of the week: did a digest arrive at 18:00 every day, did any share line appear
when you would actually have posted one, and did anything interrupt during quiet hours.

### 3.3 Cursor's plan fields — the one open question

`dashboard_usage.py` sets `COST_UNIT_CONFIRMED = False`, so the `cost_unit` check
reports "unit assumed cents". The per-model rows and the response total now agree
exactly (1619.82¢ against 1619.82¢ — they did not until `1676815`), so **cents is
settled for the aggregation**. What does not reconcile is the *plan*:

```text
planUsage.limit = 2000, totalPercentUsed = 3   ->  implies ~60¢
totalCostCents of the same cycle               ->  1619.82¢
```

Work out what scale those two fields use, or stop reading them, then either set the
flag or delete the assumption. Until then the check keeps saying it is assuming.

### 3.4 There is no CI

Nothing ran on PR #10 (`gh pr checks` reports none) and nothing runs on `main`. Every
green result today came from someone running it by hand. `wire-ci` in the bigpowers
skills is the intended tool if you want the suite and `layout-smoke.sh` gating merges.

## 4. Limits that are deliberate, not bugs

- **Codex is probe-only** — it persists no usage history to read. `harvest` reporting
  nothing for it is correct.
- **Pi token counts are estimates** — its meters are percentages, and no provider
  publishes limits in tokens. Labelled as such; never counted as measured.
- **Cursor cost is per billing cycle**, attributed to the cycle end date. A monthly
  report therefore includes the cycle that closed inside the month, not calendar days.
  Nothing reads it yet except `report --checks`.
- **`llm_notifications` is `False`** in the current config, so wording is templates.
  Turning it on routes to whichever provider has headroom, excluding the one that
  triggered the message.
- **`metadata.json`'s integer `version` stays `1`.** Bumping it makes GNOME refuse to
  hot-reload the extension.

## 5. Traps worth inheriting

1. **A `sqlite3.Connection` belongs to the thread that created it.** The daemon's
   harvest ran zero times for a week because workers borrowed the main loop's
   connection; use `LedgerRecorder.worker()`.
2. **Looking Glass `Eval` scope is small:** `GLib` and `Main` are there, `Clutter` is
   not, and `await`/`return` are invalid. The `lg` console is more permissive than
   `Eval` over D-Bus.
3. **Never `sudo systemctl --user`** — root's user manager has no such unit.
4. **`report --checks` records what the numbers were**, not a verdict. A `FAIL` row
   means a relationship broke; read the detail string before believing a diagnosis.
   The 30× "unit mismatch" was two billing cycles added together.
5. **The formatter is now told to leave CSS and shell alone** (`.pi-lens.json`), after
   it rewrote `stylesheet.css` to a one-space indent and reflowed `layout-smoke.sh`
   repeatedly, mid-edit. Python is still formatted and linted.
6. Four local branches are already merged into `main` and can be deleted:
   `feature/{cursor-spend-tray-monitor,gunmetal,instance-awareness,slate-playful}`
   (the first has a deleted upstream).

## 6. Where things are

| | |
| --- | --- |
| Design | `design/USAGE_ANALYTICS_AND_GUIDANCE.md`, `design/BILLBOARD_LANDING_PAGE.md` |
| Plan | `design/IMPLEMENTATION_PLAN_USAGE_LEDGER.md` — Phases 1–7 done, 8 in progress |
| Testing | `design/UI_TEST_GUIDE.md`, `design/QA_CHECKLIST.md` |
| Fixes worth reading | `4b4979c` worker connections · `7b87f18` digest slot · `d848e86` message identity · `1676815` Cursor cross-cycle check |
