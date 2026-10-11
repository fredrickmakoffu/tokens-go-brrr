# Implementation plan — standards conformance

**Implements:** `.cursor/rules/*`, `AGENTS.md` (coding standards established 2026-10-11)
**Baseline commit:** `4fc490b` (Cursor rules + Ruff E/F/I in CI)
**Status:** Phases 0–8 complete for in-scope work. Remaining backlog: B23 LICENSE,
B24 `AI_USAGE_LANG` rename (out of band).
**Baseline checks:** `make test` / `make lint` / `make format-check` green; stdlib-only
**Tracking:** `design/STANDARDS_BACKLOG.md`

This plan turns the audit into ordered, independently shippable steps. Each
phase states what it changes, what it deliberately does **not** change, its
tests, and how to verify. The Cursor rules stay the *law*; this document is the
*migration order*.

House style (locked):

- stdlib only (`dependencies = []`)
- fail-soft vendor edges; panel stays up
- unittest + fakes + temp dirs
- daemon owns policy; extension renders
- display brand may change; UUID / D-Bus / package / CSS prefix frozen

---

## Goals and non-goals

### Goals

1. One coercion / HTTP / time-parse toolkit — stop cloning helpers.
2. Consistent meter and auth error policy across providers.
3. Identity and docs match the shipped product.
4. Ruff (and later format) actually describe the tree, not a debt pile.
5. God modules shrink along existing seams when next touched — not a rewrite for its own sake.
6. Extension and site contracts stay aligned with the daemon.

### Non-goals

- Renaming the GitHub repo or frozen install IDs.
- Introducing pytest, a site bundler, or new PyPI dependencies.
- A big-bang split of `ledger.py` / `notify_engine.py` / `extension.js` without a feature need.
- Native-speaker i18n review (tracked separately; not blocking conformance).
- Choosing a LICENSE (tracked separately; packaging already has a TODO).

---

## Phase 0 — Inventory gates (½ day)

**Status:** ✅ **done.**

**Why first:** later phases need a checklist that CI can grow into, and a
single place that names every known smell so PRs can close rows.

**Did**

1. Added `design/STANDARDS_BACKLOG.md` with status `open | done | wontfix`.
2. Documented the **meter coercion policy** in `AGENTS.md` / `python.mdc`.
3. README architecture diagram still stale (fix in Phase 2).

---

## Phase 1 — Shared Python toolkit (1–2 days)

**Status:** ✅ **done.**

**Why:** highest smell density; every provider/harvester PR currently re-copies
`_as_int` / `_parse_iso` / `_jwt_exp` / HTTPS GET.

**Did**

1. Added `tokens_go_brrr/coerce.py` (`as_int`, `as_float`, or_none variants,
   `parse_iso`, `parse_ms_or_iso`, `jwt_exp`).
2. Added `tokens_go_brrr/http_json.py` (`request_json` / `request_json_url`,
   `USER_AGENT = tokens-go-brrr/<version>`). Migrated Cursor, Claude, OpenCode,
   Codex, OAuth refresh, and `llm_composer`.
3. Removed duplicate JWT helper from Codex; `local_auth` uses `coerce.jwt_exp`.
4. Cursor utilization now uses `as_float_or_none` — unparsable windows are
   dropped instead of becoming a healthy 0%.
5. Call sites import shared helpers (thin `_as_*` aliases where churn was high).

**Tests:** `tests/test_coerce.py`; Cursor drop case in `tests/test_provider_usage.py`.

**PR shape:** `refactor: shared coerce and HTTP helpers`.

---

## Phase 2 — Identity, docs, and packaging truth (½–1 day)

**Status:** ✅ **done.**

**Why:** agents and humans trust README / design status / package blurbs; several
still lie or lag the rename.

**Do**

1. README architecture block: list all five providers + harvesters/ledger.
2. Flip `design/BILLBOARD_LANDING_PAGE.md` status to implemented (with pointer
   to tests / extension landing).
3. Mark stale handovers **Historical** or refresh version/test counts
   (`HANDOVER_*`, “no CI”, open PR lists).
4. Packaging + `metadata.json` descriptions: include Codex and Pi.
5. Site: fix noscript releases URL → `tokens-go-brrr-releases`; align
   `ABOUT.version` with `pyproject.toml` when site-visible.
6. Scrub kit titles `"AI usage"` in `site/ds_bundle.js` / design mocks that are
   still presented as current UI chrome (wireframes may keep historical labels
   if marked historical).
