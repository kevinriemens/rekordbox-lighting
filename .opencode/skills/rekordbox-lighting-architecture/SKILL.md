---
name: rekordbox-lighting-architecture
description: rekordbox-lighting project architecture, module layout, and where code belongs. Use when adding modules, deciding file placement, or navigating the codebase.
metadata:
  skill-type: architecture
  language: python
  framework: typer, pytest
  project-type: data-tool
---

# rekordbox-lighting Architecture

You are building a local CLI data tool that safely reads and rewrites a working DJ's rekordbox lighting databases. There is no server, no network call, and no second user — but the databases you touch are live production data for someone's gigs, so every structural decision below exists to make mistakes hard to make.

## The Flow That Must Not Break

The project works against a **working copy**, not live rekordbox data. Normal operations never touch live; only `push` does:

```
# normal operation — never touches live (working copy)
CLI command -> safety.working_copy_write(work/…) -> repo write in one transaction -> verify by re-read

# the only path to live
push -> guard_rekordbox_not_running() -> verify_not_stale() -> backup_live_databases()
     -> shutil.copy2 work/<db> -> live/<db>, per file
     -> sha256 verify each copied file -> print restore command
```

**Corrected 2026-08-25:** this block previously claimed `push` goes through
`safety.write_transaction(LIVE, verify=...)`. It does not, and never has.
`sync.push()` promotes the working copy by **whole-file copy** (`shutil.copy2`), not by a
row-level SQL transaction — which is why it can move `macro.db3` and `user.db3` together.
`safety.write_transaction` is a real, tested primitive with **zero production callers**; it
exists for a future row-level live write that does not yet exist. Do not cite it as the
description of `push`.

**Two-tier write model:**
- **`safety.working_copy_write(db_name)`** — context manager for the disposable working copy (`work/`). No guard, no backup. Use for macro create/delete, layout regenerate/install, and all normal commands.
- **`safety.write_transaction(db_name, trigger_command, verify=None)`** — context manager for row-level writes to a live rekordbox DB. **Currently has no production callers** (`push` uses whole-file copy, see above); it is fully tested and available for the first command that genuinely needs to write single rows to live. Enforces: guard rekordbox not running → backup all → BEGIN → yield → verify(conn) inside txn → COMMIT. On exception: rollback + print restore instructions + re-raise. The `verify` parameter is an injectable hook (default: no-op) for operation-specific validation.

`pull` and `push` in `sync.py` are the ONLY code paths permitted to open a live database. Everything else resolves paths to `work/`. A module reaching for a live path outside `sync.py` is a defect — it bypasses the working-copy safety net that makes every other command harmless to run.

**Dry-run output** is built from typed frozen plan objects (`sync.PushPlan`, `macros.repo.CreateMacroPlan`, `macros.repo.DeleteMacroPlan`) that perform zero writes. The CLI renders these plans before asking for confirmation, so users see exactly what will happen.

**Backup and restore utilities:**
- `safety.backup_live_databases(...)` — public wrapper for timestamped backup with sha256 manifest. Called by `write_transaction` and available to `sync.push` for explicit backup before write.
- `safety.preflight_restore(backup_dir)` — named guard + verify_backup_integrity sequence. CLI `restore` calls it before its confirm prompt.

Full backup/restore/guard mechanics, the write context manager's complete API, and the complete pull/push contract (staleness checks, hashing) live in the `rekordbox-data-safety` skill — load it before writing any code that touches a `.db3` file or `sync.py`.

## System Overview

Offline, local, single-user CLI. No network, no server, no ORM, no daemon.

- **Input**: rekordbox LightingDB SQLite files — external, live, user data, **not part of this repo**. Located at `~/Library/Application Support/Pioneer/rekordbox6/LightingDB/` (`macro.db3`, `user.db3`; `master.db3` is read-only reference data, never written).
- **Output**: modified copies of those DBs (via the safety-guarded write flow) plus optional YAML macro definitions committed to this repo.

Schema details, table shapes, and the LightingEditModel XML format are covered in `rekordbox-lightingdb-schema` — this skill stays structural and cross-references that one instead of duplicating it.

## Project Structure

