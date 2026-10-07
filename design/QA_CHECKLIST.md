# QA checklist — usage ledger, harvesters and notifications

What to verify by hand, what the automated suite already covers, and what is
expected to look broken because it is not built yet.

> **Testing the panel?** Use `design/UI_TEST_GUIDE.md` instead. This file is
> about the ledger and the command line; that one walks the landing page by
> hand and includes the commands that make the periodic paths fire on demand.

Run everything from the repo root.

---

## 0. Get the new code running

The daemon installs as a *copy*, so editing the working tree changes nothing
until it is reinstalled:

```bash
./install.sh
systemctl --user restart cursor-spend-monitor.service   # NEVER with sudo
```

`systemctl --user` acts on your own user manager; `sudo` makes the caller root
and looks in root's manager, where the unit does not exist.

The extension **does** need a reload for the landing page: `extension.js` and
`stylesheet.css` both changed. GNOME Shell reads an extension only at login, so
reload the running one with `gnome-shell-extension/devtest/live-reload.sh` —
`design/UI_TEST_GUIDE.md` §0 has the paste step.

**Evidence the new code is live:** `~/.local/share/cursor-spend-monitor/usage.db`
appears within about a minute of the restart.

---

## A. Automated suite

```bash
python3 -m unittest discover -s tests -q
```

Expect **396 tests, OK**. What it pins, by module:

| Area | Tests | The property that matters |
| --- | --- | --- |
| `test_ledger.py` | 64 | keyed upserts; a re-harvest writes nothing; fold recomputes rather than accumulates; a corrupt/too-new store is refused, not corrupted |
| `test_harvesters.py` | 21 | OpenCode's numbers land exactly; a locked store is skipped and the watermark does not advance |
| `test_claude_transcripts.py` | 16 | one response written 3× counts once; subagent files land on the parent session; a partial trailing line waits |
| `test_dashboard_usage.py` | 18 | string token counts parse; the cost-unit cross-check is recorded; a first run asks for the previous cycle |
| `test_codex_state.py` | 8 | no token column → no rows, no failure, and the schema is recorded |
| `test_pi_sessions.py` | 8 | no token figure is invented; a vanished session keeps its last-seen end |
| `test_notifications.py` | 28 | an empty ledger produces no digest; an estimate is labelled; borrowed rows never counted twice; cooldowns hold and release |
| `test_billboard.py` | 28 | priority order and per-kind freshness; an acknowledged message never lands again; the `seen_at` migration upgrades an old store and is a no-op the second time |
| `test_llm_composer.py` | 45 | the writer is chosen by headroom with the trigger excluded; the prompt carries the numbers and asks for `FEATURED`; a refusal or an unknown `FEATURED` id keeps the template; credentials are never written to |
| `test_config.py` | 6 | a corrupt config falls back instead of killing the daemon |
| `test_state.py` | +2 | **the idle callbacks fire once** — the regression that pegged a CPU core |

The last row is the one worth keeping an eye on: it exists because
`GLib.idle_add` re-schedules a callback returning `True`.

---

## B. Ledger pipeline (manual)

```bash
cursor-spend-monitor harvest
cursor-spend-monitor harvest      # second run
```

Expected first run, on this machine:

```text
opencode:     66 sessions, 15 day(s) folded
claude_jsonl: 76 sessions, 22 day(s) folded
cursor_api:   N model rows
codex_state:  no token column in the local thread store
pi_sessions:  N sessions
```

The **second run must report `no change` for every reader.** That single line is
the whole accuracy story: it means writes are keyed and re-running is free.

```bash
cursor-spend-monitor report
cursor-spend-monitor report --week --by model
cursor-spend-monitor report --checks
```

Spot-check the totals against the Cursor and Claude dashboards in a browser.
Roughly **144 sessions / 2B tokens** is expected here (Claude dominates because
cache reads are counted).

**Cross-check:** `report --checks` should show a `cost_unit` row for Cursor. It
is allowed to FAIL — the unit of `totalCents` is unverified and the reader
records the disagreement instead of guessing.

---

## C. Notifications (manual)

```bash
cursor-spend-monitor quote --generate --slot monthly
cursor-spend-monitor quote
cursor-spend-monitor quote --generate --slot daily
cursor-spend-monitor quote --tweet --no-copy
cursor-spend-monitor quote --json
```

