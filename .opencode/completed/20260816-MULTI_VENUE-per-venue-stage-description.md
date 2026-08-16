# Per-venue stage description — truss geometry becomes data

**Completed:** 2026-08-16
**Epic:** MULTI_VENUE
**Source:** `.opencode/refined/MULTI_VENUE-per-venue-stage-description.md` (deleted on completion)

## Summary

The physical structure lights hang from stopped being an assumption baked into four constants and
became saved, per-venue, user-owned data: a polyline of vertices in centimetres. Fixture
auto-placement was generalized from "two verticals, two diagonals and a top" to segment-role
classification over any polyline, and the long-standing dual-bounding-box normalization bug — which
the renderer had been silently papering over — was fixed at the source.

## Plan Approved by the user

### Requirements Summary

- Truss persists per venue as a cm polyline; survives runs; loaded not regenerated
- Missing truss in older files → default 5-segment arch, no behavior change
- Auto-placement generic to any polyline (via segment roles), arch behavior preserved exactly
- Truss is user-owned: regeneration preserves it unless explicitly asked to reset
- Truss + fixtures normalized into one 0..1 frame; payload contract unchanged
- Atomic writes and dry-run guarantees do not regress
- Degenerate truss (<2 points, all-identical, non-finite) → clear actionable error on load
- Venue isolation preserved

### Technical Approach

- **Backend:** `RigLayout` gains `structure_cm` (cm polyline) + `frame_cm` (persisted normalization
  frame). `layout_from_dict` defaults both via the existing optional-field precedent. Placement
  replaces positional `p1..p5` unpacking with segment-role classification. The two normalization
  passes unify into one shared frame. `payload.py` sources `"truss"` from `normalized_structure()`.
  `layout regenerate` treats structure as user-owned and gains `--reset-structure`.
- **Frontend:** delete the `calibrateTrussX()` IIFE and its now-stale comment block.
- **DB:** no changes, zero `.db3` writes.

### Execution Order

| Phase | Agent | Task |
|---|---|---|
| 1 | backend-testing-agent | Update conflicting tests + write new truss tests (will fail) |
| 2 | backend-agent | Implement geometry/persistence/payload/CLI |
| 3 | backend-optimizer-agent | Refactor for maintainability |
| 4 | frontend-agent | Remove `calibrateTrussX` from `template.html` |

Sequential — phases 1-3 all touch `layout.py`, so no parallelization was possible.

## Three story corrections found during research

The refined story was written against a codebase structure that does not exist. Recording this
because it is a refinement-process lesson, not a one-off:

1. **Every file path in the story was wrong.** It named `rbxlight/layout/geometry.py`,
   `layout/saved_layout.py`, `cli/layout_cmd.py`, `preview/payload_builder.py`. None exist.
   Geometry, placement, normalization and persistence are all one module,
   `src/rbxlight/preview/layout.py`; the CLI is one flat `cli.py`.
2. **The saved layout is JSON, not YAML**, and has no schema version field. Backward compatibility
   is per-field `data.get(key, default)`.
3. **All nine test names the story listed as affected were invented.** None existed verbatim. The
   suite uses `Test<Subject>` classes with `test_should_<behavior>` methods. The story's "FROZEN"
   marker is not a repo convention either. Real names were mapped before any test was touched.

## Two design decisions the story left unresolved

Both were surfaced at the approval gate rather than guessed at.

1. **Scenario 3 contradicted the tests it told us to keep.** It asked for fixtures "distributed
   along the truss line in DMX order, no remaining assumption about arch segments" — but 18 existing
   tests assert *semantic* placement (heads on diagonals, bar cells grouped by DMX range onto
   verticals, pars on the ground outside the footprint). A literal arc-length walk would have
   destroyed all of it. Resolved by **segment-role classification**: classify each segment by
   orientation and length, then apply the existing per-kind rules to roles rather than fixed
   indices. The default arch reproduces today's output exactly; a straight run distributes along
   the run. Both requirements satisfied without a special case.

2. **Scenario 5 was impossible as written.** Truss and fixtures were normalized against two
   different bounding boxes, and the fixtures' cm frame was discarded at save time — so it was not
   recoverable at payload-build time. Resolved by **persisting the cm frame** (`frame_cm`)
   alongside the geometry, one field the story had not budgeted for. The alternative — normalizing
   fixtures against the truss bbox alone — would have pushed ground pars outside 0..1 and clipped
   them.

