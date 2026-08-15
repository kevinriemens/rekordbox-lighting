# Backlog

Raw ideas and future work. Items here need refinement before development.

---

## Epic: Bugs

### Items

- [ ] **Stale layout trap — `rbxlight layout regenerate --force`**
  After a layout-algorithm change, the non-destructive merge faithfully preserves the OLD positions,
  so a fix appears to have had no effect. Currently the only cure is deleting
  `work/layouts/layout_venue_<id>.json` by hand. Hit three separate times during the visualizer work.
  Needs a CLI command to rebuild, ideally with a diff of what would move and a confirmation prompt.

- [ ] **4th LPC008S par is unpatched in venue 2**
  I physically own 4 pars (2 left of the arch on the ground, 2 right). rekordbox venue 2 only
  patches 3 (ch143, ch150, ch157). Not a tool bug — a gap in the rekordbox patch. Decide whether to
  add it. Until then the visualizer will only ever draw 3, correctly.

- [ ] **Bar sweep direction may be inverted**
  Tilt blocks default to a 90° mounting rotation so their tilt sweeps horizontally. If the bars sweep
  the wrong way in practice, the default should become 270° rather than the user re-editing it forever.
  Needs one visual confirmation against the real rig.

---

## Epic: CLI completeness

### Items

- [ ] **Wire `pull` / `push` / `restore` into the CLI**
  Implemented and tested as library functions in M1, but never exposed as commands — the test contract
  only specified CLI behavior for `macro create`. Today these require a Python one-liner, which is
  unacceptable for `restore`, the command you'd reach for in a panic. `restore` is the priority.

- [ ] **Remove the M1 test macros**
  `10007 AI TEST CLONE` and `10008 AI TEST SWEEP` are still in the live macro library. They served
  their purpose (proving rekordbox accepts externally-written macros). Needs a `macro delete` that
  respects the factory-immutability rule.

- [ ] **Pretty-print generated XML**
  rekordbox writes 2-space-indented `LightingEditModel` payloads; ours are compact single-line.
  rekordbox accepts both — verified live — so this is purely for humans diffing YAML/XML exports.

---

## Epic: Multi-venue support (makes the tool reusable beyond this rig)

### Items

- [ ] **Switch between venues and read the hardware from the selected venue**
  The tool currently assumes the active venue (`ExecVenueId`, venue 2). It should let the user choose
  any venue, read that venue's fixture patch as the source of truth, and drive everything —
  preview, layout, macro generation — from it. I already have two venues describing the same
  physical rig (`FullArcCustomBars` and `FullArc2`) and switch between them deliberately.

- [ ] **Per-venue saved light positions**
  Layout files are already keyed per venue (`layout_venue_<id>.json`), but the workflow around them is
  not — switching venues should load that venue's saved positions automatically, and saving should
  never leak positions across venues. Needs to survive a venue being added or renamed.

- [ ] **User-definable truss geometry**
  The arch is currently hardcoded as 5 segments (150cm vertical, 100cm 45° up, 100cm horizontal,
  100cm 45° down, 150cm vertical) derived from my rig. To be reusable this must become data:
  the user adds, moves, resizes and deletes truss pieces in the visualizer and saves them per venue,
  the same way fixtures are dragged today. The generated default becomes a starting point, not a law.

- [ ] **Reusability goal (parent of the three above)**
  Together these make the tool work for ANY rig, not just this arch: pick a venue → read its patched
  fixtures → draw/adjust its truss → position its lights → preview and generate macros against it.
  Worth refining as one epic rather than three isolated stories, since they share the same data model
  (a per-venue "stage description" holding both truss geometry and fixture placement).

---

## Epic: Future Considerations

### Items

- [ ] **M2 — `FullArcAI` venue**
  Originally pitched as unlocking a continuous left→right sweep across all 18 bar cells.
  **That rationale was wrong** — the bars are mounted vertically, so their cells form two vertical
  columns, not one horizontal surface. Needs re-pitching around what the rig actually does:
  vertical rises/falls per leg, mirrored or opposed between legs, plus horizontal bar sweeps and
  the four heads moving in 3D. Do not build the original plan.

- [ ] **M4 — Phrase/pattern rebalance**
  2943 tracks, but 60% sit on just 2 of 27 macro_patterns (pattern 1 = 39.5%, pattern 7 = 20.7%).
  Each pattern is an 11-phase loop, so a long set cycles the same handful of macros —
  `HIGH CHORUS1 COOL` alone fires 5596×. Spread tracks across all 27 patterns using BPM/energy
  heuristics. Dry-run diff first, fully reversible. This is the change that most affects how a
  4-hour set actually feels, and it requires no change to how I play.

- [ ] **Calibrate the visualizer against the real rig**
  The preview renders OUR interpretation of the format, not rekordbox's engine. Movement patterns
  are approximations and pan/tilt sweeps default to 540°/270° with no datasheet. One A/B session
  with the lights wired would calibrate it and raise confidence in everything generated since.

- [ ] **Confirm LM70S pan/tilt sweep degrees**
  Defaults are 540° pan / 270° tilt, editable per fixture in the layout. Wrong values over- or
  under-scale movement in the preview but break nothing else.

- [ ] **Moving-head-to-truss-segment assignment is by patch order, not name**
  The layout puts moving heads 1 and 2 on the diagonals. I refer to MH1 and MH4 as the tilted
  ones. Only I can resolve which physical head sits on which segment — until then, drag and save.
