---
epic: "FUTURE"
title: "FullArcAI — a third venue profile that breaks the bar mirror"
estimate: L
status: ready
created: 2026-08-23
depends_on: ["RIG-calibration-session", "FUTURE-bank-takeover-first-pass"]
labels: [venue, fixture-assignment, bar-decomposition, data-safety]
priority: P2
claimed_by:
claimed_by_date:
---

## 1. User Story

**As a** lighting designer\
**I want** to assign bar 1's cells and bar 2's cells to different macro fixture slots\
**So that** the two vertical legs can be driven independently, enabling vertical chases, opposed motion, and phase-shifted effects that are impossible when both bars are hard-mirrored to the same slot sequence.

## 2. Business Context & Value

### The Correction

The original pitch claimed `FullArcAI` would unlock "a continuous left-to-right sweep across all 18 bar cells". **That rationale is physically impossible and the original plan must not be built.** Both L1015 bars are mounted VERTICALLY, on the inside face of the two 150cm arch legs. Their cells run UP THE POLE. There is no shared horizontal axis between them — each bar's 9 cells can only move up and down its own leg. A left-to-right sweep across 18 cells was never available.

What survives from the original pitch is the *arithmetic*, which is still valid and still the real reason to do this. What needs replacing is the *motion goal*.

### The Real Value

Today, every bar effect is symmetric by construction. Both bars run the identical cell-to-slot sequence: cells 1–9 map to Mirrorball Spot, Bar Light 1, Moving Head 1, Par Light 2, Bar Light 2, Moving Head 2, Par Light 3, Bar Light 3, Moving Head 3. Because the sequence is identical, cell N of bar 1 and cell N of bar 2 always play identically. **The two bars can never do anything different from each other.**

Breaking the mirror unlocks the motion vocabulary the rig genuinely has:
- **Vertical rises and falls per leg** — a chase up one leg, since cells run up the pole.
- **Mirrored vs opposed legs** — one leg rising while the other falls, which is impossible today because the legs are hard-mirrored.
- **Offset legs** — the same rise on both legs, phase-shifted, reading as motion across the arch even though no cell moves horizontally.
- **Horizontal bar sweeps** via the tilt blocks, which tilt each whole bar as a unit and are already separate fixtures.
- **The four heads moving in 3D**, on the two diagonals and the top, independent of the bars.

After this story, symmetry becomes a *choice*, not a constraint.

## 3. Acceptance Criteria

* [ ] **Scenario 1: Venue creation with explicit slot assignment**
    * Given the working copy of `user.db3` with venues 2 and 3 intact
    * When the user creates a new venue `FullArcAI` with a deliberately non-mirrored `macro_fixture_id` assignment for bar 1 and bar 2
    * Then exactly 27 fixture rows are written (4 heads + 2 tilt blocks + 18 cells + 3 pars), and the cell-to-slot assignment differs between bar 1 and bar 2

* [ ] **Scenario 2: Slot collision reporting**
    * Given a proposed assignment that requires sharing slots among fixtures
    * When the user runs the dry run
    * Then all collisions are reported explicitly (which fixtures share which slots), and the count of collisions matches the reviewed, intended set

* [ ] **Scenario 3: 25-slot invariant maintained**
    * Given the new venue with 27 fixtures
    * When the user inspects the `macro_fixture` table
    * Then exactly 25 rows exist, and every fixture has exactly one `macro_data` row per slot (25 rows per fixture)

* [ ] **Scenario 4: Dry run shows complete assignment table without writing**
    * Given a proposed venue configuration
    * When the user runs the dry run (default behavior)
    * Then the complete cell-to-slot assignment table is displayed for review, and no changes are written to the database

* [ ] **Scenario 5: Venues 2 and 3 remain byte-identical**
    * Given venues 2 (`FullArcCustomBars`) and 3 (`FullArc2`) before the operation
    * When the new venue is created
    * Then venues 2 and 3 are byte-identical to their state before the operation

* [ ] **Scenario 6: ExecVenueId and LastSelectedVenue untouched**
    * Given `ExecVenueId=2` and `LastSelectedVenue=2` before the operation
    * When the new venue is created
    * Then `ExecVenueId` and `LastSelectedVenue` remain unchanged

* [ ] **Scenario 7: Preview renders the new venue**
    * Given the new venue has been created
    * When the user runs preview against the new venue
    * Then the layout renders correctly, showing the new cell-to-slot assignment in effect