```
src/rbxlight/
  __init__.py
  cli.py             typer entrypoint, one sub-command group per capability
  safety.py          backup, restore, process guard, write context manager
  db.py              connection helpers (read-only default), path resolution
  sync.py            pull (live -> work/), push (work -> live), pull-state hashing, staleness check
  models.py          dataclasses: Macro, MacroData, FixtureSlot, Venue, Fixture, MacroPattern
  lightingxml.py     LightingEditModel parse + serialize (round-trip exact)
  colors.py          signed int32 ARGB <-> rgb/hex conversion
  macros/
    repo.py          macro.db3 read/write, id allocation, 25-row invariant enforcement
    patterns.py      macro_pattern / macro_assign read/write — banks, energies, phase rows
    yaml_io.py       macro <-> YAML export/import
    generate.py      primitives: chase, sweep, pingpong, colour_cycle, strobe_hit, build
    transform.py     clone, recolor, stretch, mirror
  venues/
    repo.py          user.db3 venue/fixture read/write
    builder.py       FullArcAI venue generation, slot allocation solver
  phrases/
    repo.py          content read/write (per-track macro_pattern_id). phrase_data: not yet built
    assign.py        NOT YET BUILT — bulk macro_pattern_id rebalance, phrase reassignment
  experiments/       NOT PRESENT — recreated per probe, deleted with it. See the contract below.
  preview/
    layout.py        stage geometry, fixture placement, normalization, layout JSON persistence
    payload.py       assembles the visualizer payload from macro + venue + layout
    extract.py       macro XML -> per-beat brightness/colour/movement
    document.py      renders the self-contained offline HTML
    template.html    vanilla-JS visualizer — zero external refs, no build step
tests/
  conftest.py        fixtures building throwaway temp DBs
  ...                mirrors src layout
backups/             gitignored, timestamped DB backups
macros/              gitignored or committed YAML macro definitions
work/
  macro.db3          working copy (gitignored)
  user.db3           working copy (gitignored)
  .pull-state.json   sha256 + timestamp of the live DBs at pull time
pyproject.toml
```

Keep it this flat. This is a personal tool for one rig — no plugin system, no config-driven fixture registry, no abstract "backend" layer. If a new capability doesn't fit an existing package, it's a new top-level package (`macros/`, `venues/`, `phrases/`), not a new layer of indirection inside one.

### `experiments/` — disposable by contract (added 2026-08-25)

**The package does not currently exist. That is the expected steady state.** Create it when a probe
needs it, delete it when the probe has answered its question. It existed for a few hours on
2026-08-25 to hold the ninth-bank probe and was removed the same day once the verdict was recorded —
the contract working, not an oversight.

`src/rbxlight/experiments/` holds one-off probes that exist to answer a question about rekordbox's
behaviour, not to deliver a capability. The rules that make it safe to keep in the repo:

- **Nothing permanent may import from `experiments/`.** The dependency arrow only ever points inward
  (`experiments/` → `macros/`, `phrases/`, `safety`, `db`). This is what makes a module here
  deletable in a single commit once its question is answered.
- **Reusable logic does not live here.** If a probe needs a real capability (e.g. cloning
  `macro_assign` rows), that capability goes in the permanent repo module and the probe calls it.
  What stays in `experiments/` is only the glue: the plan, the apply/revert pair, and the undo state.
- **Same safety rules as everything else.** Working copy only, dry-run by default, `--write` opt-in.
  A probe is not a licence to skip the write model.

## Where to Put New Code

