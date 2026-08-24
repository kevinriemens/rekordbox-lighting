# Extract shared orchestration layer (plans + orchestration out of cli.py)

**Completed:** 2026-08-24
**Epic:** TUI
**Source:** `.opencode/refined/TUI-extract-actions-layer.md`

## Summary

Pure refactor extracting venue resolution, layout regenerate/install orchestration and preview generation out of `cli.py` into a new typer-free `orchestration.py`, and adding four new zero-write plan objects. Unblocks `TUI-interactive-menu`, which is forbidden to import `cli.py` and would otherwise have reimplemented this logic as a second, drifting write path.

## Origin — why this story exists

`/build TUI-interactive-men` was invoked against `TUI-interactive-menu.md`. Research contradicted that story's premise: it assumed the domain layer was directly callable, but four capabilities it needs existed only as private helpers or inline command bodies in `cli.py`. Options presented were (approve extraction inside the TUI story) / (a: split it out and build first) / (b: let the TUI duplicate the orchestration — recommended against). **User chose (a).** This story was written, `TUI-interactive-menu.md` gained a `depends_on` entry plus an explicit constraint to consume this layer, and this story was built first.

## Plan Approved by the user

### Requirements Summary

- Extract venue resolution (explicit id vs active pointer vs **stale** pointer, with valid-venue enumeration on failure)
- Extract layout regenerate orchestration (generate → diff → apply prior pan/tilt calibration → save, honouring reset-structure)
- Extract layout install orchestration (load → validate venue → missing fixtures as data → diff → save)
- Extract preview generation (macro + venue → written output path)
- Add frozen zero-write plan objects for pull, restore, layout regenerate, layout install
- No user-visible behaviour change; existing tests pass unmodified

### Technical Approach

- New typer-free module; never prints, never exits — typed exceptions and return values only
- `cli.py` rewired to: parse flags → call orchestration → render
- No new write path: all writes keep going through the existing safety context managers
- No new runtime dependency

### Execution Order

| Phase | Agent | Task |
| ----- | ----- | ---- |
| 1.2 | deep-research-agent | Conflict scan across the test suite |
| 2.1 | backend-testing-agent | Orchestration + plan tests (failing) |
| 2.2 | backend-agent | Implement, rewire `cli.py` |
| 2.3 | *gate* | Backend review |
| 2.4 | backend-optimizer-agent | Refactor pass |

No frontend phase (`skip_frontend_tests: true`; visualizer untouched).

## Test Impact Analysis (refactoring story)

Conflict scan found **zero** conflicts. No test imports or calls a `cli._private_helper`, mocks internal call structure, or monkeypatches any symbol inside `rbxlight.cli`. `tests/test_cli.py` (138 tests) is pure `CliRunner` asserting stdout / exit codes / file bytes.

Three constraints were derived from the scan and passed to every agent as hard requirements:

1. `rbxlight.cli` keeps exporting `app` at its current import path
2. `rbxlight.db` and `rbxlight.safety` stay at their current locations/names
3. **Location constants must be read at call time, never bound at import time.** `from rbxlight.db import WORK_DIR` would snapshot the value and silently defeat ~23 monkeypatches, causing the suite to operate on the user's real rekordbox data instead of a sandbox. This is a data-safety constraint, not a style one.

All pre-existing tests passed unmodified — verified via `git diff --name-only -- tests/` returning empty.

## Implementation

### Backend

**New — `src/rbxlight/orchestration.py` (366 lines):**

- `VenueResolution(venue, fixtures, source)` where source is `"explicit"` | `"active_venue"`; `resolve_venue(conn, venue_id)`
- Three distinct, non-overlapping exception types, each carrying `venues` for error enumeration: `VenueNotFoundError`, `NoActiveVenueError`, `StaleActiveVenueError`
- `LayoutRegeneratePlan` + `build_layout_regenerate_plan` + `apply_layout_regenerate` (preserves pan/tilt calibration; honours reset-structure)
- `LayoutInstallPlan` + `build_layout_install_plan` (raises `LayoutVenueMismatchError`) + `apply_layout_install`
- `generate_preview(...) -> Path`
- `default_layout_dir()` / `default_backup_root()` — both read `db.WORK_DIR` / `safety.BACKUP_ROOT` at call time

**Modified:**

