---
epic: "TUI"
title: "Extract shared write layer (prerequisite refactor)"
estimate: M
status: ready
created: 2026-08-23
depends_on: []
labels: [refactor, safety, write-path, prerequisite]
priority: P1
claimed_by:
claimed_by_date:
---

## 1. User Story

**As a** developer building the interactive TUI\
**I want** to call the domain/repo layer directly without inheriting CLI concerns\
**So that** I can reuse the safety orchestration (guard, backup, verify, transaction) without copy-pasting or importing private CLI helpers

## 2. Business Context & Value

A decision was taken on 2026-08-23: the forthcoming interactive TUI will call the domain/repo layer DIRECTLY (not shell out to the CLI). An audit of `src/rbxlight/` confirmed the domain layer is already ready for this, but the safety/orchestration layer is not.

Today, safety sequencing (guard, backup, verify, transaction begin/commit/rollback) is scattered across `cli.py` command bodies and inlined in `sync.py`. The working-copy write contextmanager lives as a private CLI helper. Dry-run "plans" are f-strings echoed directly in command bodies, not typed values.

This story closes the gap by:
1. Completing `safety.write_transaction()` with injectable verification
2. Making `push` and `restore` use the shared sequence instead of inlining it
3. Promoting the working-copy write contextmanager to a public, shared, importable function
4. Introducing typed plan objects so a dry-run is a VALUE, not a print
5. Shrinking `cli.py` to flag parsing + rendering + exception-to-exit translation

**No new user-facing behaviour. No behaviour change at all.** This is a pure refactor that unblocks the TUI and removes duplicated safety sequencing.

## 3. Acceptance Criteria

* [ ] **`write_transaction` supports injectable verify**
    * Given a caller needs to write to a live database with full safety guarantees
    * When calling `write_transaction(db_name, trigger_command, verify=my_verify_fn)`
    * Then the contextmanager runs: guard → backup → BEGIN → yield conn → caller mutations → VERIFY (by calling `my_verify_fn(conn)`) → commit
    * And if `verify` raises, the transaction rolls back and restore instructions are printed
    * And if `verify` is omitted, a sensible default verify strategy is used (e.g., row count check)

* [ ] **`push` and `restore` use the shared sequence**
    * Given `push --write` or `restore` is called
    * When the command executes
    * Then no safety sequencing (guard, backup, verify, transaction begin/commit/rollback) appears in the command body
    * And the command delegates to `safety.write_transaction()` or a named safety function for the full orchestrated sequence
    * And the behaviour is identical to before (no user-visible change)

* [ ] **Working-copy write contextmanager is public and shared**
    * Given a caller (CLI or TUI) needs to mutate the working copy
    * When importing from `safety.py` (not `cli.py`)
    * Then a public contextmanager is available with a name that makes the working-copy/live distinction obvious at the call site
    * And the contextmanager has no guard, no backup (because it never touches live data)
    * And the behaviour is identical to the current private `_working_copy_write` (no user-visible change)

* [ ] **Typed plan objects exist and are used**
    * Given a dry-run is requested (e.g., `macro create --dry-run`)
    * When the command executes
    * Then a typed frozen dataclass (e.g., `CreatePlan`) is built without performing any write
    * And the plan is rendered by the CLI (not built as an f-string)
    * And the plan object carries the facts the CLI currently interpolates (names, ids, counts, target paths, which databases are affected, whether the operation touches live data)
    * And the dry-run is provably side-effect free (no backup, no guard, no transaction)

* [ ] **CLI shrinks to flag parsing + rendering + exception translation**
    * Given `cli.py` is reviewed
    * When examining any command body that performs a write (e.g., `macro create`, `macro delete`, `push`, `restore`)
    * Then no safety sequencing appears in the command body
    * And no plan-string construction appears (plans are built by domain functions, rendered by the CLI)
    * And exception-to-exit translation is present (domain exceptions caught and converted to clean messages + exit codes)

* [ ] **All existing tests pass without modification**
    * Given the test suite is run
    * When all tests execute
    * Then every test passes
    * And no test file is modified (this is the primary gate — if a test needs changing, behaviour changed)

* [ ] **Linting and type checking pass**
    * Given the codebase is checked
    * When running `ruff check .`, `ruff format .`, and `mypy src/`
    * Then all checks pass with no errors or warnings