7. Fix `config.py` docstring reference to nonexistent `notifications.py`.

**Do not:** rename `AI_USAGE_LANG` (needs a migration plan of its own).

**Verify:** grep for `cursor-spend-monitor-releases`, `claude later`, and
billboard “Nothing implemented” returns nothing in live docs; packaging text
matches README provider table.

**PR shape:** `docs: align identity and design status with shipped product`.

---

## Phase 3 — Provider / harvester contract alignment (1–2 days)

**Status:** ✅ **done.**

**Depends on:** Phase 1.

**Do**

1. Codify in code comments + tests:
   - `process_specs` is always a **tuple**
   - Claude/OpenCode/Cursor util parsing follows Phase 0 meter policy
   - Harvester failures: `failed=True` vs skip counts documented per reader
2. Type `PROVIDERS` / `REGISTRY` as `dict[str, type[Provider]]` /
   `list[type[Harvester]]` (structural Protocols stay).
3. Replace `ProviderSnapshot.backend: Any` with a real type or Protocol.
4. Prefer `dataclasses.replace` for `with_primary` / similar.
5. Align D-Bus: extension `IFACE_XML` ↔ `dbus_service.py` ↔ extension README
   table (Acknowledge, LLM log methods, Quit).

**Tests:** extend provider tests for util edge cases; add a small D-Bus IDL
parity test if cheap (string/fixture compare), else manual checklist in PR.

**Verify:** no mutable class-level `process_specs` list; D-Bus method sets match.

**PR shape:** `fix: align provider contracts and D-Bus surface`.

---

## Phase 4 — Ruff tighten + format pass (1 day)

**Status:** ✅ **done.**

**Depends on:** Phase 1 mostly done (less churn on helpers).

**Do**

1. One dedicated PR: `ruff format tokens_go_brrr tests scripts` only — no
   behaviour edits.
2. Enable `E501` at 100; fix remaining long lines (or deliberate `noqa` with why).
3. Enable `UP` then `B`/`SIM` in follow-up commits if noise is low; `BLE` last
   (fail-soft edges keep `# noqa: BLE001` with why).
4. Add `make format-check` to CI only after the format PR merges.

**Do not:** mix format with feature work.

**Verify:** `make lint` and `make format-check` green in CI.

**PR shape:** `chore: ruff format and tighten lint rules` (format-only first if large).

---

## Phase 5 — State I/O and Cursor API placement (½–1 day)

**Status:** ✅ **done.**

**Do**

1. Colocate `write_state` with `read_state` / `build_payload` (move out of
   `config.py` or make `config` re-export briefly).
2. Rename or relocate Cursor-only `api.py` → `providers/cursor_api.py` (keep a
   thin re-export if needed for one release).
3. Update imports and README pointers.

**Tests:** existing state/CLI tests; no behaviour change.

**Verify:** `rg 'from tokens_go_brrr.api|from \\.api'` clean after re-export window.

**PR shape:** `refactor: colocate state I/O; nest Cursor API under providers`.

---

## Phase 6 — Split god modules along existing seams (multi-PR, opportunistic)

**Status:** ✅ **done** — `notify_engine/` and `ledger/` packages with seam
facades over `core.py`; `borrowing.py` extracted; CLI in `cli/app.py`.

**Rule:** extract only when a feature or bug forces you into the file, **or** as
dedicated extract PRs that are behaviour-preserving with identical tests.

Suggested order (each is its own PR):

| PR | Extract from | Into | Facade kept at |
|----|--------------|------|----------------|
| 6a | `notify_engine.py` | `notify_engine/billboard.py`, `live_notes.py`, … | `notify_engine/__init__.py` |
| 6b | `ledger.py` | `ledger/schema.py`, `sessions.py`, `messages.py`, `queries.py` | `ledger` package |
| 6c | `daemon.py` | `polling.py`, `borrowing.py`, note workers | `UsageDaemon` wiring only |
| 6d | `__main__.py` | `cli/*.py` per command group | `__main__:main` |

**Do not:** change extension.js structure until 6a–6c stabilize the payload
contract; then consider GJS sectioning only if packaging still allows a single
entry file (many Shell extensions stay one file — section headers may be enough).

**Verify per PR:** full unittest suite identical pass count ± new extract tests;
manual smoke: panel opens, harvest, billboard path if touched.

---

## Phase 7 — Extension and site hygiene (1–2 days)

**Status:** ✅ **done.**

**Do**

