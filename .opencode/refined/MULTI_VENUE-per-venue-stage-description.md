---
epic: "MULTI_VENUE"
title: "Per-venue stage description — truss geometry becomes data"
estimate: L
status: ready
created: 2026-08-15
depends_on: [ ]
labels: [ backend, data-model, migration ]
priority: P1
claimed_by:
claimed_by_date:
---

## 1. User Story

**As a** lighting technician with a custom-shaped rig (not the standard 5-segment arch)\
**I want** to save and reuse my truss geometry across tool runs\
**So that** the tool can auto-place and visualize fixtures correctly for my specific rig shape, rather than always assuming the arch\

## 2. Business Context & Value

The tool currently models only one physical rig: a specific 5-segment arch shape. That shape is hardcoded as four constants and regenerated from scratch on every load, never saved anywhere. Worse, the fixture auto-placement algorithm is built into those arch assumptions — it mounts moving heads on diagonals, bars on verticals, and pars on the ground. This locks the entire tool to one rig.

Any technician with a straight overhead truss, a goalpost structure, or two separate towers cannot truly use this tool — their fixtures get mounted in nonsensical places because the placement logic has no concept of their actual rig shape. They are forced to hand-drag every fixture into place, which is impractical for 20+ fixtures.

By making truss geometry a first-class, persisted, user-owned concept — one that can be customized per venue and survives across runs — the tool becomes usable for any rig. The default arch remains a starting point, not a prison. A technician can define their rig shape once, and fixture auto-placement adapts to it automatically.

This is the foundation story for multi-venue support: venues are distinguished by their patched fixtures *and* by the physical shape of the structure those fixtures hang from.

## 3. Acceptance Criteria

* [ ] **Scenario 1: Truss geometry is persisted and survives across runs**
    * Given a venue with a saved custom truss shape (a straight horizontal run)
    * When the tool loads that venue and reads its saved layout
    * Then the truss geometry is loaded from the saved file, not regenerated from constants, and matches the stored shape exactly

* [ ] **Scenario 2: Older saved layouts without truss data load successfully**
    * Given a saved-layout file written before this change, containing fixture positions but no truss geometry
    * When the tool loads that file
    * Then the file loads without error and the venue gains the default 5-segment arch as its truss, so existing users see no change in behavior

* [ ] **Scenario 3: Fixture auto-placement adapts to any truss shape**
    * Given a venue with a saved straight horizontal truss and a set of patched moving heads and bar fixtures
    * When fixtures are auto-placed onto that truss
    * Then they are distributed along the truss line in DMX order, with no remaining assumption about arch segments — the placement algorithm is generic to any polyline shape

* [ ] **Scenario 4: Truss geometry is user-owned and preserved by layout regeneration**
    * Given a venue whose saved layout contains both fixture positions and a custom user-edited truss
    * When layout regeneration is run (either dry-run or with write)
    * Then the truss geometry is preserved unchanged — it is not reset or regenerated — unless the user explicitly requests truss regeneration

* [ ] **Scenario 5: Visualizer payload continues to work with no coordinate-system change**
    * Given a venue with persisted truss geometry stored in real-world centimetres
    * When the preview payload is built for rendering
    * Then the truss coordinates are normalized to the same 0..1 frame as fixture positions, so the renderer needs no changes and the visualization is correct

* [ ] **Scenario 6: Saved layouts remain atomic**
    * Given a venue's saved layout being written to disk
    * When a write operation is interrupted or crashes mid-operation
    * Then the on-disk file is either completely unchanged or completely updated — never truncated or half-written

* [ ] **Scenario 7: Truss geometry is validated on load**
    * Given a saved-layout file with a degenerate or malformed truss (fewer than two points, all points identical, or invalid coordinates)
    * When the tool loads that file
    * Then a clear, actionable error is raised that identifies the problem, rather than proceeding to a crash or broken drawing

* [ ] **Scenario 8: Two venues do not leak truss geometry into each other**
    * Given two venues in the tool's working directory
    * When one venue is added, renamed, or its truss is modified
    * Then no truss geometry from the first venue affects the second, and vice versa

* [ ] **Scenario 9: Existing layout-regeneration workflow contract is preserved**
    * Given a layout regeneration run
    * When the user has not specified otherwise
    * Then the operation is dry-run by default, prints a diff before any write, preserves user-owned pan/tilt hardware calibration, and resets only algorithm-owned values

* [ ] **Edge Case: Single-point or zero-length truss**
    * Given a saved truss with only one point or where all points are identical
    * When that layout is loaded
    * Then an error is raised (degenerate truss), not a silent zero-length line or crash

