# Truss editing in the visualizer

**Completed:** 2026-08-16
**Epic:** MULTI_VENUE
**Source:** `.opencode/refined/MULTI_VENUE-truss-editing-in-visualizer.md`

## Summary

The truss stopped being a picture and became an editable object: select, drag, insert and delete
points in the visualizer, with real-world centimetre readouts, and export the result. A new
`rbxlight layout install` command ends the download-then-manually-move-the-file chore, with the same
dry-run-diff-first discipline as every other mutating command in the tool.

## Plan Approved by the user

### Requirements Summary

Two halves that only meet at a file format:

- **Browser (13 requirements):** click a truss point to select it (fixture selection clears, and
  vice versa); truss handle wins when a point and a fixture overlap; drag updates both the front
  elevation and the plan view live; double-click a segment to insert a point; delete a selected
  point, refused at two remaining points; out-of-bounds drags are accepted rather than clamped;
  keyboard nudge/insert/delete matching the affordance fixtures already had; centimetre readout of
  the selected point and the truss span; export carries the truss; reset restores fixtures *and*
  truss; unsaved edits are visible and warned about on tab close.
- **CLI:** `rbxlight layout install <path>` — refuse an invalid file, refuse a file belonging to a
  different venue, dry-run diff by default, atomic write behind `--write`, first-time-install
  messaging, and a choice when the file references fixtures no longer patched.

### Technical Approach

- **Backend:** `load_layout_file` + `InvalidSavedLayoutError` in `preview/layout.py`; `frame_cm`
  added to the preview payload; `layout install` command in `cli.py` reusing the existing venue
  resolver, `diff_layouts`, and the single atomic `save_layout` primitive. No schema change, no
  migration, no schema version field.
- **Frontend:** truss editing added to `preview/template.html` alongside the existing fixture
  editing idiom. No test phase — `skip_frontend_tests: true`; the visualizer is verified by opening
  a generated preview.

### Execution Order

| Phase | Agent | Task |
| ----- | ----- | ---- |
| 1 | backend-testing-agent | Tests for `load_layout_file`, payload `frame_cm`, `layout install` |
| 2 | backend-agent | Implement to pass |
| 3 | backend-optimizer-agent | Refactor |
| 4 | frontend-agent | Truss editing in `template.html` |
| 5 | frontend-optimizer-agent | Refactor |
| 6 | — | Visual verification in a browser |

## Four corrections made before any code was written

The refined story was wrong on four counts; research caught all four up front.

1. **"The visualizer currently applies a display-only recalibration that must be removed" — false.**
   `calibrateTrussX()` was already deleted in the previous story. The acceptance criterion was
   already satisfied. Verified absent, and explicitly guarded against reintroduction: the truss and
   the fixtures now share one normalization frame by construction, which is what made the hack
   unnecessary in the first place.
2. **All six test names the story supplied were invented.** `test_saved_layout_round_trip`,
   `test_atomic_write_on_interrupt`, `test_layout_diff_output`, `test_defaults_for_missing_fields`,
   `test_dry_run_by_default`, `test_generated_page_embeds_all_data` — none existed. Third
   consecutive story with fabricated test names; the real coverage was mapped by hand instead.
3. **The browser export never carried truss geometry at all.** `currentLayoutObject()` emitted only
   `{venue_id, entries}`. The story assumed truss export was a tweak; it was a gap.
4. **The browser had no centimetres at all.** The payload shipped normalized `[0, 1]` floats only,
   so the "real-world measurements" requirement needed the frame exposed first.

## Design decisions

- **Export format == saved-layout format.** The browser emits
  `{venue_id, entries, structure_cm, frame_cm}` and echoes `frame_cm` back untouched, so install is
  a straight parse. The rejected alternative — letting Python recompute the frame on ingest — would
  have changed what every fixture's normalized coordinate means and silently moved every light in
  the rig.
- **The frame is fixed during editing.** Never recomputed from edited geometry, for the same reason.
- **Truss handle wins over a fixture on overlap.** It is the smaller target.
- **Front elevation is the editing surface**; the plan view mirrors edits but stays render-only. The
  requirement asks it to update, not to be editable, and it has no inverse projection.
- **Out-of-bounds needs an unclamped projection path for the truss only.** Fixtures keep clamping.
- **A null `frame_cm`** (legacy file saved before frames existed) makes honest centimetres
  unrecoverable, so truss editing disables itself and points at `rbxlight layout regenerate --write`
  rather than inventing a frame. Fixture editing keeps working.

## Implementation

### Backend

- `preview/layout.py` — `InvalidSavedLayoutError(ValueError)` and `load_layout_file(path)`, which
  wraps parse and shape failures but deliberately lets the existing `DegenerateStructureError`
  propagate unchanged. Also `frame_cm_to_dict()`, extracted during optimization.
- `preview/payload.py` — payload gained `frame_cm`, mirrored from the layout, never recomputed.
- `cli.py` — `layout install <path> [--venue INT] [--write] [--yes]`. Shared venue resolver, working
  copy guard, file validation, venue-mismatch refusal naming both venues, fixture diff plus a
  distinct truss-shape-changed line, "new file" versus "no changes" messaging, an orphaned-fixture
  prompt (cancelling exits 0 having written nothing) skippable with `--yes`, dry run by default,
  atomic write through the existing `save_layout`.
