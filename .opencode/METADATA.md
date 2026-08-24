# Project: rekordbox-lighting
**Initialized:** 2026-08-14

## Opencode Configuration
| Setting               | Value  | Description                                 |
|-----------------------|--------|---------------------------------------------|
| `skip_frontend_tests` | `true` | Visualizer is verified by opening the generated HTML; Python side is covered by pytest |
| `skip_backend_tests`  | `false` | Skip backend tests during the TDD-workflow |
| `skip_wiki_update`    | `true` | Skip wiki docs update after each feature (personal tool) |
| `is_monorepo`         | `false` | Indicates if the project is a monorepo with multiple subprojects |

## Project Agents
| Agent | Purpose |
|-------|---------|
| `backend-agent` | Python implementation. Loads safety + schema + rig skills. Enforces dry-run/backup/25-row rules. |
| `backend-testing-agent` | pytest suites. Never touches live DBs; builds throwaway DBs in `tmp_path`. |
| `frontend-agent` | Offline macro visualizer. Single self-contained HTML, vanilla JS, no build step, no network. |

## Project Skills
| Skill | Purpose |
|-------|---------|
| `rekordbox-data-safety` | **MANDATORY for any DB-touching code.** Backups, process guard, dry-run, rollback, 25-row invariant. |
| `rekordbox-lightingdb-schema` | Table schemas for `macro.db3` / `user.db3` + the `LightingEditModel` XML format. |
| `physical-rig-profile` | The physical DMX rig and how it maps to venue profiles and macro slots. |
| `rekordbox-lighting-architecture` | Module layout, where code belongs, the write-path flow. |

Global skills also relevant: `python-standards`, `test-behaviour`, `tdd-workflow`, `agent-delegation`.

**Skills are living documents — update them as part of the work, not afterwards.** If building or
refining a feature turns up a fact that contradicts a project skill, or a schema detail the skill
does not cover, correcting the skill file is **in scope for that story** and must not be deferred.
These skills are read as ground truth by every agent, so a stale one silently propagates the error
into future work. Note the correction and its date in the skill itself, and say so in the story's
completion report. Precedent: on 2026-08-23 the schema skill documented `macro_assign.phase` as a
uniform `1..11` (implying 297 rows); the live databases hold 232 rows with a per-energy phase count.
A refined story had already been written against the wrong number before the contradiction surfaced.

## Project File Tree Structure

```
rekordbox-lighting/
├── src/rbxlight/
│   ├── cli.py             → typer entrypoint, one sub-command group per capability
│   ├── safety.py          → backup / restore / rekordbox process guard / write context manager
│   ├── db.py              → connection helpers (read-only by default), path resolution
│   ├── sync.py            → pull (live → work/), push (work → live), staleness check
│   ├── models.py          → dataclasses: Macro, MacroData, FixtureSlot, Venue, Fixture, MacroPattern
│   ├── lightingxml.py     → LightingEditModel parse + serialize (exact round-trip)
│   ├── colors.py          → signed int32 ARGB ↔ rgb/hex
│   ├── macros/
│   │   ├── repo.py        → macro.db3 read/write, id allocation, 25-row enforcement
│   │   ├── yaml_io.py     → macro ↔ YAML export/import
│   │   ├── generate.py    → pure primitives: chase, sweep, pingpong, colour_cycle, strobe_hit, build
│   │   └── transform.py   → clone, recolor, stretch, mirror
│   ├── venues/
│   │   ├── repo.py        → user.db3 venue/fixture read/write
│   │   ├── models.py      → Venue, Fixture, FixtureSlot dataclasses
│   │   └── builder.py     → FullArcAI venue generation, slot allocation solver
│   └── preview/
│       ├── layout.py          → re-export facade for 23 public symbols
│       ├── layout_geometry.py → stage/arch geometry, coordinate normalization
│       ├── layout_segments.py → truss segment classification, point-along-segment mapping
│       ├── layout_placement.py → fixture placement, fixture-kind classification, generate_layout
│       ├── layout_io.py       → layout JSON load/save/diff/merge, dict (de)serialization
│       ├── payload.py         → visualizer payload assembly
│       ├── extract.py         → macro XML → per-beat brightness/colour/movement
│       ├── document.py        → self-contained offline HTML rendering
│       └── template.html      → vanilla-JS visualizer
├── tests/                 → mirrors src layout; conftest.py builds throwaway DBs
│   └── fixtures/          → golden XML payloads captured from the live DB
├── backups/               → gitignored, timestamped DB backups
├── work/                  → working copy (gitignored): macro.db3, user.db3, .pull-state.json
├── macros/                → YAML macro definitions
└── pyproject.toml
```

**Corrected 2026-08-23:** Removed non-existent `phrases/` module; added `sync.py`, `venues/models.py`, and `preview/` package with all submodules; added `work/` directory.

**Corrected 2026-08-24:** Split `preview/layout.py` (955 ln) into five flat siblings with one-directional imports: geometry ← segments ← placement ← io ← layout.py facade.

## Tech Stack
| Type | Technology |
|------|------------|
| Language | Python 3.12 |
| CLI | typer |
| Database | stdlib `sqlite3` (no ORM) — external rekordbox SQLite files |
| XML | stdlib `xml.etree.ElementTree` |
| Config/IO | `ruamel.yaml` |
| Testing | pytest |
| Lint/Format | ruff |
| Types | mypy |
| Network | none — fully offline, local, single-user |