* [ ] **Edge Case: Many fixtures on a short truss or few fixtures on a long truss**
    * Given a venue where fixture count and truss length are severely mismatched
    * When auto-placement runs
    * Then fixtures are still distributed along the truss line in order, even if they overlap or leave large gaps — no special-case code paths

* [ ] **Edge Case: Fixture removed from the rekordbox patch after layout save**
    * Given a saved layout containing a fixture whose DMX address is no longer patched in the current rekordbox venue
    * When layout regeneration runs
    * Then the orphaned fixture is reported in the diff output (existing behavior), not silently kept or deleted

* [ ] **Edge Case: Venue with zero patched fixtures but a saved truss**
    * Given a venue where no fixtures are currently patched, but a truss shape is saved
    * When the layout is loaded
    * Then the truss loads and persists correctly, even though there are no fixtures to place

## 4. Technical Constraints

* **API**: N/A — this is a local library and CLI change, no network API.

* **Data/Persistence**:
  * Per-venue saved-layout file gains persisted truss geometry in real-world centimetres.
  * Truss is stored as a polyline of vertices (points with X, Y coordinates).
  * Backward compatible: existing saved layouts without truss data default to the standard 5-segment arch.
  * **NO rekordbox database schema changes** — the truss is this tool's own concept and must never be written into rekordbox's macro.db3, user.db3, or master.db3 files.
  * Fixture positions themselves remain normalized 0..1 as they are today; only truss geometry is stored in centimetres. This asymmetry is intentional: fixture positions are relative to the truss, while truss itself is absolute physical reality.

* **Purity**: Geometry generation, fixture placement, truss normalization, layout diffing, and validation must remain pure functions with no database access, per the project's layering rule (cli → venues/ → repo → db → safety).

* **Security**: N/A — this is a local, single-user, offline tool. No authentication or authorization changes needed.

* **Performance**: N/A — tool handles tens of fixtures and single-digit venue counts. No performance constraints.

* **Safety**: Mandatory data-safety rules apply to rekordbox database files. This story writes only to the tool's own working directory (saved-layout files), never into rekordbox files. Existing atomic-write and dry-run guarantees must not regress.

## 5. Design & UI/UX

**No visual editing in this story.** This is the data model and generation/persistence half only.

The user-facing truss drawing and interactive editing experience (dragging, resizing, rotating the truss in the visualizer) is a **separate future story** ("Truss editing in the visualizer") that consumes what this story produces.

The only user-visible surface here is **CLI output**: the layout-regeneration diff should make it clear when truss geometry is (or is not) being changed — e.g., "Truss: unchanged" vs. "Truss: regenerated to default arch" vs. "Truss: preserved".

## 6. Scope & Context

### Existing behavior affected by this change

* **Visualizer's display-only truss recalibration**: The visualizer currently performs a horizontal stretch calibration, automatically fitting the drawn truss to the on-screen positions of the two bar fixtures. Once truss geometry is real, saved, and user-owned, that automatic recalibration is **actively wrong** — it would silently override the user's saved shape on screen. This recalibration must be reconciled (e.g., removed, or made into an optional reset-to-default function) as part of making truss data authoritative. Note this as a known issue that must be addressed in parallel or shortly after.

* **Layout regeneration workflow**: Currently resets fixture position, rotation, label and kind; preserves pan/tilt hardware sweep calibration; reports orphaned fixtures; and only writes when explicitly told. All of that behavior must survive unchanged.

* **Preview command's side effects**: The preview command's load-or-generate path currently always writes the layout file back as a side effect of loading, whereas the regeneration command deliberately loads read-only to keep its dry-run promise. That distinction is load-bearing and must not be collapsed.

* **Fixture coordinates remain normalized**: Fixture positions themselves stay as normalized 0..1 relative coordinates (relative to truss bounding box). Only truss geometry is stored in real-world centimetres. This asymmetry is intentional: fixtures are relative placements on the truss, while the truss itself is an absolute physical description.

* **Macros are unaffected**: Macros are venue-agnostic — they address 25 fixed fixture slots, not physical positions — so macro generation and macro fixture assignment are entirely unaffected by truss geometry changes.

### Design decisions already made (respect these; do not reopen)

1. **Auto-placement stays.** When a venue has a custom truss shape, fixtures must still be auto-placed onto it, distributed along the truss run in a generic way driven by fixture kind and DMX address order. Rejected alternative: keep auto-generation arch-only and force users to hand-drag every fixture. Reason: the user's real rig has 27 fixtures; hand-placing all of them makes a tool get abandoned.

