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

## Testing without a real login

```bash
./devtest/run-nested.sh 60
```

That starts a throwaway headless GNOME Shell with a mock daemon serving the same three
providers as the mockup. Add a driver extension to the runtime directory if you want
scripted clicks and screenshots.

## Design parity

`stylesheet.css` carries the mockup's values verbatim: 360px wide with an 11px radius,
`#1c1c1e` on `#333336`, rows 9px/14px/9px/16px with 12px spacing, 3px bars, 19px bold
percentages, and the 70 / 90 thresholds for amber and red. Two things are translated
rather than copied, since St has no equivalent: the CSS `backdrop-filter` becomes an
opaque panel, and `:focus-visible` becomes an explicit keyboard-focus class so the accent
bar never shows on a mouse click.
