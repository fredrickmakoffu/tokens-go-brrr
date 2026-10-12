# Plasma panel UI + DE-aware packaging

**Status:** implemented — package split (`tokens-go-brrr` / `-gnome` / `-plasma`),
`ui/tokens.json` + locales, Plasma plasmoid `org.tokensgobrrr.panel`,
`install.sh --ui=`, site GNOME/Plasma download cards. Polish and live Plasma QA
remain open (parity smoke against a real session).
**Date:** 2026-10-12
**Scope:** (1) serve a KDE Plasma top-bar / panel client that is one-to-one with
the GNOME Shell extension in UX and look; (2) split packaging so a GNOME machine
never gets Plasma deps and a Plasma machine never gets `gnome-shell`; (3) share
visual tokens and locales without sharing toolkit code; (4) keep both UIs paint-
only and cheap.

What we are deliberately *not* building here: Windows / macOS tray apps (see
`RELEASE_AND_DISTRIBUTION.md` — different transport), an Electron/WebView shell
for "one UI everywhere", or restyling the popover as Breeze / Adwaita chrome.

---

## 1. Product law (unchanged)

1. **Daemon owns policy; UI renders.** Billboard, ack, digests, which message
   interrupts — Python. Every panel client only compares `billboard.id` and paints.
2. **Published state** (`state.build_payload` + schema) and the D-Bus IDL are the
   only contracts. Plasma speaks the same methods as the GNOME extension
   (`GetState`, `Acknowledge`, …).
3. **stdlib-only** daemon. No new PyPI deps; no DE imports in `tokens_go_brrr/`.
4. **Templates first; LLM optional** — UI does not call models.

---

## 2. System shape

```text
                    ┌─────────────────────────────┐
                    │  tokens_go_brrr (daemon)     │
                    │  policy · ledger · notify    │
                    │  D-Bus + state.json          │
                    └─────────────┬───────────────┘
                                  │ same IDL + schema
              ┌───────────────────┼───────────────────┐
              ▼                                       ▼
┌─────────────────────────┐             ┌─────────────────────────┐
│ gnome-shell-extension/  │             │ plasma/ (new)           │
│ GJS · St · stylesheet   │             │ QML plasmoid            │
│ compact: panel button   │             │ compactRepresentation   │
│ full: PopupMenu         │             │ fullRepresentation      │
└─────────────────────────┘             └─────────────────────────┘
              ▲                                       ▲
              │         shared source of truth        │
              └────────── ui/  (new, see §5) ─────────┘
```

| Layer | Shared? | Notes |
|---|---|---|
| Daemon, CLI, systemd user unit | Yes | Deps: Python, PyGObject, libnotify only |
| D-Bus IDL + `schema` | Yes | Keep `dbus_service.py` and every client's iface XML/IDL in lockstep |
| Strings | Shared catalog under `ui/locales/` | Both UIs bind by key |
| Visual tokens | Shared `ui/tokens.json` | Colours, widths, type roles |
| Panel chrome implementation | **No** | GJS ≠ QML; do not wrap either in Electron |

---

## 3. Package layout

Split today's monolith into three installable units.

| Package | Contains | Hard requires | Audience |
|---|---|---|---|
| `tokens-go-brrr` | daemon, CLI, user unit, Barlow fonts, licenses | `python3` ≥ 3.11, `python3-gobject` / `python3-gi`, `libnotify` | everyone |
| `tokens-go-brrr-gnome` | extension under `/usr/share/gnome-shell/extensions/<uuid>/` | `tokens-go-brrr`, `gnome-shell` | GNOME only |
| `tokens-go-brrr-plasma` | plasmoid under `/usr/share/plasma/plasmoids/<id>/` | `tokens-go-brrr`, Plasma 6 / KF6 as needed | Plasma only |

**Rules:**

- Core must **not** `Requires: gnome-shell` or any Plasma UI package.
- Never install both UI packages by default.
- Optional empty meta packages are fine for distro convenience; they must not
  pull the wrong DE.

### Staging

`packaging/stage.sh` becomes (or grows siblings):

```text
stage-daemon.sh   → /usr/bin, site-packages, systemd, fonts, licenses
stage-gnome.sh    → gnome-shell/extensions/…
stage-plasma.sh   → plasma/plasmoids/…
```