* [ ] **Scenario 8: Venue removal is clean and reversible**
    * Given the new venue exists
    * When the user removes it
    * Then the database is restored to its state before creation, and venues 2 and 3 remain intact

* [ ] **Scenario 9: User can confirm on the real rig**
    * Given the new venue is active in rekordbox
    * When the user plays a macro that drives bar 1 and bar 2 differently
    * Then the two legs perform different actions (e.g., one rises while the other falls)

* [ ] **Edge Case: Unpatched 4th par remains unreachable**
    * Given the 4th par has no DMX address
    * When the new venue is created
    * Then the 4th par is not assigned to any slot and remains unreachable

## 4. Technical Constraints

> ⚠️ Describe WHAT is needed, not HOW. No class names, method signatures, DTO shapes, or endpoint paths.
> The implementing agents + architecture skill decide those.

* **Database**: Persist a new venue row in `user.db3` with 27 fixture rows, each with a deliberately chosen `macro_fixture_id` slot assignment. The assignment must be expressed as data (declarative table or spec), not buried in imperative code, so it can be diffed, reviewed, and revised.

* **Slot assignment logic**: Implement a mechanism to assign bar 1's cells and bar 2's cells to different subsets of the 25 available macro fixture slots. The recommended starting proposal is to share slots among the 3 pars and/or double up only the two outermost cells (1 and 9) rather than mirroring all 9 — reducing mirrored pairs from 9 down to 2. This is a proposal, not a mandate; the assignment table must be written out explicitly and reviewed before any write.

* **Dry run capability**: Render the full proposed assignment table before anything is written. Dry run is the default; `--write` must always be explicit.

* **Data safety**: Guard that rekordbox is not running, back up the database, write in ONE transaction, verify by re-read, and report the restore command. Never write `master.db3`. Never touch `macro_old.db3` or `master_old.db3`.

* **Reversibility**: Creating a venue must not disturb venue 2 or venue 3, and removing it must leave the database as it was. Must not change `ExecVenueId`.

* **Preview integration**: The new venue must be renderable via the existing preview system so the result can be judged offline before it is ever played.

* **Working copy model**: Work against the disposable working copy, with `push --write` as the only path to the live database.

## 5. Design & UI/UX

The user interaction is:
1. User runs a command to create the new venue with a proposed slot assignment (or accepts a default proposal).
2. Dry run displays the complete assignment table for review.
3. User confirms the assignment or adjusts it.
4. User runs the command with `--write` to persist the changes.
5. User can preview the new venue offline before switching to it in rekordbox.
6. User switches to the new venue in the rekordbox UI and tests on the real rig.

The assignment table should be human-readable and reviewable, showing which cells map to which slots and which slots are shared.

## 6. Scope & Context

### What exists and must not change

- **Venue 2 (`FullArcCustomBars`)** is currently ACTIVE (`ExecVenueId=2`, `LastSelectedVenue=2`). It decomposes each L1015 into a tilt-block sub-fixture (Super Storm1500B Tilt, 6 channels) plus 9 pixel-bar cell sub-fixtures (18x10W Pixel Bar, 4 channels). This decomposition is the key trick that lets rekordbox's macro system drive the 9 cells independently. It must never be "fixed" or simplified.

- **Venue 3 (`FullArc2`)** is the honest patch, each L1015 declared as one 43-channel fixture. Simple, but the bar is then a single movable block with no per-cell control.

- **The 25 fixture slots** are fixed: `macro_fixture` holds exactly 25 rows, and every macro has exactly one `macro_data` row per slot. This 25-row invariant must hold on every write. 11 of the 25 slots are currently unused and are the resource this story spends.

- **Slot sharing is not a defect.** When a bar cell (4 channels, with no pan, tilt, or gobo channels) sits on a Moving Head slot, it silently discards that macro's Position, Rotate, and Gobo data — only Brightness, Colour, and Strobe reach it. This is the *intended* mechanism for visual variety. Never "fix" this by matching slot sections to fixture capability.

### Physical rig facts (audit-verified)

- **Hardware**: 4x LM70S moving head (14 channels each, at DMX 1/15/29/43), 2x L1015 moving beam bar (43 channels each, at DMX 57 and 100) — the whole bar tilts as one unit and has 9 independently addressable pixel cells, with no independent pan. 4 LPC008S pars (only 3 patched at DMX 143/150/157; the 4th has no DMX address and is unreachable).

- **Truss**: 5-segment arch — 150cm vertical left leg, 100cm diagonal at 45° up-right, 100cm horizontal top, 100cm diagonal at 45° down-right, 150cm vertical right leg. Bounding box roughly 241cm x 221cm. One LM70S on each diagonal, two along the horizontal top. Both bars vertical on the two legs.