1. Extension README: sample state schema current (`billboard`, camelCase fields,
   version-name); remove superseded gunmetal essay or move under “Historical”.
2. Ensure `tests/test_locales.py` runs in CI when `node` is available (install
   node in the workflow or skip with an explicit message).
3. Wire `scripts/check_contrast.py` into CI (site token pairs).
4. Optional: minimal ESLint/Biome later — only if the team wants JS tooling;
   not required for conformance if locale + contrast gates exist.
5. Document canonical visual truth: extension CSS + AI Usage DS tokens;
   demote `design/menu-bar-concept.html` / `design/screens/` as references.

**Verify:** CI runs contrast + locale tests; extension README sample matches
`state.build_payload` keys used by the extension.

**PR shape:** `chore: extension docs and site CI gates`.

---

## Phase 8 — Observability and debt burn-down (ongoing)

**Status:** ✅ **done** for this pass (`logutil.py`; P0/P1 backlog closed).

**Do opportunistically**

1. Consider a tiny stderr logger wrapper (levels) without pulling in logging
   frameworks — optional; match file-local style until then.
2. Close backlog rows when touched.
3. After each release: bump site `ABOUT.version`; run packaging blurb check.
4. Re-read `.cursor/rules/` quarterly; keep under ~50 lines per rule.

**Done when:** backlog has no `open` items marked P0/P1; Ruff select includes
E501 + agreed extras; README architecture matches tree.

---

## Suggested PR sequence (summary)

| Order | Phase | Effort | Risk |
|------:|-------|--------|------|
| 1 | 0 Inventory + policy sentence | S | None |
| 2 | 1 Shared toolkit | M | Low–med (meter policy edges) |
| 3 | 2 Identity / docs / packaging | S | None |
| 4 | 3 Provider + D-Bus alignment | M | Low |
| 5 | 4 Format + lint tighten | M | Noise-only if format-only |
| 6 | 5 State I/O + api placement | S | Low |
| 7 | 6a–6d God-module extracts | L each | Med — keep behaviour-identical |
| 8 | 7 Extension/site CI | S–M | Low |
| 9 | 8 Ongoing | — | — |

Phases 2 and 1 may proceed in parallel. Phase 4 should not overlap large
Phase 1 diffs. Phase 6 waits until Phase 1 is merged to avoid merge pain.

---

## Verification cheat sheet (every conformance PR)

```bash
make lint
make test
python3 scripts/bump_version.py --check
# when touching site colours:
python3 scripts/check_contrast.py
# when touching extension dark CSS:
python3 scripts/gen_light_css.py
# when touching locales:
python3 -m unittest tests.test_locales -v   # needs node
```

Manual when UI/daemon contract changes: open popover, confirm landing rule still
compares `billboard.id` only; Confirm Continue acks; Confirm borrowed Pi meters
do not double-vote the status dot.

---

## Backlog seed (from audit)

Copy into tracking; mark done as PRs merge.

| ID | Item | Phase | Priority |
|----|------|-------|----------|
| B1 | Shared `_as_*` / ISO / JWT | 1 | P0 |
| B2 | Shared HTTP JSON helper | 1 | P0 |
| B3 | Meter policy: no invented 0% | 1 | P0 |
| B4 | User-Agent version string | 1 | P1 |
| B5 | README architecture stale | 2 | P0 |
| B6 | Billboard design status lie | 2 | P0 |
| B7 | Handover “no CI” / open PRs | 2 | P1 |
| B8 | Packaging omits Codex/Pi | 2 | P1 |
| B9 | Site noscript + ABOUT.version | 2 | P1 |
| B10 | `ds_bundle` / kit “AI usage” | 2 | P2 |
| B11 | Codex `process_specs` list | 3 | P1 |
| B12 | D-Bus IDL skew | 3 | P0 |
| B13 | `ProviderSnapshot.backend` typing | 3 | P2 |
| B14 | Ruff format + E501 | 4 | P1 |
| B15 | `write_state` next to `read_state` | 5 | P2 |
| B16 | `api.py` under providers | 5 | P2 |
| B17 | Split notify_engine | 6a | P2 |
| B18 | Split ledger | 6b | P2 |
| B19 | Slim daemon | 6c | P2 |
| B20 | Split CLI `__main__` | 6d | P3 |
| B21 | Locale + contrast in CI | 7 | P1 |
| B22 | Extension README schema sample | 7 | P1 |
| B23 | LICENSE decision | — | P2 (out of band) |
| B24 | Rename `AI_USAGE_LANG` | — | P3 (migration) |