- Optimizer extracted `_DRY_RUN_NOTICE` (previously inline five times), `_resolve_and_announce_venue`,
  `_layout_path`, `_load_existing_layout`, `_print_layout_diff_entry`.

### Frontend

`preview/template.html`, +~440 lines: truss selection with handles, drag on an unclamped projection
path, double-click segment insert, delete with the two-point floor enforced client-side, keyboard
nudge/insert/delete, cm readouts for the selected point and the span, live plan-view mirroring, the
dirty indicator plus a before-unload warning, the extended export, and reset covering both fixtures
and truss. Optimizer extracted `cloneCmPoints` and `insertTrussPointAt`, and deliberately left the
pointer/keydown handlers alone because in-scope truss logic interleaves with out-of-scope fixture
logic there and no JS test covers interaction behaviour.

### The bug that mattered

The orchestrator's own design note told the frontend agent to convert with
`cm = min + norm * (max - min)`. That is wrong. `_normalize_point` also reserves a 5% margin per
side **and flips the y-axis** (ground sits at the larger end of `[0, 1]`). Under the naive inverse a
ground-level `(0, 0)` cm point round-tripped to `(12.07, 209.67)` cm — near the top of a 221cm arch.

The consequence was not cosmetic and not limited to edited points: opening a layout and pressing
Download with **zero edits** would have exported silently corrupted `structure_cm`, and every
centimetre readout in the panel would have been wrong. Nothing catches this — the polyline is still
well-formed, so the CLI accepts it happily; it is simply wrong-but-plausible numbers. Fixed by
inverting both steps; round-trip error is now ~4e-14 cm across 1000 random points and exact against
the real generated arch.

This is the same failure shape the project has hit before: a rendering-layer coordinate assumption
that no test can see. It was caught by an agent auditing a generated payload numerically, not by the
suite.

### Deviations from Plan

- The first `frontend-agent` invocation was reported as aborted, but had in fact already written the
  feature to disk. The retry found the work in place, audited it against a real 27-fixture payload
  rather than rewriting it, and found the conversion bug. Net effect was a free review pass; worth
  remembering that an "aborted" tool call may still have had effects.
- One extra delegation not in the plan: a cross-reference comment added to `_MARGIN_FRACTION` after
  the bug (see Playbook Candidates).

## Agents Used

| Agent | Task | Result |
| ----- | ---- | ------ |
| deep-research-agent ×4 | Visualizer generation, layout persistence, CLI conventions, test impact | Complete — found all four story errors |
| backend-testing-agent | 40 tests across three files | Complete (35 failing, correct TDD state) |
| backend-agent | `layout install`, `load_layout_file`, payload `frame_cm` | Complete |
| backend-optimizer-agent | Deduplicate the two layout commands | Complete |
| frontend-agent | Truss editing in `template.html` | Complete — found and fixed the cm conversion bug |
| frontend-optimizer-agent | Refactor the truss additions | Complete |
| backend-agent | Cross-reference comment on `_MARGIN_FRACTION` | Complete |

## Files Modified

- `src/rbxlight/cli.py` — `layout install` command plus five extracted helpers
- `src/rbxlight/preview/layout.py` — `load_layout_file`, `InvalidSavedLayoutError`,
  `frame_cm_to_dict`, cross-reference comment on `_MARGIN_FRACTION`
- `src/rbxlight/preview/payload.py` — `frame_cm` in the payload
- `src/rbxlight/preview/template.html` — truss editing
- `tests/test_cli.py` — `TestLayoutInstallCommand` (28)
- `tests/preview/test_layout.py` — `TestLoadLayoutFile` (9)
- `tests/preview/test_payload.py` — 2 new, 1 updated (strict payload key set extended for `frame_cm`)

## Tests

- 40 tests written, 577 passing (was 537).
- Acceptance criteria covering browser interaction are not pytest-coverable and were verified by
  driving the real extracted script against a real generated payload in a DOM/canvas harness, plus
  manual browser checks.

## Playbook Candidates

No `/playbook` route exists — this is a CLI tool with one generated HTML page — so nothing is
route-eligible. Captured here instead:

- `insertTrussPointAt(segIndex, t)` and `cloneCmPoints(pts)` in `template.html` — helpers, not
  reusable UI components. Correctly colocated with the feature; recorded as the canonical
  "insert a point" pattern (splice, resync, mark dirty, select) for any future truss work.
- **The margin constant is mirrored across two languages.** `_MARGIN_FRACTION = 0.05` in
  `preview/layout.py` and `TRUSS_MARGIN_FRACTION = 0.05` in `preview/template.html` must change in
  lockstep or the visualizer silently exports wrong measurements. Guarded by cross-referencing
  comments on both sides — a convention, not a mechanism. Added to `.opencode/BACKLOG.md`; the real
  fix is shipping the margin in the payload, deferred because it reopens the strict payload-key-set
  test this story had just settled.