## Architecture

### System Overview
Offline local CLI that safely reads and rewrites a working DJ's Pioneer rekordbox 6 lighting databases.
It exists because the rekordbox GUI makes macro authoring and per-track phrase assignment prohibitively slow.

**The data is live, external, and irreplaceable.** It is NOT part of this repo:
`~/Library/Application Support/Pioneer/rekordbox6/LightingDB/`

| File | Size | Role |
|---|---|---|
| `macro.db3` | 9.8M | macro library — read/write target |
| `user.db3` | 13M | venues, fixtures, per-track phrase assignments — read/write target |
| `master.db3` | 512M | factory fixture-profile library — **read-only, never write** |

All are plain unencrypted SQLite 3 (not SQLCipher). Macro programming is stored as
plain `LightingEditModel` XML in `macro_data.data`.

### The Flow That Must Not Break

```
CLI command
   └─> safety.guard_rekordbox_not_running()
        └─> safety.backup_all()            (timestamped + sha256 manifest)
             └─> write inside ONE transaction
                  └─> verify by re-read
                       └─> report restore command to user
```

No module may open a database read-write except through the `safety` write context manager.
A bare `sqlite3.connect(path)` used for writing anywhere outside `safety.py` / `db.py` is a defect.

### Project Structure

```
cli.py ──> macros/ ──┐
       ──> venues/ ──┼──> repo.py ──> db.py ──> safety.py ──> [live SQLite files]
       ──> phrases/ ─┘                              ▲
                                                    │
   generate.py / transform.py (PURE, no DB access) ─┘ never crosses this line
```

### Where to Put New Code
| I need to create... | Module |
|---|---|
| A new CLI command | `cli.py` |
| Anything holding a DB file handle | `db.py` / `safety.py` **only** |
| Support for a new XML section/attribute | `lightingxml.py` |
| A new macro shape (chase, sweep, ...) | `macros/generate.py` |
| A modification of an existing macro | `macros/transform.py` |
| Venue / fixture / DMX patch logic | `venues/` |
| Track + phrase assignment logic | `phrases/` |
| Colour math | `colors.py` |

### Key Patterns
| Pattern | Usage |
|---|---|
| Dataclass models | Plain `@dataclass`, no ORM |
| Repository | Each `repo.py` owns one DB, exposes typed functions, never leaks sqlite rows/cursors upward |
| Pure generators | `generate.py` / `transform.py` return models or XML strings and never touch a DB — trivially testable |
| Dry-run default | Every mutating command changes nothing without an explicit `--write` |
| Exact round-trip | `parse(serialize(x)) == x`; fixed section order Brightness, Colour, Strobe, Position, Rotate, Gobo; empty sections still emitted as self-closing tags |
| 25-row invariant | Every macro write emits exactly 25 `macro_data` rows; unused slots get empty-string `data`, never NULL |

### Quick Reference
- **Install:** `pip install -e ".[dev]"`
- **Run:** `rbxlight --help`
- **Test:** `pytest` · single: `pytest tests/path::test_name -v`
- **Lint:** `ruff check .` · **Format:** `ruff format .` · **Types:** `mypy src/`

## Key Documents

| Doc | Purpose |
|---|---|
| `README.md` | User-facing guide — install, five-minute tour, everyday commands, recovery |
| `docs/PROJECT-FOUNDATION.md` | **Read first.** Origin record: what was discovered, what was proven live, and which assumptions were wrong |
| `.opencode/BACKLOG.md` | Open work, incl. the multi-venue epic that makes this reusable on any rig |

## Notes

**Safety — read `rekordbox-data-safety` before writing any DB code. Non-negotiable.**
- Quit rekordbox before any write. It flushes in-memory state on exit and will silently clobber external edits.
- Timestamped backup before every write. Never rely on rekordbox's own `macro_old.db3` / `master_old.db3`.
- Never modify `preset=1` rows (factory macros, ids 1..916 plus `-1` and `10000`). User macros are `preset=0`, `id >= 10001`.
- Tests must never touch anything under `~/Library/Application Support/Pioneer/rekordbox6/`, not even a read.

**Rig context (see `physical-rig-profile`)**
- Active venue is id 2 `FullArcCustomBars` (`ExecVenueId=2`), 27 fixtures.
- It deliberately decomposes each 43-channel L1015 moving beam bar into 1 tilt block + 9 addressable
  cells using off-label profiles. **This is intentional. Do not "fix" it.**
- Known ceiling: both bars use the same slot sequence, so they always mirror each other.
  Planned `FullArcAI` venue resolves this using the 11 currently-unused slots.

**Diversity baseline (measured)**
- 2943 tracks, 60% concentrated on 2 of 27 macro_patterns (pattern 1 = 39.5%, pattern 7 = 20.7%).
- 173 of 190 macros are used at least once — the library is adequate, the *distribution* is the problem.

**Unverified assumptions — do not depend on these**
- Whether rekordbox validates `lighting_property.MacroVersionNum` (1061) or `DbVersionNum` (1854).
- Whether it prunes rows it doesn't recognize, or rewrites user macros on version upgrade.
- A round-trip test (write a macro, confirm it appears and plays in rekordbox) must pass before
  any write path is trusted.
