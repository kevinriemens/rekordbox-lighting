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

## Follow-up, same day: the target track became optional

After the tooling shipped, the user reframed the experiment:

> "Adding another bank does not necessarily mean assigning it to a track. Its goal should just be
> that I CAN assign it to a track myself and then run that. So the goal of this ninth bank experiment
> is to verify IF I can assign that and if it's selectable from the menu."

This is a better experiment than the story specified, on three counts. If the bank is not selectable
in the UI, a forced assignment proves little. If it *is* selectable, the user assigns it and
rekordbox writes the `content` row itself — stronger evidence than an external write, because it
proves the round trip. And it removes the riskiest write entirely: `content` holds 2966 rows of
irreplaceable user work, and the bank-only path never opens `user.db3`.

It also dissolved a real problem. `content` has no track title (`song_id` points into the encrypted
`master.db`) and no bank has exactly one track, so no track is identifiable from the working copy. I
had written the user a diff-based procedure to identify a throwaway track. That procedure is now
unnecessary.

**Change:** the target track went from a required argument to an optional one, and omitting it is the
default. The capability now has two shapes:

| Stage | Writes | Question |
|---|---|---|
| 1 — bank only (default) | `macro.db3` only: +1 `macro_pattern`, +N `macro_assign` | Does bank 9 appear in the mood selector, and can I assign it myself? |
| 2 — forced repoint (opt-in) | + `user.db3`: 1 `content` row | Only if stage 1 fails: does it still play when assigned programmatically? |

Stage 2 was kept rather than deleted because `rbxlight` writes assignments directly, so
UI-selectability is not strictly required for the bank to be usable — if bank 9 is unreachable in the
UI but plays when assigned from the tool, that is still a usable ninth bank.

**Implementation:** `content_id` and `original_macro_pattern_id` became `int | None` across
`NinthBankApplyPlan`, `NinthBankState`, and both plan builders. `apply_ninth_bank` opens the
`user.db3` transaction only when a track was supplied; `cli.py` does not even open a read connection
to it otherwise. `revert` always removes the bank and restores a track only if one was recorded. A
state file recording no track is valid; one recording only *one* of the two track fields is corrupt
and raises the existing typed error.

Tested as a refactoring: existing ninth-bank tests were split into with-track and bank-only shapes,
with a byte-identical-`user.db3` assertion and a spy proving `safety.working_copy_write` is never
called with `"user.db3"` on the default path. **915 tests, mypy clean, ruff clean.**

**One test defect caught at the gate.** The testing agent wrote a success-path test asserting both
`exit_code == 0` and `assert_no_unhandled_exception(result)`. That helper asserts
`isinstance(result.exception, SystemExit)`, which is only true for a *nonzero* exit — its own
docstring says so. The pair is unsatisfiable for any successful command in this codebase. The backend
agent correctly escalated instead of editing a frozen test; the assertion was dropped in a scoped
testing pass. All 41 other call sites were checked and are correct.

## The experiment was run, same day. VERDICT: NO

The user ran stage 1 and reported: *"The extra bank does not appear. Not in performance mode, nor in
Macro mapping mode"* and *"Nothing is broken. Everything looks normal. Just like nothing every
happened. I can just see the regular banks"*.

**Method.** A probe bank `(id=28, energy=1, pattern=9)` plus 10 `macro_assign` rows cloned from bank
19 (CLUB1 HIGH — existing factory macros, so macro content was held constant and the pattern integer
was the only variable) was pushed live. No track was repointed; `content` was never written.
rekordbox was launched, inspected, and quit.

**Finding 1 — invisible. The blocking one.** Bank 9 appeared nowhere. The mood/bank selector is a
fixed 8-button surface, so an unknown `pattern` value has no way in and can never be selected or
assigned by hand. This confirms the story's first predicted failure mode. It is independent of the
missing name: there is no name column anywhere, so a ninth bank has no label source either.

**Finding 2 — not pruned. The reusable one.** The story's second predicted failure mode is refuted.
Verified forensically from the backups `push` takes automatically: the snapshot immediately preceding
the revert push — i.e. live *after* rekordbox had read it — still held row 28 with all 10
`macro_assign` rows, phases 1–10, `macro_id`s `201,201,202,203,204,205,205,206,207,207`,
byte-identical to the source bank. `MacroVersionNum` (1061) and `DbVersionNum` (1854) unchanged.
Both pushes passed the rekordbox-not-running guard, so the observation window is bracketed by
verified-quit states. rekordbox did not reject, rewrite, renumber, or repair anything — it simply
never looked.

**The durable result: storage tolerates unknown rows; the UI is the hard limit.** rekordbox ignores
what it does not recognise rather than repairing it, which matches the 61 `content` rows that have
long pointed at the nonexistent `macro_pattern_id = 0`. So for bank and venue work, the risk worth
testing is whether rekordbox will *display* a thing — not whether the data will *survive*.

**Stage 2 was deliberately skipped.** A bank that can never be reached from the CDJs mid-set is not
worth having, and `FUTURE-bank-takeover-first-pass` delivers the same practical outcome on a bank
that is already labelled and already selectable, with `initial_macro_id` giving a free revert.

**Post-run state.** The DB was reverted and verified back to baseline: 27 `macro_pattern` rows, 232
`macro_assign` rows, 2966 `content` rows, the 61 pre-existing orphans unchanged, undo state file
gone.

**Cleanup performed.** `src/rbxlight/experiments/` and `tests/experiments/` were deleted along with
the `experiment ninth-bank` CLI wiring — the module was disposable by contract and its job is done.
Suite went 915 → **821 passing**, mypy and ruff clean. The permanent modules the probe was built on,
`macros/patterns.py` and `phrases/repo.py`, remain and are what
`FUTURE-bank-takeover-first-pass` will build on.

**Docs updated with the verdict:** `docs/PROJECT-FOUNDATION.md` (§5.8 and §5.9 added to "Assumptions
that were wrong"; new §6.2 "The ninth bank probe — storage tolerates, the UI decides"; two new §9
working agreements — "Read the value, don't derive it" and "A bounded experiment that returns NO is a
success"), `rekordbox-lightingdb-schema/SKILL.md` ("VERDICT PENDING" replaced with "ANSWERED: NO"),
`.opencode/BACKLOG.md` (item closed; the stale `pull --write` erratum corrected — `pull` takes no
flag), `.opencode/METADATA.md` and `rekordbox-lighting-architecture/SKILL.md` (`experiments/` marked
as not-currently-present, contract retained).

**The story succeeded.** It was written to return a documented YES or NO, and it returned NO — closing
a speculative item permanently rather than leaving it to resurface, and yielding one durable rule
about rekordbox's behaviour on the way.
