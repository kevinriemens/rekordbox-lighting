# Interactive menu (questionary-based CLI frontend)

**Completed:** 2026-08-24
**Epic:** TUI
**Source:** `.opencode/refined/TUI-interactive-menu.md`

## Summary

New interactive terminal menu ("TUI") for `rbxlight`, at feature parity with the CLI including writes. Accessible via `rbxlight` with no arguments or `rbxlight tui`. Implements a two-tier confirmation model: working-copy actions (macro create/delete, layout regenerate/install, sync pull) use ordinary `confirm(default=False)`; live actions (sync push, backups restore) use distinct danger rendering with typed confirmation. Built as a new flat `src/rbxlight/menu/` package (1030 lines across 13 modules) calling the domain layer directly, with 62 new tests in `tests/tui/`. All 719 pre-existing tests passed unmodified.

## Origin — why this story exists

The TUI was blocked by two prerequisite extractions: the shared write layer (making safety reusable) and the shared orchestration layer (making venue resolution, layout regenerate/install, and preview generation callable without importing `cli.py`). Both were completed first. This story implements the menu itself.

## Plan Approved by the user

### Requirements Summary

- Entry points: `rbxlight` (no args) and `rbxlight tui` both open the menu
- All existing CLI commands work unchanged
- Top-level menu organized by user intent (Macros, Preview, Layout, Venues, Sync, Backups, Exit)
- Macros submenu: list, search, show, create, delete
- Preview: generate HTML visualizer
- Layout: regenerate, install
- Venues: list
- Sync: pull, push
- Backups: list, restore
- Two-tier confirmation: working-copy actions use normal confirm; live actions use danger rendering + typed confirmation
- Non-TTY detection with clear error message
- Ctrl-C exits cleanly with no traceback
- Full test suite passes; no existing tests modified
- README.md updated with TUI section

### Technical Approach

- New `src/rbxlight/menu/` package with flat module structure (no nested sub-packages)
- Questionary for prompts; rich for rendering
- Direct domain layer calls (no `cli.py` import)
- Shared safety and orchestration layers from prerequisite stories
- Injected-double test seam: `ScriptedPrompter` (scripted answers + call recording) and `RecordingRenderer` (records rendering calls)
- Location constants read at call time, never bound at import

### Execution Order

| Phase | Agent | Task |
| ----- | ----- | ---- |
| 1 | backend-testing-agent | 58 tests across 8 files + doubles + conftest |
| 2 | backend-agent | Implement menu package |
| 3 | backend-optimizer-agent | Refactor pass |
| 4 | general-task-agent | CLI wiring + README |

## Implementation

### Backend

**New — `src/rbxlight/menu/` package (1030 lines total):**

- `prompts.py` (76 ln) — `Prompter` Protocol (`select`, `text`, `confirm`, `confirm_typed`) + `QuestionaryPrompter` implementation
- `render.py` (52 ln) — `Renderer` Protocol (`line`, `plan`, `error`, `danger`) + `RichRenderer` implementation
- `tty.py` (29 ln) — `require_interactive_tty()`, `NotATtyError`
- `actions.py` (149 ln) — domain wrappers for all menu operations; location constants read at call time
- `mutation.py` (69 ln) — shared `run_working_copy_mutation` / `run_live_mutation` loop helpers encoding the two-tier confirmation
- `app.py` (69 ln) — `run_menu(prompter, renderer) -> int`, `main()`
- `macros_screen.py` (163 ln) — list, search, show, create, delete
- `layout_screen.py` (145 ln) — regenerate, install
- `sync_screen.py` (98 ln) — pull, push
- `backups_screen.py` (80 ln) — list, restore
- `preview_screen.py` (55 ln) — generate HTML visualizer
- `venues_screen.py` (34 ln) — list venues

**Modified:**

- `src/rbxlight/cli.py` — no-args callback with `invoke_without_command=True` plus a `tui` command; both defer-import the menu at function scope
- `pyproject.toml` — added `questionary>=2.0`; `rich` deliberately left transitive via `typer>=0.12`
- `README.md` — new "Interactive menu" section

**Tests — `tests/tui/` package (62 tests across 9 files):**

- `conftest.py` — shared fixtures
- `doubles.py` — `ScriptedPrompter` (scripted answers with `CTRL_C` sentinel, records call order) and `RecordingRenderer` (records `line`/`plan`/`error`/`danger` calls)
- `test_macros_screen.py` — list, search, show, create, delete flows
- `test_layout_screen.py` — regenerate, install flows
- `test_sync_screen.py` — pull, push flows
- `test_backups_screen.py` — list, restore flows
- `test_preview_screen.py` — generate flow
- `test_venues_screen.py` — list flow
- `test_app.py` — top-level menu, back/escape, exit, Ctrl-C handling
- `test_tty.py` — non-TTY detection
- `test_real_adapters_smoke.py` — A follow-up file (4 tests) added after the initial implementation, closing a gap found when the menu was first run for real: the whole suite passed even with `questionary` not installed, because every test injects the `ScriptedPrompter`/`RecordingRenderer` doubles and `QuestionaryPrompter` defers `import questionary` into the method body. Nothing exercised the real adapters, so a missing runtime dependency surfaced as a runtime traceback rather than a test failure. The smoke tests assert that `questionary` and `rich` are importable, that the real adapters construct, and — via signature-matching reflection, since the Protocols are not `@runtime_checkable` — that `QuestionaryPrompter` and `RichRenderer` actually conform to the `Prompter` and `Renderer` Protocols, guarding against the doubles and the real adapters drifting apart.