- **Bar orientation**: Both L1015 bars are mounted VERTICALLY, on the inside face of the two 150cm arch legs. Their cells run UP THE POLE. There is no shared horizontal axis between them.

### What does not exist yet (engineering gap)

- `generate_layout` already groups bar cells strictly by DMX address range per tilt block, so it already models "bar 1's cells" and "bar 2's cells" as separate groups. Layout is not the problem.

- `generate_layout` has a `reverse_cell_order: bool` parameter, but it only mirrors one bar's cell ordering along its own run. It is a rendering and layout-direction flag ONLY — it does not change which slot a cell inherits.

- **No code anywhere changes `macro_fixture_id` slot assignment.** Not in `preview/layout.py`, not in `venues/repo.py`, not in `cli.py`. The identical cell-to-slot sequence is a patch-time fact recorded in `user.db3.fixture`, not something `rbxlight` currently varies.

So the new capability is: **create a third venue by writing `fixture` rows with a deliberately chosen, non-mirrored `macro_fixture_id` assignment.** That is genuinely new surface area.

### Non-goals

- No horizontal sweep across 18 cells. It is not physically possible. Say so.
- Not modifying or "fixing" venue 2's decomposition trick.
- Not making the 4th unpatched par reachable — it has no DMX address.
- Not authoring the macros that would exploit the new assignment; this story delivers the venue, not the show.
- Not switching the active venue.

### In-scope documentation corrections

- `.opencode/BACKLOG.md`: move M2 out of "Not refinable yet", and record that the original left-to-right rationale was wrong and why.
- `.opencode/skills/physical-rig-profile/SKILL.md`: record the new venue and its assignment once built, and make sure the impossible-sweep correction is stated there too.

## 7. Test Impact Analysis

### Existing tests affected by this change

| Test File | Test Method | What it asserts | Conflicts? | Action |
|-----------|------------|-----------------|------------|--------|
| `tests/venues/test_repo.py` | `test_venue_creation_preserves_existing_venues` | Venues 2 and 3 remain unchanged after new venue creation | NO | Extend to cover new venue creation |
| `tests/venues/test_repo.py` | `test_fixture_slot_invariant` | 25-slot invariant is maintained | NO | Extend to cover new venue |
| `tests/preview/test_layout.py` | `test_layout_renders_venue` | Layout renders correctly for existing venues | NO | Extend to cover new venue |
| `tests/cli/test_dry_run.py` | `test_dry_run_shows_changes_without_writing` | Dry run displays changes without writing | NO | Extend to cover new venue creation |

### Test modification policy

- [ ] Existing tests MAY be updated where they assert behavior being extended (venue creation, fixture assignment, dry run).
- [ ] New tests MUST cover: venue creation with non-mirrored assignment, slot collision reporting, 25-slot invariant, dry run output, reversibility, preview rendering, and the edge case of the unpatched 4th par.
- [ ] Specific files that may be modified: `tests/venues/test_repo.py`, `tests/preview/test_layout.py`, `tests/cli/test_dry_run.py`.

### Existing files impacted

| File | Impact |
|------|--------|
| `user.db3` (working copy) | New venue row and 27 fixture rows added; venues 2 and 3 remain byte-identical |
| `.opencode/BACKLOG.md` | M2 moved out of "Not refinable yet"; original rationale correction recorded |
| `.opencode/skills/physical-rig-profile/SKILL.md` | New venue and assignment documented; impossible-sweep correction stated |

## 8. Dependencies & Ordering

- **Depends on** `RIG-calibration-session`, specifically the item confirming which physical moving head sits on which truss segment. Building a new fixture-to-slot assignment on an unverified physical mapping risks designing the wrong show.

- **Should follow** `FUTURE-bank-takeover-first-pass`. The takeover proves that a user-authored macro actually fires on a real track; without that proof, a third venue is a more elaborate way to play the same factory programming.

- **Relates to** M4 (phrase/pattern rebalance), which remains parked.

## 9. Mandatory Skills for Implementation

- `rekordbox-data-safety` — mandatory safety flow, backups, transaction guards, restore commands
- `physical-rig-profile` — rig layout, fixture positions, bar orientation, DMX addressing
- `rekordbox-lightingdb-schema` — `user.db3` schema, `fixture` and `macro_fixture` tables, 25-slot invariant
- `rekordbox-lighting-architecture` — module layout, repo/domain layer, preview integration, working copy model
