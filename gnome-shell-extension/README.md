# AI usage — GNOME Shell extension

UUID: `ai-usage@fredrickmakoffu.github.io`

A status dot in the top bar and a popover that mirrors `design/menu-bar-concept.html`
one to one. The extension is presentation only: all data arrives from the
`cursor-spend-monitor` daemon over the session bus.

## Interface

`io.github.fredrickmakoffu.AIUsage` at `/io/github/fredrickmakoffu/AIUsage`:

| Member | Kind | Meaning |
|--------|------|---------|
| `Version` | property | Daemon version string |
| `GetState` | method | Current state as JSON |
| `Refresh` | method | Poll providers now |
| `SetPrimary(provider, metric)` | method | Persist a chip swap |
| `StateChanged(json)` | signal | Emitted after every poll |

State payload:

```json
{
  "version": "0.4.0",
  "updated_at": "2026-09-13T15:00:00+00:00",
  "error": null,
  "tools": [
    {
      "id": "cursor", "name": "Cursor", "icon": "cursor",
      "primary": "monthly", "status": "ok", "dashboardUrl": "https://cursor.com/dashboard",
      "metrics": [
        {"key": "monthly", "label": "Monthly limit", "value": 74, "resets": "Resets in 12 days"}
      ]
    }
  ]
}
```

The extension does not auto-start the daemon; if the name has no owner it shows a hint
telling you to start the service.

## Install

```bash
cp -r ai-usage@fredrickmakoffu.github.io ~/.local/share/gnome-shell/extensions/
gnome-extensions enable ai-usage@fredrickmakoffu.github.io
```

Log out and back in (Wayland) or restart the shell with Alt+F2 r (X11).

## Reloading without logging out

GNOME only scans for extensions at startup, but you do not have to log out to try a change.
`./devtest/live-reload.sh` stages the working tree as a fresh revision and prints a line to
paste into Looking Glass that swaps the running indicator for it. See
[devtest/live-reload.md](devtest/live-reload.md) for why a copy is needed and how to undo it.

## Testing without a real login

```bash
./devtest/run-nested.sh 60
```

That starts a throwaway headless GNOME Shell with a mock daemon serving the same three
providers as the mockup (Cursor, Claude Code, OpenCode). Add a driver extension to the
runtime directory if you want scripted clicks and screenshots.

`./devtest/run-nested-real.sh` does the same but runs the real daemon against your real
logins, so you see live numbers. It copies your config rather than using it, so chip swaps
made inside the sandbox do not change your settings.

## Brand marks

`icons/` carries each provider's own logo, taken from the app installed on this machine
rather than redrawn: Claude's is the vector from the Claude Code VS Code extension, Cursor's
is the app icon shipped with the Cursor editor. They keep their own colours, so the badge
uses `-st-icon-style: regular` and does not recolour its children. The chevrons stay
symbolic and follow the text colour. OpenCode has no local asset yet and falls back to a
bracket glyph. These marks are the trademarks of their respective owners and are used here
only to identify the service each row reports on.

## The window picker

Providers measure different windows, and the list used to ask about them once
per row: every provider carried its own chips, so four rows meant four copies of
the same question. The windows are now chosen once, at the foot of the list, and
every row shows the chosen one.

They cannot be matched on the metric key. Claude calls its short window
`five_hour` and OpenCode calls it `rolling`; Claude's `seven_day` is OpenCode's
`weekly`; and Codex names both of its meters generically — `monthly` and
`window` — so only its own `limit_window_seconds` says what either covers. So a
meter carries a declared `kind` (`rolling`, `weekly`, `monthly`, `other`), set
by the provider that knows, in the same spirit as `ProcessSpec`: the panel is
told, it does not guess.

The picker takes the row at the foot of the list, which Settings, Guide and
About used to hold, and keeps their shape: three flat buttons dividing the row
edge to edge. Selection cannot be carried by a fill alone, since hover fills
too, so the chosen window keeps a brighter, heavier label and an accent rule
along its top edge. That is the most reachable row in the menu and it was going
to three things you press once to read something; the window is the choice you
actually change. Those three move up into the header, in space the title was not
using.

