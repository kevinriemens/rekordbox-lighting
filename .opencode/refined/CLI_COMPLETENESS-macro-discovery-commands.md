---
epic: "CLI completeness"
title: "Macro discovery commands (list, search, show)"
estimate: M
status: ready
created: 2026-08-23
depends_on: []
labels: [cli, macros, read-only, discovery]
priority: P2
claimed_by:
claimed_by_date:
---

## 1. User Story

**As a** DJ using `rbxlight`\
**I want** to discover and inspect macros via CLI commands instead of raw Python one-liners\
**So that** I can find my own macros, search factory macros by name, and view macro details without leaving the CLI

## 2. Business Context & Value

The README.md "## Finding things" section (lines 163–197) currently instructs users to run raw `python3 -c` one-liners to answer basic questions:
- List your own macros
- Search factory macros by name
- List venues (already obsolete — `rbxlight venue list` shipped 2026-08-15)

This defeats the purpose of a CLI: the documentation tells you to bypass it. Additionally, the venue snippet is stale and must be deleted.

Three new read-only commands will replace these snippets, making macro discovery discoverable via `rbxlight --help` and consistent with the existing `rbxlight venue list` pattern. This also unblocks the TUI epic, which will import these query functions directly without shelling out to the CLI.

## 3. Acceptance Criteria

* [ ] **`rbxlight macro list` — list user macros by default**
    * Given the working copy exists and the user has authored at least one macro (preset=0)
    * When running `rbxlight macro list`
    * Then output a header line "Macros:" followed by one line per macro showing id, name, and beats; exit 0
    * And the output is deterministically ordered by macro id (ascending)

* [ ] **`rbxlight macro list` — empty case**
    * Given the working copy exists and the user has authored no macros (preset=0 returns nothing)
    * When running `rbxlight macro list`
    * Then output "No macros found." and exit 0 (not an error)

* [ ] **`rbxlight macro list --all` — show all macros (user + factory)**
    * Given the working copy exists
    * When running `rbxlight macro list --all`
    * Then output all macros (preset=0 and preset=1) in deterministic order by id; exit 0

* [ ] **`rbxlight macro list --factory` — show factory macros only**
    * Given the working copy exists
    * When running `rbxlight macro list --factory`
    * Then output only factory macros (preset=1) in deterministic order by id; exit 0

* [ ] **`rbxlight macro search <term>` — search factory macros by default**
    * Given the working copy exists and at least one factory macro's name contains the search term (case-insensitive substring match)
    * When running `rbxlight macro search CHORUS`
    * Then output a header line "Search results:" followed by one line per matching macro showing id, name, and beats; exit 0
    * And results are deterministically ordered by macro id (ascending)

* [ ] **`rbxlight macro search <term>` — no matches**
    * Given the working copy exists and no factory macro's name contains the search term
    * When running `rbxlight macro search NONEXISTENT`
    * Then output "No macros found." and exit 0 (not an error)

* [ ] **`rbxlight macro search <term>` — search user macros with flag**
    * Given the working copy exists and at least one user macro's name contains the search term
    * When running `rbxlight macro search MYNAME --user`
    * Then output only user macros (preset=0) matching the term; exit 0

* [ ] **`rbxlight macro search <term>` — search all macros with flag**
    * Given the working copy exists
    * When running `rbxlight macro search TERM --all`
    * Then output all macros (preset=0 and preset=1) matching the term; exit 0

* [ ] **`rbxlight macro search <term>` — SQL LIKE wildcards are escaped**
    * Given the working copy exists
    * When running `rbxlight macro search %TERM_` (a term containing SQL LIKE wildcards)
    * Then the `%` and `_` are treated as literal characters, not SQL wildcards; exit 0
    * And the search matches only macros whose names literally contain `%TERM_`

* [ ] **`rbxlight macro show <id>` — detail view of a user macro**
    * Given the working copy exists and macro id 10006 is a user macro (preset=0)
    * When running `rbxlight macro show 10006`
    * Then output the macro's metadata (id, name, beats, preset, enabled) followed by a summary of which of the 25 fixture slots carry programming vs. are empty; exit 0
    * And the summary shows each slot id and a brief indicator (e.g., "programmed" or "empty") for every slot, even if all are empty

* [ ] **`rbxlight macro show <id>` — detail view of a factory macro**
    * Given the working copy exists and macro id 42 is a factory macro (preset=1)
    * When running `rbxlight macro show 42`
    * Then output the macro's metadata and slot summary; exit 0
    * And the command succeeds (factory macros are read-only, not forbidden)

* [ ] **`rbxlight macro show <id>` — unknown id**
    * Given the working copy exists and macro id 99999 does not exist
    * When running `rbxlight macro show 99999`
    * Then output a clean human message (e.g., "Macro 99999 not found.") and exit 1
    * And no Python traceback is shown

