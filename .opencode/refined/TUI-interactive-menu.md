---
epic: "TUI"
title: "Interactive menu (questionary-based CLI frontend)"
estimate: L
status: ready
created: 2026-08-23
depends_on: ["CLI_COMPLETENESS-macro-discovery-commands", "TUI-extract-shared-write-layer", "TUI-extract-actions-layer"]
labels: [tui, interactive, safety, questionary, frontend]
priority: P1
claimed_by:
claimed_by_date:
---

## 1. User Story

**As a** DJ using `rbxlight`\
**I want** to navigate and execute every CLI capability through an interactive menu instead of remembering command names and flags\
**So that** I can discover features, preview changes before committing them, and have a deliberate two-step confirmation for any mutation

## 2. Business Context & Value

On 2026-08-23, four blocking decisions were answered:

1. **SCOPE**: The TUI is feature-complete parity with the CLI — every capability the CLI has is reachable from the menu, including writes.
2. **SAFETY**: Every mutating action runs as a dry-run first, renders the resulting plan, then asks an explicit YES/NO confirmation before executing for real. There is no way to skip step one.
3. **LIBRARY**: `questionary` for prompting. Rejected `textual` as a heavy dependency (a full-screen app framework with its own event loop and test harness) for a project with two runtime dependencies — and because a persistent full-screen app invites rapid-fire mutation, whereas a prompt → report → confirm loop is inherently deliberate. `questionary` adds `prompt_toolkit` + `wcwidth`. `rich` is already available transitively via `typer>=0.12` and does all rendering. Division of responsibility: questionary ASKS, rich SHOWS. Reference for feel is `mole` (https://github.com/tw93/mole), a Go tool — inspiration only, no code reuse.
4. **COUPLING**: Call the domain/repo layer directly. Do NOT wrap or shell out to the CLI. Rationale: wrapping the CLI would make the CLI a de-facto API (renaming a flag breaks the TUI, and every TUI capability must first exist as a flag), forces text parsing to render anything richer than a passthrough, and turns errors into exit codes instead of exceptions. Calling the domain layer gives typed models in and out and real exceptions — but carries the risk of becoming a SECOND WRITE PATH that silently skips safety rules. That risk is retired by the prerequisite story (`TUI-extract-shared-write-layer`).

The two-tier write model is fundamental to the UX: working-copy actions (macro create/delete, layout regenerate/install) are disposable and reversible; live actions (push, restore) are guarded, backed-up, verified, and transactional. The TUI must make this distinction visible, because confirming everything with the same weight produces confirm-fatigue and trains the user to hit yes.

## 3. Acceptance Criteria

* [ ] **Entry point: `rbxlight` with no arguments opens the menu**
    * Given `rbxlight` is invoked with no arguments
    * When the command executes
    * Then the interactive menu is displayed
    * And the CLI is not degraded or deprecated (all existing commands work as before)

* [ ] **Entry point: `rbxlight tui` opens the menu explicitly**
    * Given `rbxlight tui` is invoked
    * When the command executes
    * Then the interactive menu is displayed
    * And the behaviour is identical to `rbxlight` with no arguments

* [ ] **Entry point: `rbxlight <anything else>` behaves exactly as today**
    * Given `rbxlight macro list` or any other existing command is invoked
    * When the command executes
    * Then the CLI behaves exactly as before (the TUI does not intercept or degrade it)

* [ ] **Help is still reachable**
    * Given `rbxlight --help` is invoked
    * When the command executes
    * Then the help text is displayed (typer's default help, not the menu)
    * And the help text is accurate and complete

* [ ] **Non-TTY refuses to start**
    * Given stdout/stdin is not a TTY (piped, CI, script)
    * When the TUI is invoked
    * Then the TUI refuses to start with a clear message pointing at the CLI
    * And no control codes are emitted into the pipe
    * And no prompt hangs waiting for input

* [ ] **Top-level menu is organized by user intent, not CLI structure**
    * Given the menu is displayed
    * When the user views the top-level options
    * Then the menu is organized around what the user is trying to do (Macros, Preview, Layout, Venues, Sync, Backups, Exit)
    * And not around the CLI's command-group structure

* [ ] **Macros submenu: list**
    * Given the user selects "Macros" → "List"
    * When the submenu executes
    * Then the user is prompted to choose a scope (user macros, factory macros, all)
    * And the list is displayed (reusing the query functions from the macro-discovery story)
    * And the user can return to the menu

* [ ] **Macros submenu: search**
    * Given the user selects "Macros" → "Search"
    * When the submenu executes
    * Then the user is prompted to enter a search term
    * And the user is prompted to choose a scope (user macros, factory macros, all)
    * And matching macros are displayed
    * And the user can return to the menu

* [ ] **Macros submenu: show**
    * Given the user selects "Macros" → "Show"
    * When the submenu executes
    * Then the user is prompted to enter a macro id
    * And the macro's metadata and fixture slot summary are displayed
    * And the user can return to the menu

* [ ] **Macros submenu: create (working-copy action)**
    * Given the user selects "Macros" → "Create"
    * When the submenu executes
    * Then the user is prompted for macro name and beats
    * And a dry-run plan is built and rendered (what will be created, which working-copy database)
    * And the user is asked to confirm (default: No)
    * And on YES: the macro is created and the result is rendered; on NO: nothing is written and the menu returns

* [ ] **Macros submenu: delete (working-copy action)**
    * Given the user selects "Macros" → "Delete"
    * When the submenu executes
    * Then the user is prompted to select a macro to delete
    * And a dry-run plan is built and rendered (what will be deleted, which working-copy database)
    * And the user is asked to confirm (default: No)
    * And on YES: the macro is deleted and the result is rendered; on NO: nothing is written and the menu returns

* [ ] **Preview submenu: generate HTML visualizer**
    * Given the user selects "Preview"
    * When the submenu executes
    * Then the user is prompted to select a macro
    * And the user is prompted to select a venue
    * And the HTML visualizer is generated (reusing the existing preview layer)
    * And the output path is reported and the user is offered to open it
    * And the user can return to the menu

* [ ] **Layout submenu: regenerate (working-copy action)**
    * Given the user selects "Layout" → "Regenerate"
    * When the submenu executes
    * Then the user is prompted whether to reset structure (equivalent to `--reset-structure` flag)
    * And a dry-run plan is built and rendered (what will change, which working-copy database, the typed `LayoutDiffEntry` diff)
    * And the user is asked to confirm (default: No)
    * And on YES: the layout is regenerated and the result is rendered; on NO: nothing is written and the menu returns

* [ ] **Layout submenu: install (working-copy action)**
    * Given the user selects "Layout" → "Install"
    * When the submenu executes
    * Then the user is prompted to select a layout file
    * And a dry-run plan is built and rendered (what will change, which working-copy database, the typed diff)
    * And the user is asked to confirm (default: No)
    * And on YES: the layout is installed and the result is rendered; on NO: nothing is written and the menu returns

* [ ] **Venues submenu: list**
    * Given the user selects "Venues" → "List"
    * When the submenu executes
    * Then venues are displayed with fixture counts
    * And the user can return to the menu

* [ ] **Sync submenu: pull (read-only)**
    * Given the user selects "Sync" → "Pull"
    * When the submenu executes
    * Then a dry-run plan is built and rendered (what will be refreshed from live databases)
    * And the user is asked to confirm (default: No)
    * And on YES: the working copy is refreshed and the result is rendered; on NO: nothing is written and the menu returns

* [ ] **Sync submenu: push (live-database action)**
    * Given the user selects "Sync" → "Push"
    * When the submenu executes
    * Then a dry-run plan is built and rendered (what will be written to live databases, which files will be overwritten, the backup that will be taken)
    * And the user is shown a DISTINCT VISUAL TREATMENT and an explicit statement of which live database files will be overwritten
    * And the user is shown the exact restore command
    * And the user is asked for a STRONGER CONFIRMATION than Y/N (require typing a confirmation word, not just yes/no)
    * And on confirmation: the push is executed and the result is rendered; on refusal: nothing is written and the menu returns

* [ ] **Backups submenu: list**
    * Given the user selects "Backups" → "List"
    * When the submenu executes
    * Then existing backups are displayed (name, timestamp, trigger command)
    * And the user can return to the menu

* [ ] **Backups submenu: restore (live-database action)**
    * Given the user selects "Backups" → "Restore"
    * When the submenu executes
    * Then the user is prompted to select a backup
    * And a dry-run plan is built and rendered (which live database files will be overwritten, the backup that will be taken before restoring)
    * And the user is shown a DISTINCT VISUAL TREATMENT and an explicit statement of which live database files will be overwritten
    * And the user is asked for a STRONGER CONFIRMATION than Y/N (require typing a confirmation word)
    * And on confirmation: the restore is executed and the result is rendered; on refusal: nothing is written and the menu returns

* [ ] **Exit option**
    * Given the user selects "Exit" from the top-level menu
    * When the option is selected
    * Then the program exits cleanly with exit code 0

* [ ] **Back/escape at every level**
    * Given the user is at any submenu or prompt
    * When the user selects escape or back
    * Then the user returns to the previous menu level
    * And no action is executed

* [ ] **Ctrl-C exits cleanly**
    * Given the user presses Ctrl-C at any prompt
    * When the signal is received
    * Then the program exits cleanly with exit code 130 (or equivalent)
    * And no traceback is printed
    * And no partial write is left behind

* [ ] **Core interaction loop: dry-run → render → confirm → execute**
    * Given a mutating action is selected
    * When the user answers parameter prompts
    * Then the TUI builds and executes the DRY-RUN, producing a typed plan object
    * And `rich` renders the plan (what will change, how many rows/files, which tier, diffs for layout operations)
    * And `questionary.confirm(..., default=False)` is asked (or the stronger typed confirmation for live writes)
    * And on NO: the menu returns, having changed nothing; on YES: the real write executes through the shared safety layer, then the result is rendered

* [ ] **Dry-run is provably side-effect free**
    * Given a dry-run is executed
    * When the plan is built
    * Then no backup is taken, no guard is triggered, no transaction is opened, no database is written
    * And the plan object is a pure value, not a side effect

* [ ] **Working-copy actions are visually distinct from live actions**
    * Given the user is confirming an action
    * When the action is a working-copy mutation (macro create/delete, layout regenerate/install)
    * Then the confirmation is a normal `questionary.confirm(default=False)` with standard visual treatment
    * And when the action is a live mutation (push, restore)
    * Then the confirmation is a DISTINCT VISUAL TREATMENT with an explicit statement of which live database files will be overwritten, the backup that will be taken, the exact restore command, and a stronger confirmation than Y/N

* [ ] **Declining a confirmation leaves databases byte-identical**
    * Given the user declines a confirmation
    * When the action is not executed
    * Then the working copy and live databases are byte-identical to before the action was selected
    * And no backup is taken
    * And no partial write is left behind

* [ ] **TUI does not import cli.py**
    * Given the TUI module is reviewed
    * When examining imports
    * Then no import from `cli.py` appears
    * And the TUI calls the domain and safety layers directly

* [ ] **CLI does not import TUI beyond entrypoint wiring**
    * Given `cli.py` is reviewed
    * When examining imports
    * Then no import from the TUI module appears except in the single entrypoint wiring (the no-args handler)

* [ ] **Linting and type checking pass**
    * Given the codebase is checked
    * When running `ruff check .`, `ruff format .`, and `mypy src/`
    * Then all checks pass with no errors or warnings

* [ ] **Full test suite passes**
    * Given the test suite is run
    * When all tests execute
    * Then every test passes
    * And no test file is modified (this is the primary gate — if a test needs changing, behaviour changed)

* [ ] **README.md updated with TUI section**
    * Given the README.md is reviewed
    * When the story is complete
    * Then a new section documents the TUI: how to start it, the two-step safety model, and an explicit statement that the CLI remains the interface for scripted/unattended use
    * And the section is brief and user-focused

## 4. Technical Constraints

> ⚠️ Describe WHAT is needed, not HOW. No class names, method signatures, DTO shapes, or endpoint paths.
> The implementing agents + architecture skill decide those.

* **Questionary integration**: Use `questionary` for all prompts (select, text, path, checkbox). Do not use `textual` or any other full-screen framework.
* **Rich rendering**: Use `rich` (already available transitively via typer) for rendering plans, diffs, and results. Do not add `rich` as a direct dependency.
* **Direct domain calls**: Call the domain/repo layer directly (macros/repo.py, venues/repo.py, preview/layout.py, etc.). Do NOT wrap or shell out to the CLI.
* **Shared safety layer**: Use the typed plan objects and shared safety functions from the prerequisite story (`TUI-extract-shared-write-layer`). Do NOT hand-roll safety sequencing or backup/verify logic.
* **Shared actions layer**: Use the orchestration and plan builders from the prerequisite story (`TUI-extract-actions-layer`) for venue resolution, layout regenerate/install, preview generation, and the pull/restore plans. Do NOT reimplement these — reimplementing them recreates the second-write-path drift risk both prerequisite stories exist to eliminate.
* **Two-tier write model**: Working-copy actions use the public working-copy contextmanager (no guard, no backup). Live actions use `write_transaction` with appropriate verification. This distinction must be obvious at the call site.
* **Dry-run is side-effect free**: Dry-runs must build a plan without performing any write. No backup, no guard, no transaction.
* **Confirmations default to No**: All `questionary.confirm` calls must have `default=False`.
* **Live-write confirmations are stronger**: Push and restore require a typed confirmation (user types a word, not just yes/no). This is not optional.
* **Non-TTY detection**: Detect when stdout/stdin is not a TTY and refuse to start with a helpful message.
* **Ctrl-C handling**: Catch `KeyboardInterrupt` and exit cleanly with no traceback.
* **No new dependencies beyond questionary**: `questionary` adds `prompt_toolkit` + `wcwidth`. No other new packages.
* **No new CLI commands or flags**: The CLI surface remains unchanged. Only the entrypoint wiring changes (no-args → menu instead of help).

## 5. Design & UI/UX

### Menu structure

The top-level menu is organized by user intent, not CLI structure:

```
rbxlight — Interactive Menu
  1. Macros
  2. Preview
  3. Layout
  4. Venues
  5. Sync
  6. Backups
  7. Exit
```

### Macros submenu

```
Macros
  1. List
  2. Search
  3. Show
  4. Create
  5. Delete
  6. Back
```

### Layout submenu

```
Layout
  1. Regenerate
  2. Install
  3. Back
```

### Sync submenu

```
Sync
  1. Pull
  2. Push
  3. Back
```

### Backups submenu

```
Backups
  1. List
  2. Restore
  3. Back
```

### Confirmation patterns

**Working-copy action (normal confirmation):**
```
Macro will be created:
  Name: HIGH DROP1
  Beats: 32
  Database: working copy (reversible)

Confirm? [y/N]:
```

**Live-database action (stronger confirmation):**
```
⚠️  LIVE DATABASE WRITE

This action will overwrite:
  • ~/Library/Application Support/Pioneer/rekordbox6/master.db3
  • ~/Library/Application Support/Pioneer/rekordbox6/macro.db3

Backup will be taken:
  • /path/to/backup/2026-08-23T14-30-45Z

To restore: rbxlight restore /path/to/backup/2026-08-23T14-30-45Z

Type "yes" to confirm (or press Ctrl-C to cancel):
```

### Rendering plans

Use `rich` to render:
- What will change (names, ids, counts, target paths)
- Which tier (working copy vs live)
- For layout operations: the typed `LayoutDiffEntry` diff
- For live operations: which databases are affected, the backup that will be taken, the restore command

### Error handling

Catch domain exceptions and render clean human messages. Do not show tracebacks. Return to the menu on error.

## 6. Scope & Context

### Existing behaviour affected

- `rbxlight` with no arguments now opens the menu instead of printing help (typer's default).
- `rbxlight --help` still works and prints help (typer's default).
- All existing CLI commands work exactly as before.
- README.md gains a new section on the TUI.

### Domain rules and edge cases

- **Two-tier write model**: Working-copy writes are disposable and never guarded/backed-up. Live writes are guarded, backed-up, verified, and transactional. This distinction must be visible in the UX.
- **Confirm-fatigue**: Confirming everything with the same weight trains the user to hit yes. Working-copy actions get a normal confirmation; live actions get a distinct visual treatment and a stronger gate.
- **Dry-run is a value, not a print**: Plans are typed objects, not f-strings. A dry-run is provably side-effect free.
- **Escape at every level**: The user must be able to navigate back out of any submenu or prompt without answering a confirmation.
- **Ctrl-C is clean**: Pressing Ctrl-C at any prompt must exit cleanly with no traceback and no partial write.
- **Non-TTY is explicit**: If stdout/stdin is not a TTY, the TUI refuses to start with a message pointing at the CLI.

### Known pitfalls

- **Wrapping the CLI is a trap**: Wrapping the CLI makes it a de-facto API (renaming a flag breaks the TUI) and forces text parsing. Calling the domain layer directly is the right approach, but carries the risk of becoming a second write path that skips safety rules. The prerequisite story (`TUI-extract-shared-write-layer`) retires that risk by making the safety layer reusable.
- **Textual is too heavy**: A full-screen app framework with its own event loop and test harness is overkill for a project with two runtime dependencies. A prompt → report → confirm loop is simpler and more deliberate.
- **Questionary is thin**: Questionary is a thin wrapper around prompt_toolkit. It asks, rich shows. This division of responsibility keeps the TUI testable.
- **Plans must be side-effect free**: A dry-run that takes a backup or opens a transaction is not a dry-run. Plans must be pure values.

## 7. Test Impact Analysis

### Existing tests affected by this change

| Test File | Test Method | What it asserts | Conflicts? | Action |
|-----------|------------|-----------------|------------|--------|
| `tests/cli/test_macro_create.py` | (various) | Existing `macro create` CLI behavior | NO | Keep unchanged; TUI uses shared safety layer but CLI behavior is identical |
| `tests/cli/test_macro_delete.py` | (various) | Existing `macro delete` CLI behavior | NO | Keep unchanged; TUI uses shared safety layer but CLI behavior is identical |
| `tests/cli/test_push.py` | (various) | Existing `push` CLI behavior | NO | Keep unchanged; TUI uses shared safety layer but CLI behavior is identical |
| `tests/cli/test_restore.py` | (various) | Existing `restore` CLI behavior | NO | Keep unchanged; TUI uses shared safety layer but CLI behavior is identical |
| `tests/cli/test_layout_regenerate.py` | (various) | Existing `layout regenerate` CLI behavior | NO | Keep unchanged; TUI uses shared safety layer but CLI behavior is identical |
| `tests/cli/test_layout_install.py` | (various) | Existing `layout install` CLI behavior | NO | Keep unchanged; TUI uses shared safety layer but CLI behavior is identical |

### Test modification policy

- [ ] No existing tests should be modified (greenfield for the TUI)
- [ ] New tests will be added under `tests/tui/` to cover:
  - **Interaction layer** (without questionary): action layer (build plan → render → execute) is unit-testable by injecting answers
  - **Declining a confirmation performs no write**: working-copy and live databases are byte-identical after declining
  - **Live-write actions cannot be reached without passing the stronger gate**: the typed confirmation is required
  - **Dry-run produces a plan and mutates nothing**: no backup, no guard, no transaction, no database write
  - **Non-TTY refuses to start**: a clear message is printed, no prompt hangs, no control codes are emitted
  - **Ctrl-C exits cleanly**: no traceback, no partial write
  - **Back/escape at every level**: the user can navigate back without answering a confirmation
- [ ] Test scenarios will be described in prose/Given-When-Then format; test function names will be decided by the implementing agents
- [ ] Tests must never touch anything under `~/Library/Application Support/Pioneer/rekordbox6/` — only throwaway SQLite DBs in `tmp_path` per `tests/conftest.py`
- [ ] Tests must NOT drive real terminal input (questionary is mocked or injected)

### Existing files impacted (greenfield)

| File | Impact |
|------|--------|
| `src/rbxlight/cli.py` | Entrypoint wiring added: no-args handler calls TUI; `--help` still works |
| `README.md` | New section on the TUI: how to start it, the two-step safety model, explicit statement that CLI remains the interface for scripted/unattended use |

---

## Implementation Notes for Agents

### For the backend agent (TUI layer)

1. Create the TUI module at the same layer as `cli.py` (flat module structure per architecture skill).

2. Implement the menu structure:
   - Top-level menu (Macros, Preview, Layout, Venues, Sync, Backups, Exit)
   - Submenus for each section
   - Back/escape option at every level

3. Implement the core interaction loop for each mutating action:
   - Prompt for parameters (using questionary)
   - Build a dry-run plan (pure, no writes)
   - Render the plan (using rich)
   - Ask for confirmation (questionary.confirm for working-copy, typed confirmation for live)
   - Execute the real write (using shared safety layer) or return to menu

4. Implement non-TTY detection and refuse to start with a helpful message.

5. Implement Ctrl-C handling to exit cleanly with no traceback.

6. Call the domain/repo layer directly (macros/repo.py, venues/repo.py, preview/layout.py, etc.). Do NOT import cli.py.

7. Use the typed plan objects and shared safety functions from the prerequisite story.

### For the CLI agent

1. Add entrypoint wiring in `cli.py`:
   - When `rbxlight` is invoked with no arguments, call the TUI
   - When `rbxlight tui` is invoked, call the TUI
   - When `rbxlight --help` is invoked, print help (typer's default)
   - All other commands work exactly as before

2. Do NOT import the TUI module except in the single entrypoint wiring.

### For the documentation agent

1. Add a new section to README.md on the TUI:
   - How to start it (`rbxlight` or `rbxlight tui`)
   - The two-step safety model (dry-run → render → confirm → execute)
   - Explicit statement that the CLI remains the interface for scripted/unattended use
   - Keep it brief and user-focused

### Skills the implementing agents MUST load

- `rekordbox-data-safety` (MANDATORY)
- `rekordbox-lighting-architecture`
- `python-standards`
- `test-behaviour`
- `ux-patterns`

