---
epic: "MULTI_VENUE"
title: "Truss editing in the visualizer"
estimate: M
status: ready
created: 2026-08-15
depends_on: [ "MULTI_VENUE-per-venue-stage-description" ]
labels: [ frontend, cli, ux ]
priority: P2
claimed_by:
claimed_by_date:
---

## 1. User Story

**As a** lighting technician setting up the visualizer for my venue\
**I want** to see and edit the actual shape and position of my truss in the interactive preview\
**So that** I can verify the lights are rigged exactly where they hang in reality, without hand-editing JSON files\

## 2. Business Context & Value

The visualizer already lets users position individual fixtures by clicking and dragging them, then save those edits and export them for reuse. The truss — the physical metal structure the lights hang from — is drawn but read-only. With truss geometry now represented as real, persisted, per-venue data (from the dependency story), users have no way to edit it. They would have to manually edit JSON files to describe their rig, which defeats the point of an interactive tool.

This story makes truss editing part of the visualizer's existing interaction model: click to select, drag to move, insert/delete points, save in the same export that fixtures use. It also eliminates the friction of manually moving downloaded files by adding a CLI install command that puts a saved layout in the right place with safety guarantees.

The result: a unified editing experience where the user sees the true dimensions of their rig as they reshape it, and getting the edits back into the tool requires one command, not a file-manager search.

## 3. Acceptance Criteria

* [ ] **Truss selection is independent of fixture selection**
    * Given the visualizer is open with fixtures and truss rendered
    * When the user clicks on a truss point
    * Then the truss enters selected state (visually distinct), the previous fixture selection is cleared, and a side panel shows truss properties

* [ ] **Fixture selection is independent of truss selection**
    * Given a truss is selected
    * When the user clicks on a fixture
    * Then the fixture is selected, the truss is deselected, and the side panel switches to show fixture properties

* [ ] **Overlapping selection is predictable**
    * Given a truss point and a fixture overlap on screen
    * When the user clicks on the overlapping area
    * Then the selection outcome is consistent (e.g., truss takes priority, or fixture takes priority, but not random)

* [ ] **User can drag a truss point to move it**
    * Given the truss is selected and a point is visible
    * When the user drags a point by its clickable handle
    * Then the point follows the cursor in real time and the truss shape updates both in front-elevation and top-down plan views

* [ ] **User can insert a new truss point**
    * Given the truss is selected
    * When the user activates the insert action (e.g., double-click on a line segment, or activate via keyboard)
    * Then a new point is created at that position, and the truss geometry is updated to include it

* [ ] **User can delete a truss point**
    * Given the truss is selected and has more than two points
    * When the user activates the delete action on a selected point
    * Then the point is removed and the truss geometry updates

* [ ] **Deletion is prevented when it would create a degenerate truss**
    * Given the truss has exactly two points
    * When the user attempts to delete a point
    * Then the action is prevented or clearly rejected with an explanation (e.g., "A truss must have at least two endpoints")

* [ ] **Truss points are dragged outside the visible stage area**
    * Given the user drags a truss point far beyond the stage bounds
    * When the user releases the point
    * Then the geometry is accepted (the tool allows out-of-bounds truss), the view remains usable (no view-jumping), and the point is still editable

* [ ] **Real-world dimensions are visible while editing**
    * Given the truss is selected
    * When the user views the truss properties in the side panel
    * Then the side panel displays real-world measurements (e.g., point coordinates in centimetres, truss span length in centimetres)

* [ ] **Truss edits are live in both views**
    * Given the user is dragging a truss point
    * When the front-elevation view updates
    * Then the top-down plan view also updates simultaneously, so the user sees the full spatial effect of their edit

* [ ] **Keyboard accessibility is present for truss editing**
    * Given the truss is selected and a point is selected within it
    * When the user presses arrow keys or activates insert/delete via keyboard
    * Then the corresponding edit (nudge the point, insert, delete) is applied, matching the keyboard affordance already available for fixtures

* [ ] **Truss edits are included in the export**
    * Given the user has edited the truss and clicked save/export
    * When the browser produces a download file
    * Then the file includes the updated truss geometry in the format the CLI expects to read back