* [ ] **`rbxlight macro show <id> --yaml` — full YAML export**
    * Given the working copy exists and macro id 10006 exists
    * When running `rbxlight macro show 10006 --yaml`
    * Then output the full YAML export (name, beats, and all 25 fixture slots with their XML payloads); exit 0
    * And the output is identical to what `export_macro_yaml` produces

* [ ] **Working copy missing**
    * Given `work/macro.db3` does not exist
    * When running any of the three commands
    * Then output "Working copy not found at {path}. Run `rbxlight pull` first." and exit 1
    * And the existing pull guard is reused (no new guard logic)

* [ ] **README.md updated — "Finding things" section replaced**
    * Given the README.md currently contains three `python3 -c` snippets (lines 163–197)
    * When the story is complete
    * Then the "## Finding things" section is rewritten to use the three new commands instead
    * And no `python3 -c` snippet remains anywhere in README.md
    * And the venue snippet is deleted (replaced by reference to the already-existing `rbxlight venue list`)

* [ ] **README.md updated — "Everyday commands" table extended**
    * Given the README.md "## Everyday commands" table (lines 143–157)
    * When the story is complete
    * Then the table includes rows for the three new commands (e.g., "List my macros" → `rbxlight macro list`)
    * And the table remains concise and user-focused

## 4. Technical Constraints

* **Query layer**: All macro listing and search logic must live in `src/rbxlight/macros/repo.py`, not in `cli.py`. The CLI may only format and print. This is non-negotiable for TUI reuse.
* **Reuse existing functions**: `get_macro(conn, macro_id)` and `list_macro_data(conn, macro_id)` already exist in `repo.py` and must be reused for `show`.
* **Reuse existing export**: `export_macro_yaml(conn, macro_id)` already exists in `src/rbxlight/macros/yaml_io.py` and must be reused for `show --yaml`.
* **Reuse existing pattern**: The venue listing query (`list_venues_with_fixture_counts`) establishes the pattern: a single deterministic SQL query returning a list of dataclass instances, no N+1 queries.
* **No new dependencies**: No table-rendering library (rich, tabulate) may be added. Output is plain `typer.echo` with a small private line-formatter helper.
* **Read-only**: These commands never write to any database. No backup, no process guard, no `--write` flag, no dry-run.
* **No machine-readable output**: No `--json` flag or other output formats. Default output is human-readable plain lines, optimized for reading. The TUI will import the query functions directly.
* **Error handling**: Domain exceptions (e.g., `LookupError` from `get_macro`) must be caught in the CLI layer and converted to clean human messages + exit 1. No tracebacks.

## 5. Design & UI/UX

### Flag naming and consistency

**Decision required**: Choose one coherent flag scheme for scope across `list` and `search`.

**Recommended scheme** (consistent with `venue list` pattern):
- `rbxlight macro list` — user macros only (preset=0) [default]
- `rbxlight macro list --all` — all macros (preset=0 and preset=1)
- `rbxlight macro list --factory` — factory macros only (preset=1)
- `rbxlight macro search <term>` — factory macros only (preset=1) [default, because searching by name is how you find a factory macro]
- `rbxlight macro search <term> --user` — user macros only (preset=0)
- `rbxlight macro search <term> --all` — all macros (preset=0 and preset=1)

This reflects the user's intent: `list` defaults to "my stuff" (user macros), `search` defaults to "find factory content" (factory macros).

### Output format

**`macro list` and `macro search` output:**
```
Macros:
  10006: HIGH DROP1 (32 beats)
  10007: FADE IN (16 beats)
```

**`macro show` output (default):**
```
Macro 10006: HIGH DROP1
  Beats: 32
  Preset: user (0)
  Enabled: yes (1)
  Fixture slots:
    1: programmed
    2: programmed
    3: empty
    4: empty
    5: programmed
    ...
    25: empty
```

**`macro show --yaml` output:**
```
name: HIGH DROP1
beats: 32
fixtures:
  1: |
    <?xml version="1.0" encoding="UTF-8"?>
    <LightingEditModel ver="1.0">...</LightingEditModel>
  2: |
    ...
  3: ""
  ...
```

**Empty-result messages:**
- `macro list`: "No macros found."
- `macro search`: "No macros found."
- `macro show <unknown>`: "Macro 99999 not found."

## 6. Scope & Context

### Existing behavior affected

- README.md "## Finding things" section (lines 163–197) will be rewritten and the three `python3 -c` snippets deleted.
- The venue snippet in that section is already obsolete (replaced by `rbxlight venue list` shipped 2026-08-15) and will be removed.
- README.md "## Everyday commands" table will gain three new rows.

### Domain rules and edge cases

