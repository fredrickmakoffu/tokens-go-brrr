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

## Design parity

`stylesheet.css` carries the mockup's values verbatim: 360px wide with an 11px radius,
`#1c1c1e` on `#333336`, rows 9px/14px/9px/16px with 12px spacing, 3px bars, 19px bold
percentages, and the 70 / 90 thresholds for amber and red. Three things are translated
rather than copied, since St has no equivalent: the CSS `backdrop-filter` becomes an
opaque panel, `:focus-visible` becomes an explicit keyboard-focus class so the accent
bar never shows on a mouse click, and the drop shadow is retuned.

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