* [ ] **Reset restores both fixture and truss state**
    * Given the user has edited both the truss and fixtures
    * When the user activates the reset affordance
    * Then both the truss and fixtures are restored to their originally generated positions, and the page reflects the reset state

* [ ] **Unsaved edits are visually indicated**
    * Given the user has made truss or fixture edits but not exported
    * When the user looks at the page
    * Then unsaved state is visible (e.g., a "dirty" indicator, a warning on the export button, or a prompt if they attempt to close the tab)

* [ ] **Install command refuses invalid layout files**
    * Given the user runs the install command with a file that is not a valid saved layout
    * When the file is validated
    * Then the command refuses to proceed and prints a clear error message explaining what is wrong

* [ ] **Install command refuses wrong-venue files**
    * Given the user runs the install command to install a layout file into a venue it does not belong to
    * When the venue ids are checked
    * Then the command refuses to proceed and prints a clear error message (e.g., "This layout is for venue X, not venue Y")

* [ ] **Install command shows a diff by default (dry-run)**
    * Given the user runs the install command
    * When the command begins execution
    * Then it shows what will change (diff from current saved layout to new layout) without writing, and requires an explicit flag to actually write

* [ ] **Install command writes atomically**
    * Given the user runs the install command with the write flag
    * When the write operation is interrupted (e.g., process killed mid-write)
    * Then the saved layout file is either fully updated or unchanged, never truncated or partially written

* [ ] **Install command handles first-time install**
    * Given a venue has no existing saved layout
    * When the user runs the install command
    * Then the command proceeds (no current layout to diff against) and installs the layout, making it clear this is a new file

* [ ] **Install command rejects layouts with missing fixtures**
    * Given the user runs the install command with a layout that references fixtures no longer patched into the venue
    * When the layout is validated against the current venue fixture patch
    * Then the command shows which fixtures are missing and offers a choice to proceed or cancel

* [ ] **Clipboard export fallback works with truss edits**
    * Given the user has edited the truss and clicked the clipboard copy button
    * When the clipboard API is unavailable or fails
    * Then a fallback (e.g., a textarea with copy-to-clipboard instructions) is available and includes the full truss geometry

* [ ] **Visualizer remains a single self-contained offline file**
    * Given the truss editing feature is implemented
    * When the visualizer is generated and opened from the filesystem with no server
    * Then all truss editing, selection, dragging, and export functionality works without network calls or external assets

* [ ] **Display-only truss recalibration is removed**
    * Given the truss is user-editable
    * When the user edits the truss and then clicks or drags a fixture
    * Then the truss remains in the position the user placed it (no automatic recalibration stretches or moves it)

## 4. Technical Constraints

* **Frontend**: Vanilla JavaScript only, no framework, no build step, no external assets, no network calls. The page must remain a single self-contained file that works offline from the filesystem.
* **CLI/Python**: New install command that accepts a saved-layout file produced by the visualizer, validates it, shows a diff against the current saved layout for the target venue, and writes atomically with dry-run-by-default behaviour.
* **API**: N/A — no server, no endpoints. The visualizer and CLI communicate only through an exported file the user installs with the new command.
* **Database**: N/A — no rekordbox database schema changes. Truss geometry is this tool's own concept, stored only in per-venue saved layouts, never in rekordbox's databases.
* **Security**: N/A — local single-user offline tool.
* **Performance**: N/A — tens of fixtures and a handful of truss points.

## 5. Design & UI/UX

The truss editing experience should feel like the fixture editing that already exists: the same select-then-manipulate rhythm, the same side panel for the selected thing's properties, the same save row. When the truss is selected, it should be unmistakably obvious (visually distinct from the unselected truss), and interactions with it should never ambiguously affect fixtures or vice versa.

Truss points should be draggable with clear visual feedback (e.g., highlighted when hoverable, animated when being dragged). Insert and delete actions should be accessible both by mouse (e.g., double-click to insert, right-click to delete, or a context menu) and by keyboard (consistent with the existing arrow-key nudging for fixtures).

