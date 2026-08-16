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
# normal operation — never touches live
CLI command -> db.connect(work/…) -> repo write in one transaction -> verify by re-read

# the only path to live
push -> guard_rekordbox_not_running() -> backup_all(LIVE) -> verify_not_stale()
     -> apply to live -> verify by re-read -> print restore command
```

`pull` and `push` in `sync.py` are the ONLY code paths permitted to open a live database. Everything else resolves paths to `work/`. A module reaching for a live path outside `sync.py` is a defect — it bypasses the working-copy safety net that makes every other command harmless to run.

No module may open a database read-write except through the `safety` write context manager. Read paths must use the read-only URI connection helper in `db.py`. A change that adds `sqlite3.connect(path)` for a write anywhere outside `safety.py` / `db.py` (or `sync.py`'s push path) is a defect, full stop — it skips the process guard and the backup, and it is exactly the mistake that corrupts a DJ's library before a gig.

Full backup/restore/guard mechanics, the write context manager's API, and the complete pull/push contract (staleness checks, hashing, rules 9 and 10) live in the `rekordbox-data-safety` skill — load it before writing any code that touches a `.db3` file or `sync.py`.

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
    yaml_io.py       macro <-> YAML export/import
    generate.py      primitives: chase, sweep, pingpong, colour_cycle, strobe_hit, build
    transform.py     clone, recolor, stretch, mirror
  venues/
    repo.py          user.db3 venue/fixture read/write
    builder.py       FullArcAI venue generation, slot allocation solver
  phrases/
    repo.py          content + phrase_data read/write
    assign.py        bulk macro_pattern_id rebalance, phrase reassignment
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

## Where to Put New Code

| I need to... | Goes in |
|---|---|
| Add a new CLI command | `cli.py` |
| Open, read, or write any `.db3` file handle | `db.py` (read helpers) / `safety.py` (write context manager) — nowhere else |
| Move data between live and working copy | `sync.py` |
| Resolve which DB path to use (work vs live) | `db.py` (default: work) |
| Support a new LightingEditModel XML section | `lightingxml.py` |
| Add a new macro shape/pattern (chase, sweep, ...) | `macros/generate.py` |
| Modify an existing macro (clone, recolor, stretch) | `macros/transform.py` |
| Change macro storage, id allocation, YAML round-trip | `macros/repo.py` / `macros/yaml_io.py` |
| Venue, fixture, or patch logic | `venues/repo.py` (storage) or `venues/builder.py` (generation) |
| Track/phrase macro assignment | `phrases/repo.py` (storage) or `phrases/assign.py` (bulk logic) |
| Colour math (ARGB <-> hex/rgb) | `colors.py` |
| Stage/truss geometry, fixture auto-placement, layout file persistence | `preview/layout.py` |
| Visualizer payload shape | `preview/payload.py` |
| Anything the visualizer draws or how it draws it | `preview/template.html` |
| New domain type | `models.py` — plain dataclass, no behavior beyond simple derived properties |

### `preview/layout.py` is the one deliberate exception to flatness

It owns five concerns at once — stage geometry, segment classification, fixture placement,
normalization, and layout JSON persistence — and is the largest module in the project (~900 lines).
That is intentional under the flat rule, not an oversight: the concerns share one coordinate system
and splitting them would spread a single invariant across four files.

Two things to know before changing it:

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