RPM/DEB: one artifact per stage so Fedora GNOME and Fedora KDE downloads differ.

### Frozen names

Keep: extension UUID `tokens-go-brrr@fredrickmakoffu.github.io`, D-Bus
`TokensGoBrrr`, CSS / class prefix `tokens-go-brrr-*`, config and data dirs,
systemd unit, base package name `tokens-go-brrr`.

**New freeze (pick once when implementing):** Plasma plasmoid id, e.g.
`org.tokensgobrrr.panel` — do not rename after first release.

---

## 4. How install picks the UI

Detection is by **session**, not by "is `gnome-shell` on disk" (that false-
positive is exactly the KDE-on-Fedora trap).

```text
priority:
  1. flag:  --ui=gnome|plasma|none|auto
  2. env:   XDG_CURRENT_DESKTOP / XDG_SESSION_DESKTOP
            (GNOME* → gnome; KDE|Plasma* → plasma)
  3. fail:  install daemon only; print how to pass --ui=
```

| Result | Installed |
|---|---|
| `gnome` | core + GNOME extension (enable via `gnome-extensions` / gsettings as today) |
| `plasma` | core + plasmoid (user adds widget to panel if not auto) |
| `none` / unknown | core only — CLI, notifications, `state.json` for Waybar etc. |

`install.sh` and the site download cards must follow the same matrix. Distro
users: `dnf/apt install tokens-go-brrr tokens-go-brrr-gnome` (or `-plasma`).

---

## 5. Shared `ui/` (parity without toolkit sharing)

"1:1 UI/UX" means the same screens, hierarchy, copy, meter behaviour, and visual
tokens — not the same widget code.

| Artifact | Role |
|---|---|
| `ui/tokens.json` | Graphite `#2b2b2d`, snow `#f5f5f8`, steel `#94bce3`, hairlines `#4b4b4e`, caution / critical / error, ~380px popover, 9px dot, spacing, type roles (Barlow / Condensed) |
| `ui/locales/*.json` | All user-visible keys (en, fr, pt-BR today); both UIs load by key |
| `ui/screens.md` | Screen machine: list → detail → guide → about → landing; billboard interrupt; session-chip rules |
| Golden captures | GNOME `layout-smoke` + a Plasma screenshot harness against the same mock daemon |

Codegen (when tokens land): extend the family of `scripts/gen_light_css.py` so
dark tokens generate GNOME light CSS **and** a QML palette / `Tokens.qml`, so
colours cannot drift independently.

Until `ui/tokens.json` exists, the live GNOME stylesheet + `PALETTES` remain
canonical (see `VISUAL_TRUTH.md`). After tokens land, **tokens + both live UIs**
win over mocks.

### Visual law (both DEs)

- Product chrome = AI Usage design system (square, hairlines, Barlow) — **not**
  a Breeze or Adwaita restyle of the popover.
- Host integration only where required: compact control hover/press should match
  the host panel (GNOME already does; Plasma compact should match Plasma panel
  hover).
- Light theme follows OS preference when `ui_theme` is `auto`, else the override.

### Parity gate

A change that alters layout, copy, or meter presentation is incomplete until:

1. GNOME extension updated, and
2. Plasma QML updated (or explicitly waived with a tracked issue), and
3. Both smoke against `gnome-shell-extension/devtest/mock_daemon.py` (or a shared
   mock entrypoint).

Same discipline as keeping extension `IFACE_XML` and `dbus_service.py` in sync.

---

## 6. Plasma client

**Target:** Plasma 6 panel / system-tray **plasmoid** (QML). Not StatusNotifier-
only: SNI cannot host session chips beside the dot the way the GNOME compact
representation does.

Proposed tree:

```text
plasma/
  org.tokensgobrrr.panel/          # freeze id at first ship
    metadata.json
    contents/
      ui/
        main.qml                   # compact + full shell
        Compact.qml                # dot, session chips, hover
        Popover.qml                # list / detail / guide / about / landing
        screens/…                  # one file per screen
      code/
        DBusClient…                # GetState, Acknowledge, name-owner
        ViewModel…                 # map payload → screens; billboard id gate only
ui/                                # shared (§5)
```

