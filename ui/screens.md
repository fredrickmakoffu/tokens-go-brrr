# Panel screen machine (GNOME + Plasma)

Parity checklist for both panel clients. Daemon owns policy; UI only paints
`state.json` / D-Bus and compares `billboard.id` for landing.

| Screen | Behaviour | GNOME | Plasma |
|---|---|---|---|
| Compact | Status dot (ok / hollow caution / critical / error); session chips with logos and ×N; % only at caution+ | yes | yes |
| List | Provider rows: primary %, bar, secondary chip; open detail | yes | yes |
| Detail | All meters, reset copy, open dashboard | yes | yes |
| Guide | Healthy / Caution / Critical legend | yes | yes |
| About | Daemon version, last refresh, manual refresh | yes | yes |
| Landing | Quote + featured provider; Continue acknowledges via D-Bus | yes | yes |

## Interrupt rule (entire policy in the UI)

```text
if billboard && billboard.id !== lastShownId → show landing
```

## Theme

`ui_theme` in config: `auto` | `dark` | `light`. Product palette from
`ui/tokens.json`. Host panel hover only on compact representation.