| I need to... | Goes in |
|---|---|
| Add a new CLI command | `cli.py` |
| Write to working copy (macro create/delete, layout regen) | `safety.working_copy_write(db_name)` context manager |
| Promote the working copy to live | `sync.push()` — whole-file copy, the only live write path that exists |
| Row-level write to a live DB (nothing does this yet) | `safety.write_transaction(db_name, trigger_command, verify=...)` context manager |
| Open, read, or write any `.db3` file handle | `db.py` (read helpers) / `safety.py` (write context managers) — nowhere else |
| Move data between live and working copy | `sync.py` |
| Resolve which DB path to use (work vs live) | `db.py` (default: work) |
| Support a new LightingEditModel XML section | `lightingxml.py` |
| Add a new macro shape/pattern (chase, sweep, ...) | `macros/generate.py` |
| Modify an existing macro (clone, recolor, stretch) | `macros/transform.py` |
| Change macro storage, id allocation, YAML round-trip | `macros/repo.py` / `macros/yaml_io.py` |
| Read/write banks — `macro_pattern` rows, `macro_assign` phase rows | `macros/patterns.py` |
| Read/write a track's bank assignment (`content.macro_pattern_id`) | `phrases/repo.py` |
| A throwaway, single-story probe of unknown rekordbox behaviour | `experiments/<name>.py` (see below) |
| Venue, fixture, or patch logic | `venues/repo.py` (storage) or `venues/builder.py` (generation) |
| Colour math (ARGB <-> hex/rgb) | `colors.py` |
| Stage/truss geometry, fixture auto-placement, layout file persistence | `preview/layout*.py` (see flat-structure section) |
| Visualizer payload shape | `preview/payload.py` |
| Anything the visualizer draws or how it draws it | `preview/template.html` |
| New domain type | `models.py` — plain dataclass, no behavior beyond simple derived properties |

### Flat structure: no nested sub-packages, but split large modules into siblings

"Flat" means **no nested sub-packages** (e.g. no `preview/geometry/internal/helpers/`) — it does NOT mean "never split a file".
A module past roughly 400 lines with separable concerns should split into **sibling modules within its own package**,
keeping one module as the public facade that re-exports the public symbols.

**2026-08-23 clarification** (supersedes 2026-08-16 decision that declined to split `preview/layout.py`):
The 2026-08-16 decision was made because the flat rule had no upper bound. This clarification removes that ambiguity.

#### Worked example: `preview/layout*` sibling set

`preview/layout.py` (955 lines) was split into five flat siblings with strict one-directional imports:

- `layout_geometry.py` (168 ln) — stage/arch geometry, coordinate normalization, normalization frame. No sibling imports.
- `layout_segments.py` (119 ln) — truss segment classification, point-along-segment mapping, structure validation. Imports: `geometry`.
- `layout_placement.py` (406 ln) — fixture placement onto the arch, fixture-kind classification, `generate_layout`, `apply_prior_calibration`. Imports: `geometry`, `segments`.
- `layout_io.py` (310 ln) — layout JSON load/save/diff/merge, dict (de)serialization, path resolution. Imports: `geometry`, `segments`, `placement`.
- `layout.py` (97 ln) — pure re-export facade for the 23 public symbols. No logic. No sibling imports FROM it.

**Import direction is strictly one-directional:** `geometry` ← `segments` ← `placement` ← `io` ← `layout.py`.

**Review gate:** If anyone later makes `layout_geometry.py` import from `layout_placement.py` (or otherwise reverses the chain),
a circular import appears. Reviewers must reject upward imports in this chain.

Two things to know before changing any `preview/layout*` module:

- **Layout files are the tool's own data, not rekordbox's.** They live in `work/layouts/layout_venue_{id}.json`.
  Truss geometry in particular is this tool's concept and must never be written into any `.db3`.
- **Everything in it is pure** — no DB access, no live-path resolution. `save_layout`/`load_layout`
  are the only I/O, and `save_layout`'s atomic temp-file-plus-`os.replace` is a hard guarantee with
  dedicated tests. Do not introduce a DB read into geometry or placement to "look something up".

## Key Patterns

### Dataclass models, no ORM

`models.py` holds plain `@dataclass` definitions. No SQLAlchemy, no active-record methods, no lazy loading — a `Macro` is data, not a query.

```python
@dataclass
class MacroData:
    id: int
    macro_id: int
    macro_fixture_id: int
    xml: str  # raw LightingEditModel payload, empty string allowed
```

### Repository pattern — one `repo.py` per database concern

Each `repo.py` owns exactly one database's tables and exposes typed functions. It never leaks a raw sqlite `Row` or cursor upward — callers get dataclasses in, dataclasses out.

```python
# macros/repo.py
def get_macro(conn: sqlite3.Connection, macro_id: int) -> Macro: ...
def list_macro_data(conn: sqlite3.Connection, macro_id: int) -> list[MacroData]: ...
def save_macro_data(conn: sqlite3.Connection, row: MacroData) -> None: ...
```