| Surface | GNOME today | Plasma |
|---|---|---|
| Compact | panel button: dot + chips | `Plasmoid.compactRepresentation` |
| Full | `PopupMenu` ~380px | `fullRepresentation` in panel popup / dialog |
| Theme | `org.gnome.desktop.interface color-scheme` | same product dark/light; KDE color-scheme / appearance portal when `ui_theme=auto` |
| Policy | compare `billboard.id` only | identical |

---

## 7. Performance (both UIs)

Non-negotiable:

1. No vendor HTTP from the UI — D-Bus and/or `state.json` only.
2. Compact representation updates on **diffed fields** (status, chips), not a
   full rebuild every poll.
3. Full popover builds **on open** (and while open on state change); closed =
   near-zero work.
4. No WebEngine / QtWebView / Electron.
5. Prefer D-Bus signals / name-owner changes over polling; if polling, match
   daemon publish cadence (seconds), not frames.
6. Reuse the same SVG provider marks; Barlow comes from the core fonts package
   once.

---

## 8. Configuring look

Look stays out of daemon policy except a small preference both UIs may read.

In `~/.config/tokens-go-brrr/config.json`:

```json
{
  "ui_theme": "auto",
  "ui_density": "default"
}
```

| Key | Values | Behaviour |
|---|---|---|
| `ui_theme` | `auto` \| `dark` \| `light` | `auto` follows the DE color-scheme; otherwise force the product palette |
| `ui_density` | `default` only in v1 | Reserved; do not invent a second layout yet |

UIs may read the config file themselves so the daemon stays DE-agnostic.
Publishing `ui_theme` on the payload is optional later if it simplifies clients.

**Not user-configurable (product identity):** graphite/steel palette, square
geometry, ~380px width, Barlow, class/prefix naming. Settings UIs (GNOME or
Plasma) offer theme override and links to `tokens-go-brrr setup` / docs — not a
second settings store for chrome.

---

## 9. Distro and site matrix

```text
                    detect DE
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
      GNOME           Plasma         other / none
         │              │              │
   …-gnome pkg     …-plasma pkg    daemon only
```

| Distro session | Install |
|---|---|
| Fedora / Debian GNOME | `tokens-go-brrr` + `tokens-go-brrr-gnome` |
| Fedora / Debian Plasma | `tokens-go-brrr` + `tokens-go-brrr-plasma` |
| Unknown / headless | `tokens-go-brrr` only |

Site release cards: separate GNOME and Plasma Linux downloads (not one "Linux"
RPM that pulls the wrong shell).

---

## 10. Delivery order

| Phase | Work | Done when |
|---|---|---|
| **P1** | Split packages: core without `gnome-shell`; `-gnome` carries the extension | KDE install of core does not pull GNOME Shell; GNOME path unchanged |
| **P2** | Add `ui/tokens.json` (+ locale extract plan); GNOME consumes or generates from it | Tokens are the visual source; `gen_light_css` (or successor) reads them |
| **P3** | Plasma MVP: compact dot + list/detail over D-Bus | Usable on Plasma session with mock or live daemon |
| **P4** | Parity: landing/billboard, session chips, guide/about, light theme, smoke | Checklist in `ui/screens.md` green on both |
| **P5** | `install.sh --ui=` + site cards | Auto never installs both UIs |

P1 is valuable on its own and unblocks the KDE "why did gnome packages land?"
report without waiting for QML.

---

## 11. Out of scope (this doc)

- Windows / macOS clients and localhost HTTP transport
- Rewriting the GNOME extension in QML or Qt
- Making the popover look like the host DE's widgets
- Auto-switching UI packages when the user later changes session type (they
  install the other `-gnome` / `-plasma` package explicitly)

---

## 12. Related docs

| Doc | Relationship |
|---|---|
| `VISUAL_TRUTH.md` | Visual ownership; updates when `ui/tokens.json` lands |
| `RELEASE_AND_DISTRIBUTION.md` | Release pipeline; package matrix and Linux UI split |
| `BILLBOARD_LANDING_PAGE.md` | Landing interrupt rules both UIs must honour |
| `architecture` (`.cursor/rules/architecture.mdc`) | Daemon vs UI boundary |
| Extension `IFACE_XML` / `dbus_service.py` | IDL both clients must match |