## Implementation

### Backend

- `NormalizationFrame` frozen dataclass (`min_x/max_x/min_y/max_y`, cm).
- `RigLayout.structure_cm` + `.frame_cm`, both defaulted for backward compatibility.
- `_classify_segments()` tags each polyline segment vertical/horizontal/diagonal by dx/dy against an
  epsilon. Moving heads take one diagonal each at that segment's own `atan2` angle — the arch's ±45°
  now falls out of the geometry instead of being hardcoded. Bars take one vertical each when
  verticals suffice (reproducing the arch's left/right-leg behavior), otherwise fall back to
  equal-width zones along the run with cells confined to the zone's middle 60%.
- `arch_width = p5[0]` generalized into `_structure_bounds()`.
- Single shared normalization frame (structure ∪ fixture positions) replaces the dual-bbox bug.
- `normalized_structure(layout)` maps cm → 0..1 through `frame_cm`, falling back to self-bbox for
  legacy files.
- `DegenerateStructureError(ValueError)` on <2 vertices, all-identical vertices, or non-finite
  coordinates.
- `layout regenerate` gains `--reset-structure`; structure is carried forward via the same
  `prior := old_present_by_id.get(...)` idiom already used for pan/tilt, and reports its status in a
  separate print branch (the existing `diff_layouts` deliberately does not carry user-owned fields).

### Frontend

- `src/rbxlight/preview/template.html`: removed lines 488-519 — the `calibrateTrussX()` IIFE and the
  comment block documenting the bounding-box mismatch it compensated for. The truss now arrives
  already correct and is drawn as-is.

### Bugs found and fixed en route

- **`_normalize_point` divided by zero on a zero-height frame.** A straight horizontal structure has
  zero vertical extent, so the first person to use a flat truss would have hit a crash. A degenerate
  axis now maps to the centre fraction. This was latent and unreachable before this story, because
  the only possible structure was the arch.
- **The renderer's truss recalibration was about to become actively harmful.** While the truss was
  always the arch, stretching it onto the two bars was a harmless cosmetic correction. The moment a
  user could save a goalpost or asymmetric shape, that same code would have silently overridden the
  geometry they deliberately saved. The story classified this as out-of-scope debt; it was in fact a
  precondition for Scenario 5 being true, so it was removed here.

### Deviations from Plan

- **`ensure_layout()` also preserves a saved custom structure.** No test required this and the story
  only specified the `layout regenerate` path. Without it, running `preview` would have silently
  reset a structure that `layout regenerate` promises to protect — exactly the trap this story
  exists to close. Flagged at the review gate and approved.
- **`layout.py` was not split into geometry/placement/persistence modules.** The plan anticipated
  the optimizer would do this. It declined, correctly, on the grounds that the project's
  architecture skill mandates a flat structure. The module is now 897 lines; noted in the backlog
  rather than forced.

## Agents Used

| Agent | Task | Result |
|---|---|---|
| deep-research-agent ×5 | Parallel scan: geometry, persistence, payload/visualizer, CLI, test coverage | Complete — surfaced all three story corrections |
| backend-testing-agent | 31 new/updated tests | Complete |
| backend-agent | Implementation | Complete — 537 passing |
| backend-optimizer-agent | Refactor + dead-code sweep | Complete |
| frontend-agent | Remove `calibrateTrussX` | Complete |

## Files Modified

- `src/rbxlight/preview/layout.py` — structure/frame data model, segment-role placement, unified
  normalization, validation, persistence, `apply_prior_calibration()`
- `src/rbxlight/preview/payload.py` — `"truss"` sourced from `normalized_structure()`
- `src/rbxlight/cli.py` — `--reset-structure`, structure preservation and status reporting
- `src/rbxlight/preview/template.html` — removed the recalibration IIFE
- `tests/preview/test_layout.py`, `tests/preview/test_payload.py`, `tests/test_cli.py`

## Tests

537 passing (was 506). 31 added across shape-generic placement (straight, goalpost, asymmetric),
structure round-trip and frame persistence, legacy-file defaulting, degenerate-structure validation,
shared-frame normalization, `--reset-structure`, and cross-venue isolation.

`mise run check` (ruff + mypy + pytest) green.

## Playbook Candidates

None — this is a CLI tool with no reusable UI component surface.