- **Macro preset convention**: preset=0 is user-authored, preset=1 is factory. Factory macros are immutable (writes are guarded), but reads are allowed.
- **The 25-row invariant**: Every macro has exactly 25 macro_data rows (one per fixture slot), even if all are empty. `list_macro_data` already filters to the 25 known slots and tolerates older 19-row and anomalous 150-row formats.
- **Deterministic ordering**: All queries must order by macro id (ascending) to ensure consistent output across runs.
- **SQL LIKE wildcards**: The `%` and `_` characters in a search term must be escaped as literals (e.g., `LIKE '%\%%' ESCAPE '\'`) to prevent accidental wildcard matching. This is a footgun if left unescaped.
- **Empty slot summary**: A macro with all 25 slots empty must still show the summary (not print nothing), stating "empty" for each slot.

### Known pitfalls

- **N+1 queries**: Do not fetch macro metadata and then loop to fetch macro_data per macro. Use a single query (or a single query per scope) like `list_venues_with_fixture_counts` does.
- **Stale README snippets**: The venue snippet is already obsolete. Verify it is deleted, not reimplemented.
- **Traceback leakage**: `get_macro` raises `LookupError` if the id doesn't exist. The CLI must catch this and convert it to a clean message, not let the traceback surface.

## 7. Test Impact Analysis

### Existing tests affected by this change

| Test File | Test Method | What it asserts | Conflicts? | Action |
|-----------|------------|-----------------|------------|--------|
| `tests/macros/test_repo.py` | (various) | Existing `get_macro`, `list_macro_data`, `create_macro`, `delete_macro` behavior | NO | Keep unchanged; new listing query will be tested separately |
| `tests/macros/test_yaml_io.py` | (various) | Existing `export_macro_yaml`, `import_macro_yaml` behavior | NO | Keep unchanged; `show --yaml` will reuse `export_macro_yaml` |
| `tests/venues/test_repo.py` | (various) | Existing `list_venues_with_fixture_counts` pattern | NO | Keep unchanged; macro listing query will mirror this pattern |

### Test modification policy

- [ ] No existing tests should be modified (greenfield for the new commands)
- [ ] New tests will be added under `tests/macros/` to cover:
  - The new listing query function in `repo.py` (scenarios: user macros, factory macros, all macros, empty result)
  - The new search query function in `repo.py` (scenarios: factory macros, user macros, all macros, no matches, SQL LIKE wildcard escaping)
  - The three CLI commands in `tests/cli/` (scenarios: normal output, empty result, missing working copy, unknown macro id for `show`)
- [ ] Test scenarios will be described in prose/Given-When-Then format; test function names will be decided by the implementing agents
- [ ] Tests must never touch anything under `~/Library/Application Support/Pioneer/rekordbox6/` — only throwaway SQLite DBs in `tmp_path`

### Existing files impacted (refactoring only — omit for greenfield)

| File | Impact |
|------|--------|
| `README.md` | "## Finding things" section rewritten; three `python3 -c` snippets deleted; venue snippet removed; "## Everyday commands" table extended |
| `src/rbxlight/macros/repo.py` | New listing and search query functions added (exact names and signatures decided by implementer) |
| `src/rbxlight/cli.py` | Three new commands added to `macro_app` (exact function names decided by implementer); small private line-formatter helper added |

---

## Implementation Notes for Agents

### For the backend agent (repo layer)

1. Add a listing query function to `src/rbxlight/macros/repo.py` that:
   - Takes `conn` and a scope parameter (user/factory/all)
   - Returns a list of dataclass instances (similar to `VenueWithFixtureCount`) containing macro metadata
   - Executes a single deterministic SQL query ordered by macro id
   - Mirrors the pattern of `list_venues_with_fixture_counts`

2. Add a search query function to `src/rbxlight/macros/repo.py` that:
   - Takes `conn`, a search term, and a scope parameter (user/factory/all)
   - Escapes SQL LIKE wildcards in the term (e.g., `%` → `\%`, `_` → `\_`)
   - Returns a list of matching macros ordered by id
   - Returns an empty list if no matches (not an error)

### For the CLI agent

1. Add three commands to `macro_app` in `src/rbxlight/cli.py`:
   - `macro list` with `--all` and `--factory` flags
   - `macro search <term>` with `--user` and `--all` flags
   - `macro show <id>` with `--yaml` flag

2. Use `_readonly_working_copy(_MACRO_DB_NAME)` to open the working copy (reuses the pull guard).

3. Add a small private line-formatter helper (e.g., `_format_macro_line`) that returns a single indented line showing id, name, and beats.

4. Catch `LookupError` from `get_macro` and convert to a clean message + exit 1.

5. For `show`, use `get_macro` for metadata and `list_macro_data` to build the slot summary.

6. For `show --yaml`, call `export_macro_yaml` and print the result.

### For the documentation agent

1. Rewrite README.md "## Finding things" section (lines 163–197) to use the three new commands.
2. Delete the venue snippet (lines 187–196) entirely.
3. Add three rows to the "## Everyday commands" table for the new commands.
4. Verify no `python3 -c` snippet remains anywhere in README.md.
