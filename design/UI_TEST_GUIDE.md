# What to test — the landing page, the notifications, and the ledger

Most of this is done by clicking. The parts that would otherwise need you to wait
until 18:00, or until a meter really does hit 90%, are reached with commands that
create the same conditions on demand.

Tick as you go. Anything that behaves differently from the **Expect** line is
worth capturing — §C says what would be a real bug and what is expected.

---

## 0. Set up (once)

The extension changed, and GNOME Shell only reads an extension at login. So this
is the one step where "just restart the daemon" is not enough.

```bash
cd ~/Documents/projects/cursor-folder/cursor-spend-monitor
./install.sh                    # daemon + extension copy; sudo only for dnf inside
systemctl --user restart cursor-spend-monitor.service
```

Then reload the panel **without logging out**:

```bash
./gnome-shell-extension/devtest/live-reload.sh
```

It prints one line. Press **Alt+F2**, type `lg`, Enter, paste the line, Enter,
then Esc. The indicator is replaced in place.

**Check first:** `cursor-spend-monitor --version` says **0.5.0**. If it says
0.4.0, `install.sh` did not pick up the working tree, and nothing below applies.

**To undo later:** `./gnome-shell-extension/devtest/live-reload-reset.sh`, then
log out at your convenience.

---

## A. By hand, on the panel

### A1. The panel you already know still works

Click the dot.

- [ ] The provider list appears with each provider's percentage and bar
- [ ] Clicking a row opens its **detail** screen; the back arrow returns
- [ ] **Guide** and **About** open and return
- [ ] The **window picker** at the foot still swaps every row between
      Rolling / Weekly / Monthly
- [ ] **Settings** opens the config folder

**Expect:** exactly what it did before. The landing page is additive, so nothing
here should have moved.

### A2. Nothing to say → nothing interrupts

With no pending message, open the popover.

- [ ] It opens on the provider list, not on a quote

**Expect:** no quote. This is the normal state — `billboard` is `null` far more
often than not, and that is what stops it appearing on every open.

You can confirm there is nothing pending:

```bash
cursor-spend-monitor quote        # "No message yet..." and exit code 1
```

### A3. A fresh message lands as a quote

Create one on demand:

```bash
cursor-spend-monitor quote --generate --slot monthly
```

Then **close and reopen the popover** (or just open it — the daemon publishes on
open, so it should take the turn on the same open).

- [ ] The popover opens on a **quote**, set noticeably larger than the list text
- [ ] Under it: a **badge** and the **name** of one AI, plus a short role line
      ("doing the heavy lifting", "most tokens for the least spend", …)
- [ ] A **Continue** button
- [ ] The status dot carries a faint ring while the message is waiting

**Expect:** a real sentence containing your own numbers, and the AI named under it
is one the prose actually talks about.

### A4. Continue returns you to the list — and it does not come back

- [ ] Press **Continue** → the provider list appears
- [ ] Reopen the popover (immediately, and again a few minutes later)
- [ ] It goes **straight to the list**. No repeat.

**Expect:** one showing per message, remembered across a logout, because the
daemon stores the dismissal rather than the extension.

### A5. Latest reopens the newest one

- [ ] Open the popover → there is a **Latest** button in the header, next to
      Guide and About
- [ ] Click it → the newest message appears again
- [ ] It is labelled **"Earlier update"** (so it is clear this is not a fresh
      interruption)
- [ ] Continue returns to the list

**Expect:** this keeps working even for a message you dismissed, and even once it
is past its freshness window — it is the "show me the most recent one" affordance.

### A6. The featured AI matches the prose

Look at the badge and name under the quote, then read the sentence.

- [ ] The named AI is the one the sentence is about
- [ ] If the message advises moving provider, the featured AI is the one to move
      **to**, not the one in trouble

**Expect:** they agree. This is the `FEATURED:` contract; a mismatch would mean
the daemon and the model disagree, which is worth reporting.

### A7. A shareable line, and the Copy button

```bash
cursor-spend-monitor quote --generate --slot monthly   # the monthly slot carries one
```

- [ ] The quote is followed by a line starting `SHARE:`
- [ ] A **Copy** button sits next to Continue
- [ ] Clicking Copy puts that line on your clipboard (paste it somewhere)

### A8. A long quote wraps instead of being clipped