* [ ] **Project metadata is corrected**
    * Given `.opencode/METADATA.md` lists the "Project File Tree Structure"
    * When the story is complete
    * Then the file tree matches reality (verified against actual disk)
    * And the `phrases/` package (which does not exist) is removed from the tree
    * And the `preview/` package (which does exist) is added to the tree
    * And the correction is noted with the date (2026-08-23)

* [ ] **Architecture skill is updated if stale**
    * Given the project skill `.opencode/skills/rekordbox-lighting-architecture/SKILL.md` documents the write path
    * When the story is complete
    * Then any documentation made stale by this refactor is updated
    * And the update is noted with the date (2026-08-23)

## 4. Technical Constraints

> ⚠️ Describe WHAT is needed, not HOW. No class names, method signatures, DTO shapes, or endpoint paths.
> The implementing agents + architecture skill decide those.

* **Safety orchestration**: The full sequence (guard → backup → BEGIN → yield → verify → commit/rollback) must be factored into reusable functions in `safety.py`, not duplicated in command bodies.
* **Verification injection**: `write_transaction` must accept an optional verify callable so that different write operations can use different verification strategies (e.g., `assert_25_rows` for macro writes, sha256/row-count for others).
* **Working-copy isolation**: The working-copy write contextmanager must be public and importable without importing `cli.py`. It must have no guard, no backup, because it never touches live data.
* **Plan objects**: Dry-run plans must be typed frozen dataclasses, not f-strings. They must be built without performing any write (provably side-effect free).
* **No behaviour change**: Every existing test must pass without modification. The user-visible output may change only where it falls out of rendering a plan object instead of an f-string (and even that should be kept byte-identical where cheap).
* **No new dependencies**: No new packages may be added.
* **No new CLI commands, no new flags**: The CLI surface remains unchanged. Only the internal orchestration is refactored.

## 5. Design & UI/UX

N/A — this is a pure refactor with no user-facing changes. Output wording may shift slightly where it falls out of rendering a plan object instead of an f-string, but should be kept byte-identical where cheap.

## 6. Scope & Context

### Audit findings (verified 2026-08-23)

- `src/rbxlight/cli.py` is 643 lines; roughly 300–350 of those are command-body orchestration: dry-run gating, `--write`/`--yes`/`--force` flag handling, exception-to-`typer.Exit` translation, "here is how to restore" text, confirm prompts, and plan/diff formatting. None of it is factored into reusable functions — it is `typer.echo`/`typer.Exit`-shaped, not return-value-shaped.
- `safety.write_transaction(db_name, trigger_command)` is a contextmanager that does guard → `backup_all` → BEGIN → yield conn → commit, or rollback + re-raise + print restore instructions. It has NO verify-by-re-read step. It is currently UNUSED by `cli.py`.
- `push` and `restore` bypass `write_transaction` entirely and hand-roll guard/backup/verify inline (`sync.push` calls `safety.guard_rekordbox_not_running`, `safety._backup_databases`, and a hand-rolled sha256 verify).
- `cli._working_copy_write()` is a PRIVATE contextmanager living in `cli.py`. It has no guard, no backup (by design — working copy only). `macro create` and `macro delete` use it. A TUI needs it too but cannot import a private CLI helper without inheriting CLI concerns.
- Dry-run "plans" for `macro create`, `macro delete`, and `push` are f-strings echoed directly in the command body. There is no plan object. `layout` is the one exception: `preview_layout.diff_layouts(old, new) -> tuple[LayoutDiffEntry, ...]` already returns a typed renderable diff (`LayoutDiffEntry` has `fixture_id`, `label`, `old_x/y/rotation`, `new_x/y/rotation`).
- The repo/domain layer is already clean and needs NO changes: `macros/repo.py` (144 lines: `get_macro`, `list_macro_data`, `create_macro`, `update_macro_data`, `delete_macro`), `venues/repo.py` (100 lines: `get_venue`, `list_fixtures`, `get_exec_venue_id`, `list_venues_with_fixture_counts`), `preview/layout.py`, `preview/payload.py`, `preview/document.py`. All take/return typed dataclasses, raise domain exceptions, and contain zero typer/print/sys.exit.
- `safety.py` public surface today: `RekordboxRunningError`, `BackupCorruptedError`, `guard_rekordbox_not_running()`, `backup_all(trigger_command) -> Path`, `verify_backup_integrity(backup_dir)`, `restore_from_backup(backup_dir)`, `BackupInfo` dataclass, `list_backups() -> list[BackupInfo]`, `connect_readonly(db_name)`, `assert_25_rows(conn, macro_id)`, `write_transaction(db_name, trigger_command)`.
- The write model is two-tier and this must be preserved and made explicit: `macro create/delete` and `layout regenerate/install` mutate only a DISPOSABLE WORKING COPY. `push --write` is the ONLY command that writes the live rekordbox databases. `restore` also touches live files. `pull` refreshes the working copy from live (read of live only).