Picking a window is a bulk chip swap — it calls the existing `SetPrimary` for
every provider offering that kind. Nothing new persists: the choice lives in the
daemon's `primary_overrides` as before, and the top bar, the alerts and the
status dot follow it because they already read the primary. The active window is
read back from what the rows are showing rather than stored, so the picker
cannot come to disagree with the panel beneath it.

**No provider offers every window.** Cursor publishes no weekly, Claude no
monthly, so some row is always the exception. A row that cannot honour the
choice keeps its own meter and names it, in the dim label the chips used to sit
in; a row that can say nothing at all. An exception that stayed silent would
read as though the picker had applied to it.

## Design parity

`stylesheet.css` carries the mockup's geometry: 360px wide with an 11px radius,
`#1c1c1e` on `#333336`, rows 9px/14px/9px/16px with 12px spacing, and the 70 / 90
thresholds for amber and red. Four things are translated rather than copied, since
St has no equivalent or the browser value does not survive the port: the CSS
`backdrop-filter` becomes an opaque panel, `:focus-visible` becomes an explicit
keyboard-focus class so the accent bar never shows on a mouse click, the drop
shadow is retuned, and the type scale is relative.

## Status colours

Green `#3ddc84`, amber `#ffb224`, red `#ff5c5c`, against gunmetal at 8.29, 8.20
and 4.89 to one. The mockup's softer trio was chosen against near-black and read
washed once the surface lightened.

**They are distinguishable without hue**, which took two changes. The first
amber tried was `#ffb224`, which sits at relative luminance 0.532 against the
green's 0.538 — a ratio of 1.01, meaning one swatch to a reader with red/green
colour blindness or in greyscale. The mockup's original palette was barely
better at 1.12:1, so this had been inherited rather than introduced. `#e8930f`
keeps the orange cast and takes the pair to 1.37:1.

Lightness alone is thin, though, and the top-bar dot is the one place a state is
carried by colour and nothing else — everywhere a meter is drawn the percentage
is written beside it. So caution is also drawn *hollow*: a 3px core inside a 3px
border, which keeps the 9px outer size so the panel does not reflow as the state
changes. Green and red are far enough apart in lightness (1.69:1) to need no
form of their own.

That makes every pair separable twice over, or once where it is plainly enough:

| | lightness | form |
|---|---|---|
| ok vs caution | 1.37:1 | solid vs ring |
| caution vs critical | 1.19:1 | ring vs solid |
| ok vs critical | 1.69:1 | both solid |

A halo was the first attempt at the form cue, and St renders `box-shadow` spread
without clipping it to the border radius, so the round dot got a square glow —
the same quirk that made the popover shadow read as a slab. A border follows the
radius.

## Motion

Opening the list plays an entry: each row fades and rises a beat after the one
above it, and its meter grows from the left once it has landed, so the eye goes
down the list and then watches the bars fill.

Three things this had to get right.

**It never overstates a meter.** The fill is allocated at its true width and
scaled in, and the easing is a plain ease-out. A bar that springs past its mark
and settles back shows more usage than the provider reported, and a quota display
has no business exaggerating even for a sixth of a second.

**It respects `enable-animations`.** With animations off nothing is hidden and
nothing eases; the menu is simply drawn. Verified in a nested shell with the
setting off — every row at full opacity and every bar at full width on the first
sample.

**Hiding and revealing are governed by one condition.** They were not at first,
and the bug is worth keeping written down: rows were hidden as the list was
built, and revealed only on the path that plays the entry. Four of the five
render call sites do not animate — `setState` among them — so every daemon poll
rebuilt the list invisible with nothing to bring it back, and the menu emptied
itself a few minutes after opening. Only the code that will play the entry is
allowed to hide anything for it, and if it hides and then cannot play, it puts
the actors back.

**The actors are hidden just before the entry is scheduled.** The entry runs one turn of the main loop after
the screen is built, because an ease started on an actor that has not been
allocated yet settles on its first frame — which is how the whole animation
silently did nothing until it was measured rather than watched. Anything visible
during that gap would flash at full value first, so rows and fills start at zero
and the entry only reveals them.

Opening the menu replays the entry even when the screen has not changed, which is
the usual case: the list is already up from last time.