```bash
# stop the real daemon so the mock can own the bus name
systemctl --user stop cursor-spend-monitor.service
python3 gnome-shell-extension/devtest/mock_daemon.py "$PWD"
```

Now open the popover.

- [ ] The quote from the mock's second message wraps neatly over several lines
- [ ] Nothing is truncated with an ellipsis
- [ ] The panel is not pushed off-screen or widened

**Expect:** the popover keeps its width and grows downward. Then, to go back:

```bash
# Ctrl+C the mock, then
systemctl --user start cursor-spend-monitor.service
```

### A9. The mock cycles its messages (a deterministic billboard)

With the mock daemon still running from A8, each Continue advances it:

- [ ] It lands on an **actionable** message (a recommendation to move)
- [ ] Continue → the list → reopen → an **informative** one (a value finding)
- [ ] Continue → reopen → a **shareable** one
- [ ] Continue → reopen → the list, with no quote

**Expect:** the three kinds in that order — that is the priority rule
(actionable 3, informative 2, shareable 1) being exercised on real panel code.
`Latest` stays available the whole time.

---

## B. Simulating the clocks, by command

The daemon's schedule is daily/weekly/monthly and its alerts need a real meter.
These reach the same code paths without waiting.

### B1. The scheduled digest, without waiting for 18:00

```bash
# set the digest hour to right now
python3 - <<'PY'
import json, os
from datetime import datetime
p = os.path.expanduser("~/.config/cursor-spend-monitor/config.json")
cfg = json.load(open(p)) if os.path.exists(p) else {}
cfg["notify_daily_hour"] = datetime.now().hour
cfg["notify_enabled"] = True
os.makedirs(os.path.dirname(p), exist_ok=True)
json.dump(cfg, open(p, "w"), indent=2)
print("digest hour ->", cfg["notify_daily_hour"])
PY
systemctl --user restart cursor-spend-monitor.service
```

The daemon checks its schedule every 5 minutes, so within 5 minutes:

- [ ] A desktop notification arrives with the day's digest
- [ ] `cursor-spend-monitor quote` prints the same text
- [ ] Opening the popover lands on it

Put it back when you are done (`"notify_daily_hour": 18`), or delete the key.

### B2. The weekly and monthly slots

```bash
cursor-spend-monitor quote --generate --slot weekly
cursor-spend-monitor quote --generate --slot daily
cursor-spend-monitor quote --generate --slot monthly
```

- [ ] `--slot weekly` writes a weekly digest *and* a fun fact; the command prints
      the newest of the two, so a fun fact on screen is a pass, not a failure
- [ ] `--slot monthly` adds a month-over-month comparison
- [ ] `--slot daily` produces a digest **or** a fun fact
- [ ] Each one appears on the landing page on the next open

### B3. An actionable alert, without a meter actually hitting 90%

The event path needs either a meter at 90% or a burn-rate ETA sooner than
`wind_down_hours`. Raising that window is the config-only way to reach it:

```bash
python3 - <<'PY'
import json, os
p = os.path.expanduser("~/.config/cursor-spend-monitor/config.json")
cfg = json.load(open(p)) if os.path.exists(p) else {}
cfg["wind_down_hours"] = 500        # any meter with a computed ETA now qualifies
json.dump(cfg, open(p, "w"), indent=2)
print("wind_down_hours ->", cfg["wind_down_hours"])
PY
systemctl --user restart cursor-spend-monitor.service
```

- [ ] Within a poll or two, a notification arrives naming a provider, its meter
      and roughly how long is left, and **where to move to**
- [ ] Its featured AI on the landing page is the suggested one, not the one in
      trouble

**Note:** this needs enough recorded samples for the burn-rate fit to produce an
ETA (at least three samples across five minutes). If nothing fires, use the mock
in A8/A9 instead — its first message is exactly this case.

### B4. Turning the wording over to a model

```bash
python3 - <<'PY'
import json, os
p = os.path.expanduser("~/.config/cursor-spend-monitor/config.json")
cfg = json.load(open(p)) if os.path.exists(p) else {}
cfg["llm_notifications"] = True
cfg["llm_generator_provider"] = ""     # "" = whichever has the most headroom
cfg["llm_generator_model"] = ""
json.dump(cfg, open(p, "w"), indent=2)
PY
systemctl --user restart cursor-spend-monitor.service
cursor-spend-monitor quote --generate --slot weekly     # not LLM-composed: see note
```