### Existing behaviour affected

- `cli.py` command bodies will shrink; safety sequencing moves to `safety.py`.
- `push` and `restore` will use `safety.write_transaction()` or a named safety function instead of inlining guard/backup/verify.
- The working-copy write contextmanager becomes public and importable from `safety.py`.
- Dry-run plans become typed objects instead of f-strings (output may shift slightly but should be kept byte-identical where cheap).

### Domain rules and edge cases

- **Two-tier write model**: Working-copy writes (macro create/delete, layout regenerate/install) are disposable and never guarded/backed-up. Live writes (push, restore) are guarded, backed-up, verified, and transactional. This distinction must be obvious at the call site.
- **Verification strategies**: Different write operations need different verification (e.g., `assert_25_rows` for macro writes, sha256/row-count for push, file-existence check for restore). Verification must be injectable.
- **Restore is file-based**: `restore` copies files rather than running SQL, so it cannot use `write_transaction` directly. Its guard→verify→copy→verify sequence must be factored into a named function in `safety.py`.
- **Plan objects are domain-specific**: A plan carries the facts needed for a dry-run (names, ids, counts, target paths, which databases are affected, whether the operation touches live data). It is not a generic "operation" object.

### Known pitfalls

- **Behaviour must not change**: Every existing test must pass without modification. If a test needs changing, that is a signal behaviour changed — escalate rather than edit the test.
- **Private helpers are a trap**: The current `_working_copy_write` in `cli.py` is private, so the TUI cannot import it without inheriting CLI concerns. Making it public and shared is the fix.
- **Safety sequencing is scattered**: Guard, backup, verify, and transaction logic is spread across `cli.py` and `sync.py`. Centralizing it in `safety.py` is the goal.
- **Plans are not strings**: Dry-run "plans" today are f-strings echoed directly. They must become typed objects so that a dry-run is a VALUE, not a print.

## 7. Test Impact Analysis

### Existing tests affected by this change

| Test File | Test Method | What it asserts | Conflicts? | Action |
|-----------|------------|-----------------|------------|--------|
| `tests/safety/test_write_transaction.py` | (various) | Existing `write_transaction` behavior (guard, backup, commit/rollback) | NO | Keep unchanged; new verify injection will be tested separately |
| `tests/sync/test_push.py` | (various) | Existing `push` behavior (guard, backup, verify, commit) | NO | Keep unchanged; refactored `push` will use shared sequence but behaviour is identical |
| `tests/sync/test_restore.py` | (various) | Existing `restore` behavior (guard, backup, verify, file copy) | NO | Keep unchanged; refactored `restore` will use shared sequence but behaviour is identical |
| `tests/cli/test_macro_create.py` | (various) | Existing `macro create` behavior (dry-run, working-copy write, confirm prompt) | NO | Keep unchanged; refactored CLI will use shared contextmanager but behaviour is identical |
| `tests/cli/test_macro_delete.py` | (various) | Existing `macro delete` behavior (dry-run, working-copy write, confirm prompt) | NO | Keep unchanged; refactored CLI will use shared contextmanager but behaviour is identical |
| `tests/cli/test_push.py` | (various) | Existing `push` CLI behavior (dry-run, confirm prompt, exit codes) | NO | Keep unchanged; refactored CLI will render plan objects but behaviour is identical |
| `tests/cli/test_restore.py` | (various) | Existing `restore` CLI behavior (confirm prompt, exit codes) | NO | Keep unchanged; refactored CLI will use shared sequence but behaviour is identical |

### Test modification policy

- [ ] No existing tests should be modified (this is the primary gate)
- [ ] New tests will be added under `tests/safety/` to cover:
  - `write_transaction` runs the injected verify and ROLLS BACK when verify raises
  - `write_transaction` uses a sensible default verify if none is provided
  - The working-copy contextmanager does NOT trigger a backup or a process guard
  - The live-write path refuses to proceed when the rekordbox process guard trips
