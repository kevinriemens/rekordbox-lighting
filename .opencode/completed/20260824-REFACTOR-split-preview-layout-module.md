# Split preview/layout.py into flat sibling modules

**Completed:** 2026-08-24
**Epic:** REFACTOR
**Source:** `.opencode/refined/REFACTOR-split-preview-layout-module.md`

## Summary

`preview/layout.py` — the project's largest file at 955 lines of five mixed concerns — was split into four flat sibling
modules plus a pure re-export facade. Zero behaviour change; the existing 717-test suite passed completely unmodified,
which was the entire safety argument for doing the split now rather than later.

## Plan Approved by the user

### Requirements Summary

- Split `preview/layout.py` (955 lines) into 4 flat sibling modules + a re-export facade
- All 23 public symbols stay importable from `preview.layout`, identical names and behaviour
- Zero test file modifications — the existing suite is the safety net
- Update the architecture skill (flat = no nested sub-packages; ~400-line sibling-split rule, dated 2026-08-23) and the
  METADATA file tree

### Technical Approach

Backend only. New siblings in `src/rbxlight/preview/`, strict one-directional imports:

```
layout_geometry.py ← layout_segments.py ← layout_placement.py ← layout_io.py ← layout.py (facade)
```

Frontend skipped (`skip_frontend_tests: true`, no UI impact). No optimizer phase — the story mandates zero logic change
and an optimizer would violate that constraint.

### Execution Order

| Phase | Agent | Task |
|-------|-------|------|
| 1 | *(skipped)* | No test changes — existing suite is the contract |
| 2 | `backend-agent` | Perform the split; verify tests + ruff + mypy pass unchanged |
| 3 | `general-task-agent` | Update architecture skill + METADATA file tree |

## Test Impact Analysis

Zero conflicts. `cli.py` reaches the module via attribute access (`preview_layout.X`); `payload.py` and both test files
import public symbols only. No private symbol is reached from anywhere in `src/` or `tests/`. Phase 1.3 report skipped.

| Test File | Count | Action |
|-----------|-------|--------|
| `tests/preview/test_layout.py` | 103 | Unmodified |
| `tests/preview/test_payload.py` | multiple | Unmodified |

## Implementation

### Backend

| Module | Lines | Imports from |
|--------|-------|--------------|
| `layout_geometry.py` | 168 | — |
| `layout_segments.py` | 119 | geometry |
| `layout_placement.py` | 406 | geometry, segments |
| `layout_io.py` | 310 | geometry, segments, placement |
| `layout.py` | 97 | all four (re-export only, no logic) |

- `generate_layout` (209 lines) kept whole in `layout_placement.py`, as specified.
- `KIND_BY_MASTER_ID` and `_EFFECT_SLOT_TYPE_ID` moved into placement rather than left stranded.
- `DEFAULT_PAN_DEGREES` / `DEFAULT_TILT_DEGREES` live in placement; `layout_io` imports them for the
  `layout_from_dict` migration fallback.
- `layout.py` re-exports module-attribute constants (`GROUND_Y`, `SKY_Y`, `DEFAULT_TILT_BLOCK_ROTATION_DEGREES`, …)
  alongside the 23 public symbols, because `cli.py` and tests reach them as attributes.

### Deviations from Plan

- `layout_io.py` also imports `layout_segments` (it needs `DegenerateStructureError`). The story's chain specified only
  geometry + placement. The import direction remains strictly one-way with no cycles — the story simply
  under-specified this edge.

## Agents Used

| Agent | Task | Result |
|-------|------|--------|
| `backend-agent` | Perform the module split | Complete |
| `general-task-agent` | Architecture skill + METADATA docs | Complete |

## Files Modified

- `src/rbxlight/preview/layout.py` — 955 → 97 lines, now a pure re-export facade
- `src/rbxlight/preview/layout_geometry.py` — new
- `src/rbxlight/preview/layout_segments.py` — new
- `src/rbxlight/preview/layout_placement.py` — new
- `src/rbxlight/preview/layout_io.py` — new
- `.opencode/skills/rekordbox-lighting-architecture/SKILL.md` — flat-structure rule amended (2026-08-23, supersedes
  2026-08-16); sibling set documented; circular-import review gate added
- `.opencode/METADATA.md` — file tree expanded with the new siblings

## Tests

717 tests passing, zero test files modified. `ruff check`, `ruff format --check`, `mypy src/` all clean.

## Playbook Candidates

None reported (no optimizer phase; N/A for a Python CLI).
