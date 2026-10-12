# Visual source of truth

**Canonical:** `ui/tokens.json` (colours, thresholds, popover width, typefaces)
plus both live panel UIs:

* GNOME: `gnome-shell-extension/tokens-go-brrr@fredrickmakoffu.github.io/stylesheet.css`
  and `extension.js` (`PALETTES` — keep aligned with tokens; regenerate light CSS
  with `python3 scripts/gen_light_css.py` / `gen_ui_artifacts.py`)
* Plasma: `plasma/org.tokensgobrrr.panel/contents/ui/` (Tokens.qml is generated
  from `ui/tokens.json`)

AI Usage design system: graphite `#2b2b2d`, snow `#f5f5f8`, steel `#94bce3`,
hairlines `#4b4b4e`, Barlow, ~380px, square geometry.

**References only (not current chrome):**

* `design/menu-bar-concept.html`
* `design/screens/`

When mocks disagree with tokens or a live UI, tokens + live UIs win.
Screen machine for parity: `ui/screens.md`. Packaging / DE split:
`design/PLASMA_AND_PACKAGING.md`.
