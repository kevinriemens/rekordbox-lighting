---
epic: "REFACTOR"
title: "Split preview/layout.py into flat sibling modules"
estimate: M
status: ready
created: 2026-08-23
depends_on: [ ]
labels: [ refactor, architecture, preview ]
priority: P2
claimed_by:
claimed_by_date:
---

## 1. User Story

**As a** maintainer of the rekordbox-lighting codebase\
**I want** to split the 955-line `preview/layout.py` into smaller, focused sibling modules\
**So that** the codebase remains navigable as it grows, and future changes to geometry, classification, placement, or persistence can be made independently without touching unrelated code\

## 2. Business Context & Value

`preview/layout.py` is the largest file in the project at 955 lines and continues to grow. It contains five separable concerns: geometry/coordinate math, truss segment classification, fixture placement, normalization, and JSON persistence. While each concern is internally cohesive, they are independent enough that changes to one should not require re-reading or re-testing the others.

The project's architecture skill mandates a flat module structure to prevent deep nesting (e.g., `preview/geometry/internal/helpers/`). A prior decision (2026-08-16) declined to split the file because the rule had no upper bound. **This story amends that rule:** flat means no nested sub-packages; a module past roughly 400 lines with separable concerns should split into siblings within its own package, keeping one module as the public facade. This preserves the intent (no deep nesting) while allowing the codebase to scale.

The split is safe today because no external caller and no test reaches past the public surface — a property that will not survive indefinitely. Splitting now costs less than splitting later.

## 3. Acceptance Criteria

* [ ] **Scenario 1: All existing tests pass unmodified**
    * Given the test suite in `tests/preview/test_layout.py` (103 test functions) and `tests/preview/test_payload.py`
    * When the refactored code is run
    * Then all tests pass without any modifications to test files, test imports, or test assertions

* [ ] **Scenario 2: Public surface remains unchanged**
    * Given that `cli.py` imports `layout_path_for_venue`, `RigLayout`, `load_layout`, `LayoutDiffEntry`, `ensure_layout`, `arch_outline_cm`, `generate_layout`, `diff_layouts`, `apply_prior_calibration`, `save_layout`, `load_layout_file`, `InvalidSavedLayoutError`, `DegenerateStructureError` from `preview.layout`
    * When `cli.py` is run
    * Then all imports resolve and the CLI functions identically to before

* [ ] **Scenario 3: Payload module continues to work**
    * Given that `payload.py` imports `RigLayout`, `frame_cm_to_dict`, `normalized_structure` from `preview.layout`
    * When `payload.py` is used
    * Then all imports resolve and payload generation is identical to before

* [ ] **Scenario 4: Code quality gates pass**
    * Given the refactored modules
    * When `ruff` and `mypy` are run
    * Then no linting or type errors are reported

* [ ] **Scenario 5: No circular imports**
    * Given the new sibling modules
    * When the preview package is imported
    * Then no circular import errors occur, and the import direction is strictly: geometry ← segments ← placement ← io, with `layout.py` as a pure re-export leaf

* [ ] **Scenario 6: Architecture skill is updated**
    * Given the project's architecture documentation
    * When reviewed
    * Then it includes the clarification that flat means no nested sub-packages (not no file splitting), and notes the ~400-line sibling-split guidance, dated 2026-08-23, superseding the 2026-08-16 decision

## 4. Technical Constraints

> ⚠️ Describe WHAT is needed, not HOW. No class names, method signatures, DTO shapes, or endpoint paths.
> The implementing agents + architecture skill decide those.

* **Module organization**: Split `preview/layout.py` into four new sibling modules (geometry, segments, placement, persistence) plus a refactored `layout.py` that re-exports the public surface. No nested sub-packages.
* **Import direction**: Strictly one-directional: geometry (no imports from siblings) ← segments (imports geometry) ← placement (imports geometry and segments) ← persistence (imports geometry and placement) ← layout.py (pure re-export, no logic).
* **Public surface**: All 22 currently-public symbols must remain importable from `preview.layout` with identical names and behavior. No symbol may be renamed or moved to a different import path.
* **Private symbols**: All underscore-prefixed symbols are internal; they may be reorganized freely as long as no external caller or test reaches them (verified: none do).
* **Behavior preservation**: Zero behavior changes. All logic, constants, and defaults remain identical. The split is purely organizational.
* **No new dependencies**: The refactored code uses only the same imports as the original file.

## 5. Design & UI/UX

N/A — this is a pure refactor with no user-facing changes.

## 6. Scope & Context

### Concern grouping (audit-verified 2026-08-23)

**Geometry / coordinate math** (approx. 130 lines): Real-world truss polyline, coordinate normalization, bounding boxes, normalization frame serialization. Constants: `VERTICAL_SEGMENT_LENGTH_CM`, `DIAGONAL_SEGMENT_LENGTH_CM`, `TOP_SEGMENT_LENGTH_CM`, `DIAGONAL_ANGLE_DEG`, `GROUND_Y`, `SKY_Y`, `_MARGIN_FRACTION`. Symbols: `arch_outline_cm`, `normalize_rotation`, `normalized_arch_outline`, `normalized_structure`, `NormalizationFrame`, `frame_cm_to_dict`, plus private helpers.

**Truss segment classification** (approx. 90 lines): Walk the polyline classifying segments as vertical/diagonal/horizontal, map fractions to points along the segment chain, extract runnable segments, validate structure. Symbols: `_StructureSegment`, `_classify_segments`, `_point_along_segments`, `_run_segments`, `_validate_structure_cm`, `DegenerateStructureError`, plus constant `_ORIENTATION_EPS_CM`. Pure math on tuples; imports nothing from other concerns.