Real-world measurements (point coordinates, span length, all in centimetres) should be visible in the side panel while editing, because a rig that measures correctly is the entire point of this tool. The front-elevation and top-down plan views should update live as the user drags, so they see the full spatial effect in real time.

Do not redesign the transport controls, the playback behaviour, or the fixture editing that already works. This is an addition to an interface that already has a working idiom, not a redesign.

## 6. Scope & Context

**Existing behaviour that changes:**

The visualizer currently applies a display-only recalibration that stretches the drawn truss horizontally to line up with the on-screen positions of bar fixtures, so dragging a bar fixture does not make the truss appear to chase it. Once the truss is user-editable, that automatic recalibration would silently fight the user's own edits. This recalibration must be removed or reconciled before truss dragging can be trusted.

**Domain concepts and constraints:**

The saved-layout export already carries the venue id, so a produced file already knows which venue it describes. This is what allows the install command to verify a file is going to the right place.

The load-or-generate path writes the saved layout back as a side effect (for preview generation), while the regeneration command deliberately loads read-only to keep its dry-run promise. The new install command must not disturb that distinction.

Macros are venue-agnostic — they address fixed fixture slots, not physical positions — so nothing about macro generation or playback is affected by truss shape changes.

**Known pitfalls:**

A real bug in this project's history was found by generating an actual preview and looking at it, not by the test suite. Visual verification of the generated HTML is a required part of finishing this story. Do not rely on automated testing alone.

## 7. Test Impact Analysis

### Existing tests affected by this change:

| Test File | Test Method | What it asserts | Conflicts? | Action |
|-----------|------------|-----------------|------------|--------|
| Python test suite | `test_saved_layout_round_trip` | Layout can be loaded, modified, and saved | NO | Keep passing (truss geometry now part of round-trip) |
| Python test suite | `test_atomic_write_on_interrupt` | Atomic writes guarantee | NO | Keep passing (install command uses same atomic write) |
| Python test suite | `test_layout_diff_output` | Diff is printed before write | NO | Keep passing (install command shows diff) |
| Python test suite | `test_defaults_for_missing_fields` | Old layout files without truss field load safely | YES | Update to handle truss field defaulting |
| Python test suite | `test_dry_run_by_default` | Command shows output without writing | NO | Keep passing (install command follows pattern) |
| Python test suite | `test_generated_page_embeds_all_data` | Visualizer references no external assets | NO | Keep passing (truss data is embedded, no new network calls) |

### Test modification policy:

- [ ] Existing tests for atomic writes are FROZEN — they may not be weakened.
- [ ] Existing tests for dry-run-by-default behavior are FROZEN — they may not be weakened.
- [ ] Existing tests for self-contained offline output are FROZEN — they may not be weakened.
- [x] Existing tests MAY be updated where they assert behavior being moved or extended (e.g., layout round-trip tests now include truss geometry).
- [ ] New tests must cover the install command (validation, diff, atomic write, edge cases).

### Existing files impacted (refactoring only)

| File | Impact |
|------|--------|
| Visualizer HTML template | Add truss selection state and side panel. Add truss point drag handling, insert/delete affordances, and keyboard support. Update front-elevation and plan rendering to reflect truss edits live. Include truss geometry in export payload. Update reset affordance to restore truss. Remove display-only truss recalibration. Add unsaved-state indicator. Ensure single self-contained file remains offline-capable. |
| CLI module (install command) | New command that loads a saved-layout file from user input, validates format and venue id, loads current saved layout (if exists) for diff, shows diff output, requires explicit flag to write, and writes atomically. Reuse existing layout-loading and atomic-write primitives. |

> Do NOT list files to be created — new file structure and test files are decided by the implementing agents using the project's architecture skill.

### Visual verification requirement

This story includes an interactive feature. Before marking it complete, generate the visualizer HTML, open it in a browser, and manually verify:
1. Truss points are selectable and draggable independently of fixtures.
2. Dragging a truss point updates both the front-elevation and top-down plan views.
3. Insert and delete actions work as designed.
4. Reset restores the original truss shape.
5. Real-world measurements display correctly in the side panel.
6. The exported file includes truss geometry and can be installed via the new CLI command.
