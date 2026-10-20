# tokens-go-brrr — Plasma plasmoid

Panel client for Plasma 6. Same D-Bus / `state.json` contract as the GNOME
Shell extension. Daemon owns policy; this UI only paints and compares
`billboard.id` for landing.

## Install (from source)

```bash
./install.sh --ui=plasma
```

Or copy `org.tokensgobrrr.panel` to `~/.local/share/plasma/plasmoids/` (see
`install.sh`), then add **tokens-go-brrr** to a panel.

## Layout

| Path | Role |
|------|------|
| `contents/ui/main.qml` | Plasmoid shell, theme, expand → open popover |
| `contents/ui/CompactRepresentation.qml` | Status dot + session chips |
| `contents/ui/FullRepresentation.qml` | List / detail / guide / about / landing |
| `contents/ui/StateModel.qml` | Read state file, D-Bus actions via busctl |
| `contents/ui/Tokens.qml` | Generated from `ui/tokens.json` |

Shared tokens and locales live under `ui/` and are copied in at stage/install time.

## Dev

```bash
python3 scripts/gen_ui_artifacts.py   # Tokens.qml + GNOME light CSS
```