`conn` is passed in — repo functions never open their own connection. That's `db.py`/`safety.py`'s job, which is what keeps every write on the guarded path.

### `lightingxml` round-trip requirement

`parse(serialize(x)) == x` is a hard invariant, not a nice-to-have — rekordbox will silently misrender or ignore a payload that doesn't match its exact section order and empty-tag convention.

- Fixed section order: `Brightness, Colour, Strobe, Position, Rotate, Gobo` — always in that order, even if some are empty.
- Empty sections serialize as self-closing tags: `<Strobe/>`, `<Gobo/>`, never `<Strobe></Strobe>`.

```python
def serialize(model: LightingEditModel) -> str:
    # section order is fixed — do not reorder, do not sort
    sections = [
        model.brightness,
        model.colour,
        model.strobe,
        model.position,
        model.rotate,
        model.gobo,
    ]
    ...
```

### typer command shape — dry-run by default

Any command that can mutate a DB defaults to a dry run and requires an explicit flag to actually write. This makes "I just wanted to preview it" the safe default instead of an opt-in.

```python
@app.command()
def recolor(macro_id: int, hex_color: str, write: bool = False):
    plan = build_recolor_plan(macro_id, hex_color)
    print_plan(plan)
    if not write:
        print("dry run — pass --write to apply")
        return
    with safety.guarded_write() as conn:
        apply_plan(conn, plan)
```

### Working copy default

`db.py` path resolution returns `work/` paths by default; live paths require an explicit opt-in flag that only `sync.py` passes. This makes "resolve a DB path" safe to call from anywhere without accidentally reaching live.

### Pure functions in `generate.py`

Macro-shape primitives (`chase`, `sweep`, `pingpong`, `colour_cycle`, `strobe_hit`) take parameters and return an XML string or `LightingEditModel` — they never touch a database or filesystem. This makes them trivially unit-testable and reusable from both `macros/repo.py` and ad-hoc scripts.

```python
def chase(beats: float, colours: list[int], steps: int) -> str:
    """Pure: params in, XML string out. No DB, no I/O."""
    ...
```

## Testing Approach

Tests never touch the live rekordbox DBs — there is exactly one copy of a working DJ's library and it does not go anywhere near a test run.

- `conftest.py` builds throwaway SQLite DBs in `tmp_path` using the real schema plus a handful of representative rows (a couple of macros, a couple of fixtures, one venue).
- Golden-file tests for XML round-trip use real payloads captured from the live DB into `tests/fixtures/` — these are the project's most important tests, since `lightingxml` round-trip correctness is what keeps rekordbox from rejecting or misplaying a macro.
- Safety-path tests (backup, restore, process guard) live under `rekordbox-data-safety`'s scope — see that skill for what must be covered there.
- Tests never touch `work/` either — only throwaway DBs in `tmp_path`. A corrupted working copy must not fail the suite, and a test run must never mutate the developer's working state. `work/` is for manual/CLI use; `tmp_path` is for tests.

## Quick Reference

- install: `pip install -e ".[dev]"` (or `uv sync`)
- run: `rbxlight --help`
- pull working copy: `rbxlight pull`
- push to live: `rbxlight push --write` — stale-write protected, refuses if live changed since last pull
- test: `pytest`
- lint/format: `ruff check .` / `ruff format .`
- typecheck: `mypy src/`

## Required Skills

Any DB-touching work must also load:
- `rekordbox-data-safety` (mandatory) — backup/restore/guard mechanics and the write context manager contract.
- `rekordbox-lightingdb-schema` — full table shapes, the LightingEditModel XML format, fixture slot/section matrix.
- `physical-rig-profile` — the real hardware rig (universes, fixture types, venue patch layouts) that macro/venue generation must stay grounded in.

---

**Updated 2026-08-23:** Documented `safety.working_copy_write` vs `safety.write_transaction` as explicit working-copy-vs-live distinction; added injectable `verify` hook, `preflight_restore`, `backup_live_databases`, and typed frozen plan objects for dry-run output. Clarified flat-structure rule: no nested sub-packages, but modules >400 lines with separable concerns should split into siblings with one facade. Documented `preview/layout*` sibling set (geometry ← segments ← placement ← io ← layout.py) as worked example; added review gate against circular imports.