**Note:** `quote --generate` writes straight to the ledger and never calls a
model — the daemon does that, because only the daemon knows the live meters. So
wait for the next digest (B1), then check **which** wrote it:

```bash
cursor-spend-monitor quote --json | grep -o '"composed_by":[^,}]*' || echo "template wrote it"
```

- [ ] `"composed_by":"claude"` or `"opencode"` → a model wrote it
- [ ] No such key → the template wrote it, which is a valid outcome, not a failure

- [ ] The wording reads like a sentence about your work, with the same numbers as
      `cursor-spend-monitor report`
- [ ] The featured AI still matches the prose

**Expect:** every failure degrades to the template. If you see an error instead of
a template, that is a real bug.

### B5. The ledger, end to end

```bash
cursor-spend-monitor harvest            # first run reads everything (~5-10s)
cursor-spend-monitor harvest            # second run
cursor-spend-monitor report
```

- [ ] The first run reports sessions per provider
- [ ] The **second run says `no change` for every reader** — this is the single
      most important line on this page
- [ ] `report` shows plausible totals and a top project and model
- [ ] `report --checks` includes a `cost_unit` row for Cursor (a **FAIL** here is
      expected — the unit is unverified and recorded rather than guessed)

```bash
cursor-spend-monitor report --week --by model
cursor-spend-monitor report --checks
cursor-spend-monitor quote --tweet --no-copy    # prints one SHARE: line
```

---

## C. Expected, and what would be a real bug

### Expected — please do not file these

- **Codex contributes no rows.** Its local store has no token column.
- **Pi shows 0 tokens.** Pi persists no token data, and no estimate is invented.
- **Cursor's `cost_unit` check FAILs**, and its current billing cycle may be
  empty.
- **The popover is unchanged after a plain daemon restart.** The extension needs
  the reload in §0 — GNOME only reads it at login.
- **`quote --generate` never uses the LLM.** Only the daemon composes, because
  only the daemon has the live meters (B4).
- **The default generator model ids are unverified.** A wrong id means the
  template is used.

### Real bugs — worth capturing

1. The quote appears on **every** open, or reappears after Continue.
2. Continue does not reach the provider list, or the popover closes.
3. The featured AI does not match the prose.
4. A second `harvest` reports sessions again.
5. A long quote is clipped or the panel is widened.
6. The daemon pegs a CPU core, or exits on a locked/unreadable store.
7. Any notification during your quiet hours (22:00–07:00 by default).
8. An error where a template should have been used (B4).

### When something looks wrong

```bash
systemctl --user status cursor-spend-monitor.service --no-pager | head -5
journalctl --user -u cursor-spend-monitor.service -n 200 --no-pager
cursor-spend-monitor report --checks

# what the panel is being told right now
python3 -c "import json,os;d=json.load(open('/run/user/%d/cursor-spend-monitor/state.json'%os.getuid()));print(json.dumps({k:v for k,v in d.items() if k in ('billboard','latestMessage','error','version')}, indent=2))"
```

The last one is the most useful: if `billboard` is `null` the daemon has nothing
to offer, and the panel is behaving correctly by showing the list.

### When a screen opens empty — a layout bug, not a JS bug

If the popover seems to vanish, or a screen comes up blank, the JavaScript
probably ran fine and the *layout* is broken. Nothing throws, so there is no
stack trace to follow, and the panel simply draws nothing.

One command reproduces every screen headlessly, with the mock daemon, no mouse
and no display:

```bash
./gnome-shell-extension/devtest/layout-smoke.sh
```

It walks list, guide, about, landing, detail and sessions in a throwaway Shell
and fails if any of them lays out to an impossible size. This is how the landing
page's own bug was found: a `margin-bottom: -8px` on one decorative label
subtracted more height than the box had, so the popover's preferred height
underflowed to −2147483648 and it was drawn as nothing.

The signal to grep for, in `journalctl /usr/bin/gnome-shell` or the shell's own
log:

```text
Actor 'unnamed [StBin]' tried to allocate a size of 360.00 x -2147483648.00
cogl_framebuffer_set_viewport: assertion 'width > 0 && height > 0' failed
```

A **negative** height there means a box is subtracting more than it has — a
negative margin, or an unset dimension in that screen's CSS.