**Fixture placement** (approx. 280 lines): Mount every fixture onto the arch. Constants: `_PAR_GROUND_OFFSET_CM`, `_PAR_SPACING_CM`, `BAR_CHANNEL_SPAN`, `DEFAULT_PAN_DEGREES`, `DEFAULT_TILT_DEGREES`, `DEFAULT_TILT_BLOCK_ROTATION_DEGREES`, `KIND_BY_MASTER_ID`, `_EFFECT_SLOT_TYPE_ID`. Symbols: `_BarGroup`, `_bar_address_ranges`, `classify_fixture_kind`, `generate_layout` (209 lines, stays whole), `apply_prior_calibration`. Imports geometry and segments.

**JSON persistence / validation / migration** (approx. 240 lines): Load, save, diff, merge layouts. Symbols: `LayoutEntry`, `RigLayout`, `LayoutDiffEntry`, `LayoutMergeResult`, `load_layout`, `save_layout`, `load_layout_file`, `ensure_layout`, `layout_path_for_venue`, `layout_to_dict`, `layout_from_dict`, `InvalidSavedLayoutError`. Imports geometry and placement (for defaults and constants).

### Known coupling

- `generate_layout` (209 lines) touches 13 other symbols spanning all three concerns (geometry, classification, placement). It stays whole in placement and imports from the other siblings.
- `RigLayout` uses `arch_outline_cm()` as a default factory, hard-coupling persistence to geometry. This is the reason import direction cannot be reversed.
- `DEFAULT_PAN_DEGREES` and `DEFAULT_TILT_DEGREES` are read by both `generate_layout` (placement) and `layout_from_dict` (persistence migration fallback). They live in placement; persistence imports them.

### Misplaced symbols today

`KIND_BY_MASTER_ID` (dict constant, 6 lines) and `_EFFECT_SLOT_TYPE_ID` (constant, 1 line) sit at the top of the current file but feed only `classify_fixture_kind` (placement). They must move with placement, not be left stranded.

### No external changes

- `cli.py` and `payload.py` are untouched; they import from `preview.layout` unchanged.
- No test files are modified.
- No new dependencies are added.

## 7. Test Impact Analysis

### Existing tests affected by this change:

| Test File | Test Count | What it asserts | Conflicts? | Action |
|-----------|-----------|-----------------|------------|--------|
| `tests/preview/test_layout.py` | 103 test functions | Geometry, classification, placement, persistence, and integration across all concerns | NO | Keep unmodified; all imports are from `preview.layout` or `preview.layout.LayoutEntry`/`RigLayout` (public surface only) |
| `tests/preview/test_payload.py` | Multiple | Payload generation using `RigLayout`, `frame_cm_to_dict`, `normalized_structure` | NO | Keep unmodified; all imports are from `preview.layout` (public surface only) |

### Test modification policy:

- [x] No existing tests should be modified (this is a pure refactor)
- [ ] Existing tests MAY be updated where they assert behavior being moved (N/A)
- [ ] Specific files that may be modified: None

### Rationale for unmodified tests

The test suite imports only from the public surface (`from rbxlight.preview import layout` and `from rbxlight.preview.layout import LayoutEntry, RigLayout`). Zero private imports exist. Because the refactored `layout.py` re-exports all public symbols with identical names and behavior, all test imports resolve identically and all assertions remain valid without modification. This is the primary safety gate for the refactor.

### Existing files impacted (refactoring only)

| File | Impact |
|------|--------|
| `src/rbxlight/preview/layout.py` | Refactored from 955 lines of mixed concerns to a thin re-export facade (~50 lines) with explicit named imports |
| `.opencode/skills/rekordbox-lighting-architecture/SKILL.md` | Updated with clarification that flat means no nested sub-packages (not no file splitting), and ~400-line sibling-split guidance, dated 2026-08-23 |
| `.opencode/METADATA.md` (if it lists `preview/`) | Updated to include new sibling modules in the file tree |

## 8. Implementation Notes for Agents

### Required public surface (must be re-exported from `layout.py`)

`LayoutEntry`, `RigLayout`, `NormalizationFrame`, `LayoutDiffEntry`, `LayoutMergeResult`, `DegenerateStructureError`, `InvalidSavedLayoutError`, `arch_outline_cm`, `normalize_rotation`, `normalized_arch_outline`, `normalized_structure`, `frame_cm_to_dict`, `classify_fixture_kind`, `generate_layout`, `diff_layouts`, `apply_prior_calibration`, `load_layout`, `save_layout`, `load_layout_file`, `ensure_layout`, `layout_path_for_venue`, `layout_to_dict`, `layout_from_dict`.

### Import direction (strict, no exceptions)

```
layout_geometry.py (no imports from siblings)
    ↑
layout_segments.py (imports layout_geometry)
    ↑
layout_placement.py (imports layout_geometry, layout_segments)
    ↑
layout_io.py (imports layout_geometry, layout_placement)
    ↑
layout.py (pure re-export, no logic, no imports from siblings)
```

No sibling may import from `layout.py` itself. No circular imports.

### Ambiguous placements (decided)

- `DEFAULT_PAN_DEGREES`, `DEFAULT_TILT_DEGREES` → placement module (their conceptual home); imported by io module.
- `generate_layout` (209 lines) → placement module, stays whole, imports from other siblings.
- `KIND_BY_MASTER_ID`, `_EFFECT_SLOT_TYPE_ID` → placement module (feed `classify_fixture_kind`).

### Future hazard to document in review

If anyone later makes `layout_geometry.py` import a constant from `layout_placement.py`, a circular import appears. The architecture skill should note this as a review gate.

### Value statement

This refactor has no aesthetic value. Its value is that the file is the project's largest and still growing, that splitting later costs more than splitting now, and that the split is only safe today because no external caller and no test reaches past the public surface — a property that will not survive indefinitely.
