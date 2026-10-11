# Agent guide — tokens-go-brrr

GNOME Shell indicator + local daemon for AI coding usage limits (Cursor, Claude, OpenCode, Codex, Pi).

## Before you change code

1. Read `.cursor/rules/` — product identity, architecture, and surface-specific rules apply automatically by glob.
2. Prefer the smallest change that preserves fail-soft behaviour and stdlib-only Python.
3. Do not rename frozen install IDs (UUID, D-Bus, package, config dir). Display brand only.

## Meter coercion policy

Unparsable utilization → drop the meter or use `error_snapshot`; never publish a
healthy `0%` for "unknown". A real vendor `0` / `"0"` is a reading. Config and
non-meter figures may use an explicit default (`tokens_go_brrr.coerce`). Shared
HTTPS JSON lives in `tokens_go_brrr.http_json` (`USER_AGENT` includes the package
version).

## Verify

```bash
make test
make lint          # Ruff E/F/I (CI)
python3 scripts/bump_version.py --check
# If you touch site colours:
python3 scripts/check_contrast.py
# If you touch extension dark CSS:
python3 scripts/gen_light_css.py
```

## Layout

| Path | Role |
|------|------|
| `tokens_go_brrr/` | Daemon, CLI, providers, harvesters, ledger, notify, LLM |
| `gnome-shell-extension/` | GJS popover + top bar |
| `site/` | Marketing page (no bundler) |
| `design/` | Product intent (check status lines — code may be ahead) |
| `tests/` | unittest suite |
| `packaging/` `systemd/` | Distro install |

## Do not

- Add PyPI dependencies without an explicit ask
- Invent 0% meters or silent `except:` that hides auth failures
- Put billboard/digest policy in the extension
- Treat `design/` "nothing implemented" or "no CI" lines as current without checking the tree