- `--generate --slot monthly` should produce a sentence with **your** numbers and
  a month-over-month comparison.
- `--slot daily` should produce a digest or a fun fact (cache share, streak, or
  longest session).
- `--tweet` must print a single `SHARE:` line, ≤ 200 characters. Without
  `--no-copy` it also copies; it never posts anywhere.
- `quote` with no arguments prints the newest stored message, and exits 1 with a
  helpful line if nothing has been generated yet.

Then let the daemon run and confirm delivery:

- A digest arrives at `notify_daily_hour` (default 18:00 local).
- A desktop notification arrives when a meter crosses 90%, or when its burn ETA
  drops under `wind_down_hours` (default 2) — with the name of a provider that
  still has room.
- **Nothing** arrives between `notify_silent_hours` (default 22:00–07:00).

Verify the daemon published a quote for the panel:

```bash
python3 -c "import json,os;d=json.load(open('/run/user/%d/cursor-spend-monitor/state.json'%os.getuid()));print(d.get('billboard'))"
```

---

## D. Daemon resource behaviour (manual — do not skip)

This is the check that caught a 6-hour CPU burn.

```bash
systemctl --user status cursor-spend-monitor.service --no-pager | grep -E "CPU|Memory"
```

Run it, wait a minute, run it again. **`CPU:` must creep, not race.** The broken
build added ~1 CPU-second per wall second (6h24m of CPU in 6h30m of uptime, and
97.6% instantaneous). A healthy daemon sits near 0% while idle.

Also confirm it survives a hostile store:

```bash
# with the OpenCode TUI running
cursor-spend-monitor harvest        # expect "skipped", not a traceback
journalctl --user -u cursor-spend-monitor.service -n 50 --no-pager
```

No repeated errors, and the daemon must still be `active`.

---

## E. Install hygiene (manual)

A repeat install must not accumulate copies.

```bash
ls ~/.local/share/gnome-shell/extensions/ | grep ai-usage
gnome-extensions list | grep ai-usage
gsettings get org.gnome.shell enabled-extensions
```

- On disk: **exactly one** `ai-usage@fredrickmakoffu.github.io`, and no
  `ai-usage-rN@` leftovers.
- Enabled: exactly one entry for this extension.
- `gnome-extensions list` may still show stale revisions until you log out —
  the Shell only scans at startup. That is cosmetic.

Then prove the fix: run `./install.sh` twice and confirm the counts do not grow.

Note: a `live-reload.sh` run legitimately leaves **two** directories (the
canonical plus the one active revision). That is how the reload gets the Shell
to re-import a changed file, not a duplicate install. `live-reload-reset.sh` or
another `./install.sh` collapses it back to one.

---

## F. Expected — do not file these

- **Codex contributes no rows.** Its local store has no token column; the reader
  records that as a cross-check.
- **Pi contributes sessions with 0 tokens.** Pi persists no token or cost data,
  and the design's residual estimate proved underivable: the meters are
  percentages of a limit, and no provider publishes that limit in tokens.
- **Cursor's `cost_unit` check FAILs**, and the current cycle may be empty.
- **No LLM wording.** `llm_notifications` exists in config but no generator is
  wired, so all wording is the template.
- **The popover shows no quote.** The daemon publishes `billboard`; the
  extension does not render it yet.
- Pre-existing: `providers/{claude,opencode,cursor,pi}.py` (mutable class
  attribute) and `instances.py` (`except: pass`) still report lint blockers.
  Untouched by this work; a separate hygiene pass.

---

## G. Real bugs — please capture

1. A second `harvest` reports sessions again (idempotency broken).
2. `usage.db` never appears after a restart.
3. The daemon pegs a CPU core, or exits on a locked/unreadable store.
4. `report` disagrees badly with the vendors' own dashboards.
5. A message contains a number that `report` does not show.
6. A period containing an `estimate` row does not say so — or claims one when
   there is none.
7. A notification arrives during silent hours, or the same one repeats inside
   its cooldown.
8. `./install.sh` run twice produces more than one extension directory, or
   leaves two enabled.

For any of these, capture:

```bash
cursor-spend-monitor report --checks
journalctl --user -u cursor-spend-monitor.service -n 200 --no-pager
python3 -c "import json,os;print(json.load(open('/run/user/%d/cursor-spend-monitor/state.json'%os.getuid()))['version'])"
```