2. **Truss geometry is stored in real-world centimetres**, and normalized only at the point where the visualizer payload is built. Rejected alternative: store normalized 0..1 coordinates like fixture positions. Reason: normalized geometry cannot distinguish a 3-metre truss from a 12-metre one, and that information is lost permanently once users start saving custom shapes.

3. **Truss is a polyline of vertices**, not a set of discrete truss pieces with lengths and angles. Rejected alternative: model individual pieces the way a rigger thinks about them. Reason: vertices reach every shape for a fraction of the complexity, and the renderer only ever needs the resulting line.

4. **The current arch remains the default.** A venue with no saved truss gets the existing 5-segment arch generated as a starting point. It becomes a default, not a law.

## 7. Test Impact Analysis

This is a refactoring and data-model extension of existing behavior.

### Existing tests affected by this change

| Test File | Test Method | What it asserts | Conflicts? | Action |
|-----------|------------|-----------------|------------|--------|
| layout/test_geometry.py | test_arch_shape_matches_segments | The hardcoded arch produces the expected 5-segment polyline | YES | Update: assert this is the _default_ arch, not the only arch. Keep the assertion that the default shape is correct. |
| layout/test_geometry.py | test_fixture_placement_on_arch | Moving heads and bars are placed on specific arch segments | YES | Update: re-frame as "default arch" test. Add new tests for placement on straight horizontal, goalpost, and custom shapes. |
| layout/test_saved_layout.py | test_round_trip_fixture_positions | Fixtures survive save and load | NO | Keep unchanged — this test encodes atomicity and must not regress. |
| layout/test_saved_layout.py | test_older_file_missing_fields_default_correctly | Missing fields from older files are populated with defaults | NO | Keep unchanged — this is the precedent for handling truss. This test is frozen. |
| layout/test_saved_layout.py | test_atomic_write_survives_interrupt | Interrupted writes leave the file unchanged, not truncated | NO | Keep unchanged — this is a critical safety guarantee that must not regress. |
| preview/test_payload_normalization.py | test_truss_normalized_to_unit_square | Truss is normalized to 0..1 for rendering | NO | Keep unchanged — the payload contract is unchanged. The normalization source changes (from constants to saved data), but the output shape is the same. |
| cli/test_layout_regeneration.py | test_dry_run_by_default | Regeneration is dry-run unless explicitly written | NO | Keep unchanged — this is a critical UX guarantee. May gain assertions about truss preservation. |
| cli/test_layout_regeneration.py | test_diff_printed_before_write | Layout diff is printed for review | NO | Keep unchanged. May gain assertions about truss diff entries. |
| cli/test_layout_regeneration.py | test_pan_tilt_calibration_preserved | Hardware calibration is not reset by regeneration | NO | Keep unchanged — user-owned data must survive. Same principle applies to truss. |

### Test modification policy

- [x] Existing tests MAY be updated where they assert behavior being moved
- [x] Specific files that may be modified: `layout/test_geometry.py`, `layout/test_saved_layout.py`, `preview/test_payload_normalization.py`, `cli/test_layout_regeneration.py`
- [x] **Frozen tests (may not be weakened or deleted)**: 
  - `test_round_trip_fixture_positions` (atomicity)
  - `test_older_file_missing_fields_default_correctly` (backward compatibility)
  - `test_atomic_write_survives_interrupt` (data safety)
  - `test_dry_run_by_default` (UX contract)
  - `test_diff_printed_before_write` (UX contract)
  - `test_pan_tilt_calibration_preserved` (user data preservation)

### Existing files impacted (refactoring only)

| File | Impact |
|------|--------|
| `rbxlight/layout/geometry.py` | Hardcoded arch constants become defaults. Fixture auto-placement becomes shape-generic (distributes along any polyline, not just arch). Truss normalization logic extracts from generation and applies to loaded data. |
| `rbxlight/layout/saved_layout.py` | Schema gains persisted truss geometry (polyline of vertices in centimetres). Load logic defaults to standard arch if truss is missing (backward compatibility). Validation enforces minimum two vertices, non-degenerate. |
| `rbxlight/preview/payload_builder.py` | Normalizes persisted truss geometry (in centimetres) to 0..1 frame for the renderer, same as it does for fixtures. No change to output shape. |
| `rbxlight/cli/layout_cmd.py` | Regeneration diff reports truss status (unchanged, regenerated, preserved). Truss is marked user-owned and only reset if user explicitly requests it. |
| `rbxlight/visualizer/template.html` | Display-only truss recalibration logic is flagged as now-incorrect and must be reconciled (removed or converted to optional reset function) — out of scope for this story but a known debt. |

> Do NOT list new files to be created — the implementing agents decide file structure using the project's architecture skill.
