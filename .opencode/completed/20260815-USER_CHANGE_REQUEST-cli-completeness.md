# CLI completeness — sync, restore, macro delete, layout regenerate

**Completed:** 2026-08-15
**Epic:** USER_CHANGE_REQUEST
**Source:** ad-hoc request (three backlog items batched)

## Summary

Exposed the already-implemented-but-unreachable `pull` / `push` / `restore` / `macro delete` library
functions as real CLI commands, and added `layout regenerate` as the supported cure for the stale-layout
trap. Before this, `restore` — the command you reach for in a panic — required a Python one-liner.

## Plan Approved by the user

### Requirements Summary

- `rbxlight pull` — live → working copy, applies immediately (only writes the disposable working area)
- `rbxlight push [--write] [--force]` — dry run by default; `--force` bypasses the staleness check only
- `rbxlight restore [--from NAME] [--yes]` — lists backups with no name; interactive confirm rather than
  a `--write` flag, because making a user type a flag twice during a panic is worse than a prompt
- `rbxlight macro delete <id> [--write]` — dry run by default, refuses factory content
- `rbxlight layout regenerate [--venue N] [--write]` — diff first, apply on demand
- New pure helper for layout comparison; new read-only backup enumeration

### Two decisions taken at the approval gate

1. **Flag naming.** The backlog asked for `--force` on regenerate. Used `--write` instead, matching every
   other mutating command in the tool. `--force` already means something different on `push` (bypass the
   staleness check), so reusing it would have made two unrelated behaviours share one name.
2. **Regeneration is not a clean slate.** `generate_layout` emits the default 540°/270° sweep values, so a
   naive regenerate would silently wipe per-fixture pan/tilt calibration. Position and mounting rotation
   are algorithm output and get reset; sweep degrees are user-supplied hardware calibration and survive.
   This is the single most important behaviour in the command.

### Execution Order

| Phase | Agent | Task |
|---|---|---|
| 1 | backend-testing-agent | CLI command contract + pure diff helper + backup enumeration tests |
| 2 | backend-agent | Implement to pass |
| 3 | backend-testing-agent | Fix an unsatisfiable harness assertion (escalated by phase 2) |
| 4 | backend-testing-agent | Failing test for rotation-only diff reporting |
| 5 | backend-agent | Surface rotation in the diff output |
| 6 | backend-optimizer-agent | Deduplicate `cli.py` |

## Implementation

### Backend

- **`cli.py`** — five new commands. `pull`, `push`, `restore` are the only commands permitted to resolve
  live paths; everything else stays on the working copy. New `layout` sub-app.
- **`safety.py`** — `list_backups()` + `BackupInfo`. Read-only scan of the backup root, newest first.
- **`preview/layout.py`** — `diff_layouts()` + `LayoutDiffEntry`. Pure: no filesystem, no database.
  Deterministically ordered by `fixture_id` regardless of input entry order.

### Safety properties held

- `restore` guards rekordbox and verifies backup checksums **before** printing the overwrite plan or
  prompting, so a corrupt backup can never reach the confirmation.
- `layout regenerate` deliberately does **not** call `ensure_layout` — that function writes the layout file
  as a side effect of loading, which would have silently broken the dry-run guarantee. An explicit comment
  in the source records why, so a future refactor doesn't reintroduce it.
- `push --force` bypasses the staleness check only; it still guards rekordbox and still takes a backup.
- Dry-run branches are asserted inert by checksum comparison before/after, not merely by absence of error.
- No new code opens a live database read-write. All live access remains file-copy behind the guarded helpers.

### Deviations from Plan

- **`restore` takes `--from NAME` rather than a positional argument.** Matches the recovery hint already
  printed by `safety.write_transaction` on rollback (`rbxlight restore --from <dir>`), so the message a user
  is shown at the moment of failure is now literally the command they can run.
- **Extra phase for a broken assertion.** Ten tests asserted `exit_code != 0 and result.exception is None`.
  `click.testing.CliRunner` unconditionally populates `result.exception` with the `SystemExit` for any
  nonzero exit, so that combination is unreachable by construction. The implementation agent refused to edit
  a locked test and escalated instead — the correct call. Replaced with a shared
  `assert_no_unhandled_exception` helper that still fails on a genuine crash, verified by injecting one.
- **Extra phase for rotation reporting.** Caught at the backend review gate: a rotation-only change rendered
  as `(0.314, 0.194) -> (0.314, 0.194)` — the user was told something changed and shown nothing that
  differed. Output now carries `@ <rotation>` on both sides.

## Agents Used

| Agent | Task | Result |
|---|---|---|
| backend-testing-agent | CLI contract, 46 tests | Complete |
| backend-agent | Implementation | Complete, escalated one bad test rather than editing it |
| backend-testing-agent | Harness assertion fix | Complete, verified the fix still bites |
| backend-testing-agent | Rotation-diff failing test | Complete |
| backend-agent | Rotation-diff fix | Complete |
| backend-optimizer-agent | Deduplicate `cli.py` | Complete |

## Files Modified

- `src/rbxlight/cli.py` — five commands, `layout` sub-app, `_working_copy_write()` and
  `_resolve_venue_and_fixtures()` helpers extracted by the optimizer
- `src/rbxlight/safety.py` — `list_backups()`, `BackupInfo`
- `src/rbxlight/preview/layout.py` — `diff_layouts()`, `LayoutDiffEntry`
- `tests/test_cli.py`, `tests/test_safety.py`, `tests/preview/test_layout.py`

## Tests

476 passing (was 427). 49 added. `ruff check .`, `ruff format`, `mypy src/` all clean.

## Notes for next time

- The optimizer reverted one extraction it had made (a repeated `json.loads(manifest.json)` one-liner)
  after finding it grew the line count — a trivial stdlib idiom, not duplicated logic. Left `safety.py` and
  `preview/layout.py` byte-identical rather than forcing an abstraction. Correct instinct, worth keeping.
- `macro delete` needed no new domain logic: `repo.delete_macro` with its factory guard already existed and
  was already tested. The backlog entry claiming it needed writing was stale.

## Playbook Candidates

None reported. This project has no `/playbook` route (CLI tool, no component library).
