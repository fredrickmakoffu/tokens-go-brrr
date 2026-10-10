# Handover — popover redesign, site copy, website i18n, light and dark

**State:** #25–#31 shipped and merged; **#33 (extension i18n) and #34 (rename) are open**,
#34 stacked on #33. `main` @ `440c2b3`, version **0.6.2** (no release cut for any of this
yet). PRs [#25](https://github.com/fredrickmakoffu/cursor-spend-monitor/pull/25),
[#26](https://github.com/fredrickmakoffu/cursor-spend-monitor/pull/26),
[#27](https://github.com/fredrickmakoffu/cursor-spend-monitor/pull/27),
[#29](https://github.com/fredrickmakoffu/cursor-spend-monitor/pull/29),
[#30](https://github.com/fredrickmakoffu/cursor-spend-monitor/pull/30). **416 tests pass.**

**Left:** merge #33 then #34, then the logo.

---

## 1. What shipped

| PR | what | where |
| --- | --- | --- |
| #25 | Popover restyled to the AI Usage design system (square, hairlines, Barlow, pace ticks, Earlier insights page). Barlow bundled under the extension's `fonts/`; `install.sh` / `install-fonts.sh` install it. Daemon gained `Meter.elapsed_percent` (pace) and `recentMessages` in the state payload | `extension.js`, `stylesheet.css`, `providers/base.py`, `ledger.py`, `daemon.py` |
| #26 | Website copy rewritten: one job per section (hero → download → what it does → privacy → FAQ → releases). Simpler rate-limit modal. Privacy claim reduced to what the code supports | `site/*.jsx` |
| #27 | Website i18n: **en, fr, pt-BR**. Switcher in the top bar and footer | `site/i18n.js` |
| #29 | Website light and dark. Follows the system until the first click; the toggle is two-state and saved on click | `site/theme.js`, `site/styles.css` |
| #30 | Extension light theme, following GNOME's `color-scheme` | `stylesheet.css`, `extension.js`, `scripts/gen_light_css.py` |

| #33 | Extension i18n (en, fr, pt-BR). The daemon now sends numbers and template ids instead of English sentences | `i18n.js`, `locales.js`, `notify_engine.py`, `providers/base.py` |
| #34 | Display name "AI usage" → `tokens-go-brrr` (lowercase, hyphenated) | popover, notifications, README, site mock |

## 2. How each piece works

### Website i18n — `site/i18n.js`
No build step, so it is a plain script loaded before the JSX. `t("key", {vars})`; if
`vars.n` is set, `key_one` / `key_other` (Intl.PluralRules) win. Lookup falls back to
English, then to the key. Locale: `?lang=` → saved choice → browser → `en`. Switching
re-renders by keying the tree on the locale. The data behind the live popover
(`site/data.jsx`) is rebuilt by `loadData()` on every switch and mutated in place,
because the screens read it as globals. Four literals in the vendored design-system
bundle (`ds_bundle.js`: Settings, Back, Focus, Focused) were patched to call `window.t`
— **re-apply that patch if the bundle is ever regenerated.**

- Brand and technical strings are the same in every locale on purpose: "Tokens go
  brrr", provider names, commands, file names, the `−1.2k` / `−4k` label gag.
- Lowercase is a per-locale flag (`lower` in `LOCALES`), applied by CSS under
  `html[data-lower]`. All three locales have it on.
- **The French and Portuguese were written by me, not a native speaker.** Have one
  read them, the privacy and FAQ text first.
- GitHub release notes are shown as published (English).
- The `<noscript>` message is English only.
- One page means one language to search engines. Per-language URLs would fix that.

### Website theme — `site/theme.js`
Loaded in `<head>` so `data-theme` is on `<html>` before first paint. Until a click,
nothing is stored and the page tracks `prefers-color-scheme` live. A click flips
light/dark and saves it (`tgb-theme`). `?theme=light|dark` forces one load. Tokens
live in `site/styles.css` under `:root` (light) and `[data-theme="dark"]`.
`scripts/check_contrast.py` checks the token pairs in both themes; it does **not**
read the CSS, so change a token in both places. It found real misses: light-mode
amber, red and the primary button were under 4.5:1 and were darkened.

### Extension theme
St's CSS has no `var()`, so the dark rules stay literal and the light values are a
**generated block** at the end of `stylesheet.css`, scoped under `.ai-usage-light`.
Edit a dark rule, then `python3 scripts/gen_light_css.py` (idempotent). Colours set
from JS live in `PALETTES` in `extension.js`. The popover is light **only** when
`org.gnome.desktop.interface color-scheme` is `prefer-light`; `default` counts as
dark, because most installs sit on it and GNOME's panel is dark either way. Top-bar
chips always use the dark palette (`panelColorFor`).

## 3. Running and checking

```bash
python3 -m unittest discover -s tests -q                       # 416 tests
python3 scripts/check_contrast.py                              # website token contrast
SCHEME=prefer-light ./gnome-shell-extension/devtest/layout-smoke.sh    # or SCHEME=default
SCHEME=prefer-light ./gnome-shell-extension/devtest/capture-screens.sh /tmp/shots
cd site && python3 -m http.server 8765                         # the website, locally
```

Headless Brave works for the site: `brave-browser --headless=new --no-sandbox
--virtual-time-budget=15000 --screenshot=out.png "http://127.0.0.1:8765/?theme=dark&lang=fr"`.

**Gotcha:** a server started in `site/` serves the working tree, so switching branches
changes what it serves (this hid the theme toggle for a while). Serve from a
`git worktree` instead.

## 4. Publishing

Merged is not live. `publish-public.yml` copies `site/*` to `gh-pages` of the public
repo **when a release is published**, so the site changes above reach the world with the
next release. New files in `site/` are picked up by the `cp site/*`.

## 5. Not verified by eye

- Flipping `color-scheme` in a real session while the popover is open (smoke test and
  screenshots only).
- The website's theme toggle, language switcher and rate-limit modal were checked in
  headless Brave, not clicked through in a window. The modal in light mode especially.
- The 46 unticked boxes in `design/UI_TEST_GUIDE.md` are still a person's job.

## 6. Extension i18n and the rename (#33, #34)

**Data, not sentences.** Each meter carries `resetsSeconds` (and already had
`etaSeconds`); each message the engine wrote carries `template: {id, params}` in the
payload, taken from `meta.tpl` (`notify_engine._tpl`). The English `text` is unchanged
and is what the CLI prints and a model rewrites. `_template_of` drops the template when
`meta.composed_by` is set: a model-reworded message is its own prose, so it shows as
written, in English. Template ids: `digest`, `fun.cache`, `fun.streak`, `fun.longest`,
`share`, `actionable`. Adding one means: set `tpl` in the builder, add `tpl.*` keys to
all three catalogs, add a `case` in `templateText` (`extension.js`).

**Catalogs.** `locales.js` (en/fr/pt-BR) + `i18n.js` (`tr`, plurals, `duration`,
`formatTokens`, `metricLabel`). Locale from GLib's language names; `AI_USAGE_LANG`
forces one. A plain JS catalog, not gettext, so the packages need no `msgfmt` step;
the keys are stable if gettext is wanted for extensions.gnome.org later.
`tests/test_locales.py` (needs `node`) checks keys and `{placeholders}` for the
extension **and** the website catalogs.

**Fallbacks that stay English:** model-reworded messages; diagnostics with a detail
("HTTP 429 from Claude usage ..."); only a fixed list of daemon error strings is
translated (`err.*` keys); and an older daemon with no `resetsSeconds` shows its own
English label. Dates come from GLib's `LC_TIME`, so they follow the session, not
`AI_USAGE_LANG` (headless screenshots show English dates).

**Behaviour change:** Copy on a share line copies the sentence without the old
`SHARE:` marker when it renders from the template.

**Rename.** Display strings only. Deliberately unchanged: the extension UUID
`ai-usage@fredrickmakoffu.github.io`, D-Bus names (`...AIUsage`), `ai-usage-*` CSS
classes, `[ai-usage]` log prefixes, the config dir and package names
(`cursor-spend-monitor`) — changing them breaks installs and upgrades. The "AI Usage
design system" keeps its name. The popover kicker keeps the brand's own case instead of
uppercasing it.

## 7. What is next

1. Merge #33, then #34 (retargets to `main` by itself).
2. Native-speaker review of the French and Portuguese, on the site and in the extension.
3. A real-session check: French session against the real daemon.
4. The logo.
