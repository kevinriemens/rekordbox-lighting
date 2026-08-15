# M1 — Safety layer, working-copy sync, and macro round-trip

**Completed:** 2026-08-14
**Epic:** USER_CHANGE_REQUEST
**Source:** ad-hoc request (analyze LightingDB, enable macro authoring outside the rekordbox GUI)

## Summary
Built the safety-critical foundation for reading and writing a working DJ's live rekordbox
LightingDB, plus macro read/write, YAML export/import, and pure macro-generation primitives.
Verified end-to-end against the real database: two macros written externally (one cloned,
one machine-generated) both appear in rekordbox.

## Plan Approved by the user

### Requirements Summary
- Never destroy live show data — backups, guards, dry-run, rollback, all enforced permanently
- Work on a copy; explicit `pull` / `push` with stale-write protection
- Read/write macros and their `LightingEditModel` XML payloads
- Generate macros procedurally instead of via the GUI
- Prove rekordbox accepts externally-written rows before building anything on that assumption

### Technical Approach
- Backend: Python 3.12 CLI, stdlib `sqlite3` + `ElementTree`, typer, ruamel.yaml, pytest
- Modules: `safety`, `sync`, `db`, `models`, `colors`, `lightingxml`, `macros/{repo,yaml_io,generate}`, `cli`
- Frontend: none
- Database: no migrations — schema is rekordbox's

### Execution Order
| Phase | Agent | Task |
|---|---|---|
| 1 | init-skill-writer ×6 | Safety, schema, rig, architecture skills + 2 agent customizations |
| 2 | backend-testing-agent | 254 tests defining the contract |
| 3 | backend-agent (×2 parallel) | Pure domain layer / safety+sync layer |
| 4 | backend-testing-agent | Fix rollback test fixture defect |
| 5 | backend-agent | macros + CLI layer |
| 6 | backend-optimizer-agent | Standards review, dedup, lint |

## Implementation

### Backend
- `safety.py` — `guard_rekordbox_not_running`, `backup_all` (timestamped + sha256 manifest),
  `verify_backup_integrity`, `restore_from_backup`, `write_transaction`, `assert_25_rows`
- `sync.py` — `pull` (records live sha256), `push` (re-hashes live, hard-stops on drift), `verify_not_stale`
- `db.py` — `resolve_path` defaults to `work/`, live requires explicit opt-in; read-only URI connections
- `lightingxml.py` — parse/serialize, section order fixed, empty sections preserved, absent vs present-empty distinguished
- `colors.py` — signed int32 ARGB both directions
- `macros/repo.py` — 25-row invariant, factory-immutable, user id allocation ≥ 10001, tolerant reads
- `macros/yaml_io.py` — export/import, capability validation
- `macros/generate.py` — pure `chase`, `sweep`, `pingpong`, `colour_cycle`, `strobe_hit`
- `cli.py` — `macro create`, dry-run by default

### Deviations from Plan
- Added the working-copy (`pull`/`push`) model at the user's suggestion mid-build; it replaced
  direct-to-live operation and added sha256 stale-write protection. Safety and architecture
  skills were amended accordingly (rules 9 and 10).
- `pull`/`push`/`restore` were implemented as library functions but NOT wired into the CLI —
  the test contract only specified CLI behavior for `macro create`. Carried to backlog.

## Agents Used
| Agent | Task | Result |
|---|---|---|
| init-skill-writer ×6 | skills + agent customization | Complete |
| backend-testing-agent | 254-test contract suite | Complete |
| backend-agent | pure domain layer | Complete |
| backend-agent | safety + sync layer | Complete, escalated 1 test defect correctly |
| backend-testing-agent | rollback fixture fix | Complete |
| backend-agent | macros + CLI | Complete |
| backend-optimizer-agent | review + dedup + lint | Complete |

## Files Modified
- `src/rbxlight/{__init__,models,colors,lightingxml,db,safety,sync,cli}.py`
- `src/rbxlight/macros/{__init__,repo,yaml_io,generate}.py`
- `tests/**` — 254 tests, `conftest.py`, golden corpus of 37 real XML payloads
- `.opencode/skills/**` — 4 skills; `.opencode/agents/**` — 2 customized agents

## Tests
254 written, 254 passing. ruff clean, mypy clean.

## Live verification (the milestone gate)
Backup: `backups/2026-08-14T184537568265Z/`
- `10007 AI TEST CLONE` — byte-identical clone of user macro `<example macro>` → DB write layer proven
- `10008 AI TEST SWEEP` — machine-generated cyan sweep across Bar Light 1–6 → XML generator proven

**Result: both macros appear in rekordbox.**

### What this establishes (previously unverified)
- rekordbox accepts externally-written macro rows
- no checksum, no version gate, no pruning of unknown rows
- `MacroVersionNum` / `DbVersionNum` do not need to be bumped
- machine-generated `LightingEditModel` XML is accepted as valid
- compact single-line XML is accepted despite rekordbox writing pretty-printed output

### Still unverified
- whether the generated sweep *renders* as a correct left-to-right sweep during playback
  (appearance in the macro list is confirmed; visual playback is not)
