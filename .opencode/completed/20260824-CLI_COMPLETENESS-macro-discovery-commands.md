# Macro discovery commands (list, search, show)

**Completed:** 2026-08-24
**Epic:** CLI_COMPLETENESS
**Source:** .opencode/refined/CLI_COMPLETENESS-macro-discovery-commands.md

## Summary

Three read-only CLI commands — `rbxlight macro list`, `macro search`, `macro show` — replace the README's `python3 -c` one-liners for macro discovery. Query logic lives in the macros repo layer so the planned TUI can import it directly.

## Plan Approved by the user:

### Requirements Summary

- `macro list [--all|--factory]` — user macros by default; header "Macros:", lines `  <id>: <name> (<beats> beats)`, ordered by id asc; empty → "No macros found."
- `macro search <term> [--user|--all]` — factory macros by default; case-insensitive substring on name; SQL LIKE wildcards escaped as literals
- `macro show <id> [--yaml]` — metadata + all 25 slots marked programmed/empty; --yaml prints export_macro_yaml verbatim; unknown id → clean message + exit 1
- Missing working copy → reuse existing pull guard
- README: replace "Finding things" snippets, delete obsolete venue snippet, extend "Everyday commands" table

### Technical Approach

- Backend: `list_macros(conn, scope)` / `search_macros(conn, term, scope)` in `src/rbxlight/macros/repo.py`; three commands on `macro_app` in `src/rbxlight/cli.py`
- Frontend: none (visualizer untouched)

### Execution Order

| Phase | Agent | Task |
| ----- | ----- | ---- |
| 1 | backend-testing-agent | Failing pytest suite (repo queries + CLI commands) |
| 2 | backend-agent | Implement repo functions + CLI commands + README |
| 3 | backend-optimizer-agent | Refactor for maintainability |

## Implementation

### Backend

- `list_macros(conn, scope="user") -> list[Macro]`, `search_macros(conn, term, scope="user") -> list[Macro]` — single deterministic query per call, `ORDER BY id`, LIKE wildcards escaped (`\%`, `\_`) with `ESCAPE '\'`; shared helpers `_row_to_macro`, `_scope_where`, `_MACRO_COLUMNS`
- CLI: `macro_list`, `macro_search`, `macro_show` mirroring `venue list` structure; `_format_macro_line` output helper; `_resolve_macro_scope` shared flag resolver (rejects conflicting flags with clean message + exit 1); LookupError → "Macro {id} not found." + exit 1; slot summary always lists all 25 FIXTURE_SLOT_IDS
- DB changes: none — strictly read-only

### Frontend

- None

### Deviations from Plan

- Testing agent initially wrote search defaulting to USER scope with a redundant `--factory` flag, contradicting story §5 (default = factory). Caught in orchestrator review of test assertions before implementation; corrected (default factory, `--user`/`--all` only). One ordering test still carried the old assumption and was fixed after first implementation run.
- Repo-level `search_macros` default scope is `"user"` (function-level default only; the CLI passes factory explicitly). Tests exercise scopes explicitly.

## Agents Used

| Agent | Task | Result |
| ----- | ---- | ------ |
| deep-research-agent ×2 | CLI patterns; tests/README state | Complete |
| backend-testing-agent | Failing suite + two correction passes | Complete |
| backend-agent | Implementation | Complete |
| backend-optimizer-agent | Refactor | Complete |

## Files Modified

- `src/rbxlight/macros/repo.py` — list_macros, search_macros + private helpers
- `src/rbxlight/cli.py` — macro list/search/show commands + _format_macro_line, _resolve_macro_scope
- `tests/macros/test_discovery.py` — NEW: 31 repo-level tests
- `tests/test_cli.py` — 34 new CLI discovery tests
- `README.md` — "Finding things" rewritten (no python3 -c remains), venue snippet deleted, 3 rows added to "Everyday commands"

## Tests

- 65 tests written, all passing; full suite 644 passing

## Playbook Candidates

1. **Row-mapper + WHERE-builder extraction** (`_row_to_macro` / `_scope_where` in repo.py) — any repo.py building the same dataclass from multiple query sites benefits from extracting these as private helpers. Pattern captured here; no follow-up refactor implied.
2. **Mutually-exclusive-flag scope resolver** (`_resolve_macro_scope` in cli.py) — CLI flag groups sharing a default resolve to one canonical value via a single helper. Pattern captured here; no follow-up refactor implied.

Both are utility/pattern candidates, not reusable UI components — colocated with the feature, not added to any playbook route.
