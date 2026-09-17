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
About used to hold. That is the most reachable row in the menu and it was going
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
