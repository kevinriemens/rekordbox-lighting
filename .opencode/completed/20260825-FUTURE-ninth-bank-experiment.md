# Ninth Bank Experiment — Tooling

**Completed:** 2026-08-25
**Epic:** FUTURE
**Source:** `.opencode/refined/FUTURE-ninth-bank-experiment.md`

## Summary

Built the tooling half of the ninth-bank experiment: `rbxlight experiment ninth-bank apply|revert`,
plus the two permanent repo modules it needed (`macros/patterns.py` for banks/phase rows,
`phrases/repo.py` for a track's bank assignment). **The experiment itself has not been run** — its
verdict is still open, because answering it requires a human physically launching rekordbox and
watching a track play. That half is recorded in `.opencode/BACKLOG.md` under "Open physical sessions".

## Plan Approved by the user

The story as refined asked for a runbook that issues raw row-level SQL directly against the live
LightingDB. Research showed that bypasses the entire safety architecture, so the plan was reshaped
and approved with one explicit deviation (see below).

### Requirements Summary

- Insert one `macro_pattern` row with `pattern = 9` and a full set of `macro_assign` phase rows
  copied from an existing factory bank, so the pattern integer is the only variable under test
- Repoint exactly one throwaway track's `content.macro_pattern_id` at the new bank
- Dry-run by default; `--write` required for any mutation
- Fully reversible regardless of verdict
- Tests never touch the live rekordbox directory, not even for reads

### Technical Approach

- Backend: two permanent repo modules (`macros/patterns.py`, `phrases/repo.py`), one disposable
  orchestration module (`experiments/ninth_bank.py`), thin CLI wiring in `cli.py`
- Frontend: none
- Database: no migrations — these are pre-existing external rekordbox tables. Test DDL for
  `macro_pattern`, `macro_assign`, and `content` was added to `tests/conftest.py` (none existed)

### Execution Order

| Phase | Agent | Task |
| ----- | ----- | ---- |
| 1 | `backend-testing-agent` | Write failing test suite defining the contract |
| 2 | `backend-agent` | Implement until green |
| 3 | `backend-optimizer-agent` | Refactor without touching the public API or tests |

## Implementation

### Backend

**`src/rbxlight/macros/patterns.py`** (new, permanent) — `MacroPattern` / `MacroAssign` frozen
dataclasses; `get_macro_pattern`, `list_macro_patterns`, `list_macro_assign`,
`next_macro_pattern_id` (derived from `MAX(id)`, never hardcoded), `create_macro_pattern`,
`clone_macro_assign` (row count follows the source bank), idempotent `delete_macro_pattern` /
`delete_macro_assign`.

**`src/rbxlight/phrases/repo.py`** (new package, permanent) — `Content` frozen dataclass,
`get_content`, `update_content_macro_pattern_id`. Deliberately performs no FK validation: 61 rows in
the live data legitimately point at a nonexistent `macro_pattern_id = 0`, so a dangling reference is
a real, tolerated state, not corruption.

**`src/rbxlight/experiments/ninth_bank.py`** (new package, disposable) — `NinthBankApplyPlan` /
`NinthBankRevertPlan` frozen plans built by zero-I/O builders; `apply_ninth_bank` /
`revert_ninth_bank`; `NinthBankState` persisted atomically (tempfile + `os.replace`) so revert
survives a shell exit; `default_state_path()` reads `db.WORK_DIR` at call time; typed exceptions
`NoSourceBankError`, `NoTargetTrackError`, `NinthBankAlreadyAppliedError`,
`CorruptNinthBankStateError`; double-apply guard checked before any write.

**`src/rbxlight/cli.py`** (modified) — `experiment` → `ninth-bank` → `apply` / `revert`. Dry-run by
default, reusing the shared `_DRY_RUN_NOTICE`. Not wired into the TUI (`menu/`), which is correct for
a disposable probe.

### Frontend

N/A.

### Deviations from Plan

**1. Working copy instead of live row-level writes (raised as a question, explicitly approved).**
The story's runbook issued `sqlite3` commands straight at
`~/Library/Application Support/Pioneer/rekordbox6/LightingDB/`. Every mutating command in this
codebase instead writes to `work/` via `safety.working_copy_write`, and is promoted to live only by a
separate deliberate `rbxlight push --write` (guard → backup → whole-file copy → sha256 verify). The
experiment now follows that path. Two consequences worth stating plainly:

- The story's Phase 0 step `rbxlight backup --trigger "..."` **does not exist** — there is no
  `backup` command. It was never needed: `push` backs up internally before touching live.
- The story's "all changes in a single transaction" requirement is **not achievable as written and is
  not implemented**. The change spans `macro.db3` and `user.db3`, and nothing in SQLite or this
  codebase gives a cross-database atomic commit. Rather than fake it, each file is written in its own
  `working_copy_write` transaction. This is safe precisely because `work/` is disposable and
  regenerable via `pull` — the atomicity that actually matters happens at `push`, which already
  handles both files together with backup and verification.

**2. Module placement, chosen by the testing agent, reviewed and accepted.** `content` accessors went
to a new `phrases/repo.py` rather than into `venues/repo.py`, because the architecture skill's "Where
to Put New Code" table already assigns track/phrase assignment to `phrases/` — this makes a documented
module real instead of overloading the venue repo. Bank access went to a new `macros/patterns.py`
rather than growing `macros/repo.py`.

**3. `apply` / `revert` sub-commands instead of a `--revert` flag.** Clearer, and revert takes no
positional arguments.

**4. New pattern id is allocated, not hardcoded.** The story specified `id = 28`. The implementation
uses `MAX(id) + 1`, which is 28 today but does not silently corrupt anything if the table changes.

**5. Phase count is read from the source bank, never assumed.** See the doc correction below for why
this mattered more than expected.

## Doc Corrections (in scope per the standing project rule)

**1. `rekordbox-lightingdb-schema/SKILL.md` — phase counts. This one was a live landmine.**
The skill claimed the `macro_assign` phase count is determined by the pattern's `energy`: "11 phases
for energy 1 (HIGH)". Verified false by direct query against the working copy: patterns 7 and 8
(CLUB1, CLUB2) have **10** phases at HIGH, not 11. Arithmetic confirms it —
`6×(11+10+6) + 2×(10+10+6) + 3×6 = 232`, the known live row count.

This is the *second* correction to the same claim. On 2026-08-23 it was corrected from a uniform
`1..11` to the energy-based rule; that fix replaced one wrong formula with another. The skill now
carries the measured per-pattern table and an explicit instruction to **read the count, never compute
it**. Directly relevant here: the story told the implementer to source phases from
`macro_pattern_id = 19` (CLUB1 HIGH) and warned against hardcoding 11 — had anyone instead trusted the
skill's formula, the experiment would have written a phantom 11th phase row into the probe bank and
quietly contaminated the very result it exists to measure.

**2. `rekordbox-lighting-architecture/SKILL.md` — the `push` write path.** The skill stated `push`
goes through `safety.write_transaction(LIVE, verify=...)`. It does not and never has: `sync.push()`
uses `shutil.copy2` per file. `safety.write_transaction` is real and tested but has **zero production
callers**. Corrected, with the distinction spelled out so the next reader does not repeat the
mistake — this stale line is what the refined story's runbook was implicitly written against.

**3. `rekordbox-lightingdb-schema/SKILL.md` — ninth-bank status.** Added a dated "VERDICT PENDING"
section recording what is already established (no name source exists for a ninth bank; 61 dangling
`macro_pattern_id` rows are tolerated in live data), the two open hypotheses, and a pointer to the
tooling. The story asked for the verdict itself to be recorded here — that cannot honestly be written
until the experiment is actually run.

**4. `rekordbox-lighting-architecture/SKILL.md` + `METADATA.md`** — added `macros/patterns.py`,
`phrases/`, and `experiments/` to both module trees and to the placement table, plus a new section
defining the `experiments/` contract: nothing permanent may import from it, reusable logic never
lives there, and it obeys the same working-copy/dry-run rules as everything else.

**5. `BACKLOG.md`** — the story left the refined table; the un-delegatable physical half was recorded
under a new "Open physical sessions" heading with the exact command sequence and the instruction to
delete `src/rbxlight/experiments/` once the verdict is recorded.

## Agents Used

| Agent | Task | Result |
| ----- | ---- | ------ |
| `deep-research-agent` ×3 (parallel) | Safety/write-path contract; CLI + orchestration + state-persistence precedent; DB test patterns | Complete — surfaced the live-write architecture mismatch that reshaped the plan |
| `backend-testing-agent` | Failing test suite defining the contract | Complete — 77 tests, failing at collection with clean `ModuleNotFoundError` |
| `backend-agent` | Implement until green | Complete — 870 passed, no test file modified |
| `backend-optimizer-agent` | Refactor within a frozen public API | Complete — extracted `_row_to_macro_pattern`, used `dataclasses.replace` in `clone_macro_assign` |

## Files Modified

- `src/rbxlight/macros/patterns.py` — new, permanent: `macro_pattern` / `macro_assign` repo
- `src/rbxlight/phrases/__init__.py`, `src/rbxlight/phrases/repo.py` — new, permanent: `content` repo
- `src/rbxlight/experiments/__init__.py`, `src/rbxlight/experiments/ninth_bank.py` — new, disposable
- `src/rbxlight/cli.py` — `experiment ninth-bank apply|revert` wiring
- `tests/conftest.py` — added `macro_pattern`/`macro_assign` to `MACRO_DB_SCHEMA`, `content` to `USER_DB_SCHEMA`
- `tests/fixtures/pattern_fixtures.py`, `tests/fixtures/content_fixtures.py` — new row factories
- `tests/macros/test_patterns.py`, `tests/phrases/`, `tests/experiments/` — new suites
- `tests/test_cli.py` — appended CLI tests, no existing test touched
- `.opencode/skills/rekordbox-lightingdb-schema/SKILL.md` — phase-count correction, ninth-bank status
- `.opencode/skills/rekordbox-lighting-architecture/SKILL.md` — `push` correction, module tree, `experiments/` contract
- `.opencode/METADATA.md` — module tree
- `.opencode/BACKLOG.md` — open physical session

## Tests

- 870 passing (77 new), 0 failing
- `mypy src/` clean across 43 files, `ruff check .` clean
- Safety invariants under test: dry-run changes zero bytes; live directory never created (tripwire);
  id allocation never hardcoded; phase count always copied from source; exactly one track repointed;
  double-apply refused; corrupt vs missing undo state handled distinctly

## Playbook Candidates

None (backend-only, no UI).

## Outstanding

The experiment's **verdict is still unknown**. The story's acceptance criteria covering Phases 0, 2,
3 and 4 — backup, observe in rekordbox, re-read, clean up — are satisfiable only by a human at the
machine. Tracked in `.opencode/BACKLOG.md` under "Open physical sessions".