- [ ] New tests will be added under `tests/models/` (or equivalent) to cover:
  - Plan objects are built without performing any write (a dry-run must be provably side-effect free)
  - Plan objects carry the expected facts (names, ids, counts, target paths, which databases are affected, whether the operation touches live data)
- [ ] Test scenarios will be described in prose/Given-When-Then format; test function names will be decided by the implementing agents
- [ ] Tests must never touch anything under `~/Library/Application Support/Pioneer/rekordbox6/` — only throwaway SQLite DBs in `tmp_path` per the existing `tests/conftest.py` pattern

### Existing files impacted (refactoring only)

| File | Impact |
|------|--------|
| `src/rbxlight/safety.py` | `write_transaction` completed with injectable verify; new public working-copy contextmanager added; new named function for restore guard→verify→copy→verify sequence (if needed) |
| `src/rbxlight/cli.py` | Safety sequencing removed from command bodies; plan-string construction replaced with plan object rendering; exception-to-exit translation preserved |
| `src/rbxlight/sync.py` | `push` and `restore` refactored to use shared safety functions instead of inlining guard/backup/verify |
| `src/rbxlight/models.py` (or equivalent) | New typed frozen dataclasses for plans (e.g., `CreatePlan`, `DeletePlan`, `PushPlan`) added |
| `.opencode/METADATA.md` | "Project File Tree Structure" corrected: `phrases/` package removed, `preview/` package added, date noted |
| `.opencode/skills/rekordbox-lighting-architecture/SKILL.md` | Write path documentation updated if made stale by this refactor, date noted |

---

## Implementation Notes for Agents

### For the backend agent (safety layer)

1. Complete `write_transaction(db_name, trigger_command, verify=None)` so it:
   - Runs guard → backup → BEGIN → yield conn → caller mutations → VERIFY → commit
   - Accepts an optional `verify` callable receiving the connection
   - Uses a sensible default verify if none is provided (e.g., row count check)
   - Rolls back and prints restore instructions if verify raises

2. Promote `_working_copy_write` from `cli.py` to a public contextmanager in `safety.py` with a name that makes the working-copy/live distinction obvious (e.g., `working_copy_write_transaction`).

3. If `restore` cannot use `write_transaction` directly (because it copies files rather than running SQL), factor its guard→verify→copy→verify sequence into a named function in `safety.py` and have the CLI call that.

### For the backend agent (sync layer)

1. Refactor `push` to use `safety.write_transaction()` with an appropriate verify callable instead of inlining guard/backup/verify.

2. Refactor `restore` to use the shared safety function (either `write_transaction` or a named restore function) instead of inlining guard/backup/verify.

### For the backend agent (models layer)

1. Add typed frozen dataclasses for plans (e.g., `CreatePlan`, `DeletePlan`, `PushPlan`) carrying the facts needed for a dry-run:
   - Names, ids, counts, target paths
   - Which databases are affected
   - Whether the operation touches live data
   - Any other facts the CLI currently interpolates into f-strings

2. Decide with the architecture skill where these live; `models.py` is the existing home for dataclasses but a plan is arguably domain-specific — prefer whichever keeps the flat-module rule intact and does not create a new module for three dataclasses.

### For the CLI agent

1. Refactor command bodies to:
   - Build a plan (pure, no writes)
   - Render the plan (for dry-run or confirm prompt)
   - Execute the plan (if confirmed)

2. Remove all safety sequencing (guard, backup, verify, transaction begin/commit/rollback) from command bodies.

3. Remove all plan-string construction (f-strings) and replace with plan object rendering.

4. Keep exception-to-exit translation (domain exceptions caught and converted to clean messages + exit codes).

### For the documentation agent

1. Verify `.opencode/METADATA.md` "Project File Tree Structure" against reality:
   - Remove `phrases/` package (does not exist)
   - Add `preview/` package (does exist)
   - Verify all other listed paths

2. Note the correction with the date (2026-08-23).

3. If `.opencode/skills/rekordbox-lighting-architecture/SKILL.md` documents the write path in a way this refactor makes stale, update it and note the date.

### Skills the implementing agents MUST load

- `rekordbox-data-safety` (MANDATORY)
- `rekordbox-lighting-architecture`
- `python-standards`
- `test-behaviour`
