# Extract Shared Write Layer

**Completed:** 2026-08-24
**Epic:** TUI
**Source:** `.opencode/refined/TUI-extract-shared-write-layer.md`

## Summary

Pure refactor, no behaviour change. Consolidated all DB write sequencing into named `safety.py` functions, made the working-copy-vs-live distinction explicit at the call site, and replaced inline dry-run f-strings with typed frozen plan objects that provably perform no writes. Unblocks a future interactive TUI that calls the domain layer directly instead of shelling out to the CLI.

## Plan Approved by the user

### Requirements Summary

- `write_transaction` gains an injectable `verify` hook, run inside the open transaction before commit.
- Guard/backup/verify sequencing removed from CLI command bodies into named safety functions.
- Working-copy write contextmanager promoted from private `cli._working_copy_write` to public.
- Typed frozen dataclass plan objects for create/delete/push, built without any write.
- All existing tests pass without modification (primary gate).
- ruff + mypy clean.
- METADATA file tree and architecture skill corrected.

### Technical Approach

- Backend only (`skip_frontend_tests=true`). No new deps, no new CLI commands or flags, no schema changes.
- Test impact: zero conflicts found in Phase 1.2 scan — no test referenced any private name, and all output assertions were substring checks. 23 new tests added.

### Execution Order

| Phase | Agent | Task |
| ----- | ----- | ---- |
| 1 | backend-testing-agent | Write failing tests for verify injection, working-copy ctxmgr, plan objects |
| 2 | backend-agent | Implement to pass |
| 3 | backend-optimizer-agent | Refactor cli.py |
| 4 | general-task-agent | METADATA + architecture skill docs |

## Implementation

### Backend

- `safety.write_transaction(db_name, trigger_command, verify=None)` — live write ctxmgr: guard → `backup_all` → connect+BEGIN → yield → `verify(conn)` inside the txn → commit; on exception rollback + print restore instructions + re-raise.
- `safety.working_copy_write(db_name)` — promoted public from `cli._working_copy_write`. Deliberately no guard, no backup; never touches live.
- `safety.backup_live_databases(...)` — public wrapper over the former private `_backup_databases`; `sync.push` no longer reaches into a private.
- `safety.preflight_restore(backup_dir)` — named guard → `verify_backup_integrity` sequence; CLI `restore` calls it instead of duplicating the sequence inline.
- `sync.PushPlan` / `sync.build_push_plan` — frozen, `touches_live=True`, raises `FileNotFoundError` when the working copy is missing.
- `macros.repo.CreateMacroPlan`/`build_create_macro_plan`, `DeleteMacroPlan`/`build_delete_macro_plan` — frozen, `touches_live=False`, delete builder raises `LookupError` for unknown ids.
- `cli.py` — renders plan objects instead of inline f-strings (following the existing `LayoutDiffEntry` precedent); 14 hand-rolled echo+`Exit(1)` pairs consolidated into `_fail()`; `macro list`/`macro search` rendering consolidated into `_echo_macro_listing()`.

### Deviations from Plan

Three story inaccuracies were found during research and accepted by the user:

1. Story claimed `restore` lives in `sync.py` inlining guard/backup/verify. No `sync.restore` exists — `safety.restore_from_backup` already did the full sequence. What was actually duplicated was a pre-flight guard + integrity check in `cli.py`, now `safety.preflight_restore`.
2. Story said `cli.py` was ~643 lines; actual was 772.
3. Story assumed `push` could route through `write_transaction`. It cannot — `write_transaction` opens a sqlite connection, `push` is a whole-file `.db3` copy. AC-2 was reinterpreted as extracting the orchestration into named safety functions.

Fourth judgement call, user-approved: `safety._default_verify` is a documented **no-op**. Several frozen tests write garbage non-SQLite bytes into DB files, so a real default check (e.g. `PRAGMA quick_check`) would fail them. AC-1 is therefore satisfied structurally — the hook always fires — with real verification passed per-call.

## Agents Used

| Agent | Task | Result |
| ----- | ---- | ------ |
| deep-research-agent ×3 | Verify story against disk (safety/sync, cli, tests) | Complete — surfaced 3 story inaccuracies |
| backend-testing-agent | 23 failing tests, 4 new files | Complete |
| backend-agent | Implementation | Complete |
| backend-optimizer-agent | cli.py cleanup | Complete |
| general-task-agent | METADATA + skill docs | Complete |

## Files Modified

- `src/rbxlight/safety.py` — verify injection, `working_copy_write`, `backup_live_databases`, `preflight_restore`
- `src/rbxlight/sync.py` — `PushPlan`, `build_push_plan`, uses public backup entry point
- `src/rbxlight/macros/repo.py` — create/delete plan dataclasses + builders
- `src/rbxlight/cli.py` — plan rendering, `_fail()`, `_echo_macro_listing()`, private ctxmgr removed
- `tests/test_working_copy_write.py` — import retarget only (single pre-authorized edit)
- `.opencode/METADATA.md` — file tree corrected (removed nonexistent `phrases/`, added `preview/`, `sync.py`, `venues/models.py`, `work/`)
- `.opencode/skills/rekordbox-lighting-architecture/SKILL.md` — write-path docs updated

## Tests

- 23 new tests (`tests/test_safety_write_verification.py`, `tests/test_working_copy_write.py`, `tests/macros/test_plans.py`, `tests/test_sync_plans.py`)
- 683 passing, 0 failing. Zero existing tests modified beyond one import retarget.
- `ruff check .`, `ruff format .`, `mypy src/` clean.

## Playbook Candidates

None reported.