## Surface and font

The popover is gunmetal — `#24282f` with `#474a50` edges — rather than the
mockup's near-black. Two things about it, and the second is why it is not slate.

A surface wants a temperature. `#1c1c1e` has only a level, and reads as a hole
cut in the desktop; a grey with a cast reads as a panel sitting on it.

But the cast has to stay under the name. An earlier pass ran at `#1e242f`, which
is blue enough that beside a neutral grey it reads navy rather than grey.
`#24282f` keeps the trace and drops the announcement, and being lighter it has
more presence as a material.

The whole ramp is derived from that one colour by mixing toward white at fixed
ratios, so the borders, dividers and hover states cannot drift out of family when
the surface is retuned — the four candidates for this change were generated and
contrast-checked that way before any of them was rendered. Text `#f0f0f0` at
12.98:1, secondary `#a3a5a8` at 5.99:1, and the green / amber / red at 8.4, 7.5
and 4.8, all past WCAG AA. `#73757a` is reserved for rules and icon glyphs, where
the 3:1 bar for UI components applies instead.

The top bar keeps neutral colours. It sits on GNOME's panel, which is not our
surface, so tinting its text to match a menu that is not open would be wrong.

The popover sets no `font-family`. The mockup asked for Inter, which is not
installed on a default Fedora or Ubuntu, so for the life of the project the menu
quietly rendered in Noto Sans while the shell, the top bar and every other
extension used Adwaita Sans. Inheriting is both more honest and more consistent.

Numbers carry `font-feature-settings: "tnum"`. Proportional digits change width
as they change value, so a meter ticking 9% to 10% nudged the text beside it, and
in the top bar shifted every chip along the row.

## Type scale

The popover sets no base `font-size`. The mockup pinned 13px and every child
below it in half-point steps, which is the whole story in a browser and the wrong
one here: it overrides the font the user picked and freezes the menu against
`text-scaling-factor`, so the popover stays put while every other menu on the
desktop grows. Sizes are `em` against the inherited shell font, which is what the
shell's own menus do.

Top-bar rules keep fixed px. The panel has a hard width budget — several
providers with session chips already run to the edge — so it is tuned on its own
and does not follow the popover.

Two consequences worth keeping. Secondary text is `#9a9ba0`, not the mockup's
`#6c6d70`: at 3.29:1 on `#1c1c1e` that failed WCAG AA for text this size, and it
was carrying the reset copy — the line most worth reading. And the meter bar is
an 8px slab rather than a 3px hairline, because the fill answers the question the
menu exists to answer and should not be something you look for. The slab geometry
is borrowed from `ai-usagebar`; the colour is not. That extension fills with
`-st-accent-color`, which would say the same thing at 20% as at 95%, and the
green / amber / red distinction is what the status dot, the Guide screen and the
alert thresholds are all built on.

The shadow is worth spelling out, because verbatim was tried first and looked wrong.
`box-shadow` does not mean the same thing in the two engines: CSS fades a shadow to
nothing across the blur radius, while St paints a blurred silhouette of the background
box with a much heavier profile and no clipping. The mockup's `0 20px 48px rgba(0,0,0,.5)`
reads as a soft lift in a browser and as a dark slab under the panel in the shell — most
obvious as the menu drops out of the top bar, or grows into a taller screen. `0 6px 16px
rgba(0,0,0,.45)` keeps the intent at values St renders as a shadow.

One deliberate departure: the mockup draws the selected window as plain text followed by a
single chip for the other one, and swapping trades their places. That leaves the large
percentage unattributed, and makes the badges jump around under the pointer. Every window
now gets a badge of its own in the provider's own order, the selected one filled and the
rest outlined, and picking one moves the fill without moving anything else. A provider
reporting a single window keeps plain text, since nothing is being selected.

Badges wrap onto further lines when they do not fit, which they will: three windows with
percentages exceed 360px, and Claude can report four. `BadgeFlow` does the line breaking,
because Clutter's own `FlowLayout` stacks the children at the same x rather than wrapping
them. Its greedy line breaking is shared between height reporting and allocation so the two
cannot disagree about the line count.