- `sync.py` — added `PullPlan` + `build_pull_plan` (`touches_live=False`)
- `safety.py` — added `RestorePlan` + `build_restore_plan` (`touches_live=True`)
- `cli.py` — `preview`, `restore`, `layout regenerate`, `layout install` rewired to orchestration; `_layout_path` and `_load_existing_layout` moved out; `_fail_missing_working_copy()` extracted to kill a duplicated error block

No schema changes. No new write path. No new dependency.

### Deviations from Plan

1. **Flat module instead of a package.** The story specified an `actions/` package; the implementation is a flat `src/rbxlight/orchestration.py`. Accepted — it matches the existing flat convention (`sync.py`, `safety.py`, `db.py`). Naming differs from the story text; recorded here so future readers searching for "actions layer" find it.

2. **`LayoutInstallPlan` field naming corrected mid-flight.** The test contract defined `missing_fixture_ids` as *venue fixtures absent from the incoming file*, while `cli.py`'s frozen "No longer patched into venue X" warning concerns the **opposite** direction. The first implementation preserved CLI behaviour by recomputing the second direction locally in `cli.py` — correct, but it left the plan object unable to feed the CLI's own confirmation gate, which the TUI would have hit immediately. Surfaced at the review gate; user approved carrying both directions. Resolved into two unambiguous fields:
   - `missing_from_incoming_fixture_ids` — venue fixtures the incoming file does not cover
   - `missing_from_venue_fixture_ids` — incoming entries no longer patched into the venue

   `cli.py` now reads both off the plan. This required editing one *new* test file (`tests/test_orchestration_layout.py`); no pre-existing test was touched.

3. **`cli.py` did not shrink meaningfully.** 765 → 717 lines (−48). Orchestration moved out but plan-construction moved in. Flagged to the user, who accepted. The optimizer reviewed for further extraction and declined: the remaining glue is either presentation (must stay) or coupled to `typer.echo`/`typer.confirm`, which cannot move into a typer-free module.

4. **`build_pull_plan` / `build_restore_plan` are not yet consumed by `cli.py`.** Deliberate — wiring them in would change `pull`/`restore` dry-run output, violating the byte-identical constraint. They exist for `TUI-interactive-menu`, whose acceptance criteria require a rendered plan + confirm for both.

## Agents Used

| Agent | Task | Result |
| ----- | ---- | ------ |
| deep-research-agent ×4 | Parallel research: safety/write layer, cli surface, domain API, test conventions | Complete |
| deep-research-agent | Test conflict scan | Complete — 0 conflicts |
| general-task-agent | Write this refined story (the split) | Complete |
| backend-testing-agent | 33 tests across 7 new files | Complete |
| backend-agent | Implement orchestration, rewire `cli.py` | Complete |
| backend-agent | Correct `LayoutInstallPlan` field naming | Complete |
| backend-optimizer-agent | Refactor pass | Complete |

## Files Modified

- `src/rbxlight/orchestration.py` — new orchestration layer
- `src/rbxlight/cli.py` — rewired to orchestration; helpers moved out; duplication removed
- `src/rbxlight/sync.py` — `PullPlan`, `build_pull_plan`
- `src/rbxlight/safety.py` — `RestorePlan`, `build_restore_plan`
- `tests/test_orchestration_venue.py` — new
- `tests/test_orchestration_layout.py` — new
- `tests/test_orchestration_preview.py` — new
- `tests/test_orchestration_plans_touch_nothing.py` — new
- `tests/test_orchestration_structure.py` — new
- `tests/test_sync_pull_plan.py` — new
- `tests/test_safety_restore_plan.py` — new
- `.opencode/refined/TUI-interactive-menu.md` — `depends_on` + actions-layer constraint

## Tests

- **717 passing**, 0 failing (683 pre-existing + 34 new)
- All 683 pre-existing tests pass **unmodified**
- `ruff check .`, `ruff format --check .`, `mypy src/` all clean

Notable guarantees now test-locked:

- Building any of the four new plans performs zero I/O — proven by the byte-identical `read_bytes()` idiom, not mocking
- `orchestration.py` imports neither `typer` nor `click` — enforced by an AST-based structural test
- `default_layout_dir()` / `default_backup_root()` honour redirected module globals, proving call-time (not import-time) constant binding

## Playbook Candidates

None reported (not applicable — this is a CLI tool with no `/playbook` route).