## Key Architectural Decisions

### 1. Phase 0 extraction was required

Two things the menu needed lived only inside `cli.py`: the private `_readonly_working_copy` contextmanager (the "Run `rbxlight pull` first." guard used by every read command) and the inline 25-slot programmed/empty verdict used by `macro show`. Because the menu is forbidden to import `cli.py`, reimplementing either would have recreated the drifting-second-path problem the two prerequisite stories existed to eliminate. Both were extracted into the domain layer first: `db.WorkingCopyMissingError` (typed, typer-free, carries `.path`) and public `db.readonly_working_copy(db_name)`, with `cli._readonly_working_copy` reduced to a thin wrapper that catches it and produces the identical message; and `macros.repo.SlotStatus` + `macros.repo.get_slot_statuses(conn, macro_id)`, with `cli.macro_show` rewired to call it. The now-dead `cli._require_working_copy` was removed. All 719 tests passed unmodified through that extraction, which is the proof the CLI's observable behaviour was untouched.

### 2. `sync.build_pull_plan` had never been called by anything

The menu is its first caller. The `pull` CLI command still calls `sync.pull()` directly with no dry-run gate, because pull only ever touches the disposable working copy. No CLI change was needed.

### 3. There is no `apply_restore_plan`

Restore has no build+apply pair like the other operations — `safety.restore_from_backup(backup_dir)` re-derives everything from the backup directory itself rather than from a plan object. The menu therefore sequences restore itself: `preflight_restore` → `build_restore_plan` (for display) → typed confirmation → `restore_from_backup`.

### 4. Location constants are read at call time, never bound at import

Carried forward from the actions-layer story as the single most dangerous failure mode: an import-time binding would silently defeat the suite's monkeypatches and point the tests at the user's real, irreplaceable rekordbox data. Every reference to `db.WORK_DIR`, `db.LIGHTINGDB`, `safety.LIGHTINGDB`, `safety.BACKUP_ROOT` and the `orchestration.default_*()` accessors is resolved fresh inside the function body.

### 5. Two tiers, deliberately unequal friction

Working-copy actions (macro create/delete, layout regenerate/install, sync pull) get an ordinary `confirm(default=False)`. Live actions (sync push, backups restore) get a distinct danger rendering naming exactly which live files will be overwritten, the backup that will be taken and the exact restore command, then require a typed confirmation word. This is a direct defence against confirm-fatigue: confirming everything with equal weight trains the user to hit yes.

### 6. Structural boundaries are asserted by tests, not by convention

One test asserts the menu package never imports `rbxlight.cli`; another asserts `cli.py` keeps its menu imports at function scope only.

## Deviations from the Story

**Flat package instead of flat module.** The story's implementation notes said to create the TUI "at the same layer as `cli.py` (flat module structure per architecture skill)". It was instead created as a `menu/` package. This matches the precedent set by the preview-layout-split story: "flat module structure" means no nested sub-packages, not never-split-a-file. `menu/` sits alongside the existing `macros/`, `venues/` and `preview/` packages and contains only flat sibling modules. No skill correction was needed — the existing wording already supports this reading.

## Agents Used

| Agent | Task | Result |
| ----- | ---- | ------ |
| backend-testing-agent | 62 tests across 9 files + doubles + conftest | Complete |
| backend-agent | Implement menu package + CLI wiring | Complete |
| backend-optimizer-agent | Refactor pass | Complete |
| general-task-agent | README section | Complete |

## Files Modified

- `src/rbxlight/menu/` — new package (13 modules, 1030 lines)
- `src/rbxlight/cli.py` — no-args handler + `tui` command with defer-import
- `src/rbxlight/db.py` — `WorkingCopyMissingError`, public `readonly_working_copy`
- `src/rbxlight/macros/repo.py` — `SlotStatus`, `get_slot_statuses`
- `pyproject.toml` — added `questionary>=2.0`
- `README.md` — new "Interactive menu" section
- `tests/tui/` — new package (62 tests across 9 files + doubles + conftest)

## Tests

- **781 passing**, 0 failing (719 pre-existing + 62 new)
- All 719 pre-existing tests pass **unmodified**
- `ruff check .`, `ruff format --check .`, `mypy src/` all clean

Notable guarantees now test-locked:

- Menu package never imports `rbxlight.cli` — enforced by structural test
- `cli.py` keeps menu imports at function scope only — enforced by structural test
- Declining a confirmation leaves databases byte-identical — proven by read-before/after
- Live-write actions cannot be reached without passing the stronger gate — enforced by flow tests
- Dry-run produces a plan and mutates nothing — proven by byte-identical read
- Non-TTY refuses to start with a clear message — enforced by exception test
- Ctrl-C exits cleanly with no traceback — enforced by signal test
- Back/escape at every level returns to previous menu — enforced by flow tests

## Playbook Candidates

None reported.
