# Backlog

Raw ideas and future work. Items here need refinement before development.

---

## Epic: Bugs

### Items

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

- [ ] **Remove the M1 test macros** *(tool now exists — this is just the chore)*
  `10007 AI TEST CLONE` and `10008 AI TEST SWEEP` are still in the live macro library. They served
  their purpose (proving rekordbox accepts externally-written macros). `rbxlight macro delete` now
  exists and respects factory-immutability, so this is:
  `pull` → `macro delete 10007 --write` → `macro delete 10008 --write` → `push --write`.

- [ ] **Pretty-print generated XML**
  rekordbox writes 2-space-indented `LightingEditModel` payloads; ours are compact single-line.
  rekordbox accepts both — verified live — so this is purely for humans diffing YAML/XML exports.

---

## Epic: Multi-venue support (makes the tool reusable beyond this rig)

**REFINED 2026-08-15 → three stories in `.opencode/refined/`.** Build in order:

1. ~~`MULTI_VENUE-venue-discovery-and-selection` (S)~~ — **BUILT 2026-08-15.** Shipped as more than
   discovery: `layout regenerate` turned out to never validate the venue at all, so a bad or stale
   `--venue` silently exited 0. Both venue-aware commands now share one resolver.
2. `MULTI_VENUE-per-venue-stage-description` (L) — truss geometry becomes persisted per-venue data
   in cm; fixture auto-placement stops assuming the arch shape.
3. `MULTI_VENUE-truss-editing-in-visualizer` (M) — draw/edit truss as a polyline, plus a CLI install
   command that ends the download→manually-move-the-file chore. Depends on 2.

Decisions taken during refinement: auto-placement stays (generic, along the truss run) rather than
hand-placing 27 fixtures; truss is stored in **cm**, not normalized, so rig scale survives; truss is
a **polyline of vertices**, not discrete truss pieces; the existing arch becomes the default shape,
not a law. Split into three because they share a data model but not a review surface — 2 is Python +
schema migration, 3 is vanilla-JS canvas work.

Findings that shrank the epic: layout files were already per-venue by construction, and macros are
venue-agnostic (they address the 25 fixed slots, not a venue's physical patch) so macro generation
needed no work at all. The real hardcode was never the four arch constants — it was the placement
algorithm assuming "two verticals, two diagonals and a top".

### Items

- [x] ~~Switch between venues and read the hardware from the selected venue~~ → story 1
- [x] ~~Per-venue saved light positions~~ → story 2 (largely already true; folded in)
- [x] ~~User-definable truss geometry~~ → stories 2 + 3
- [x] ~~Reusability goal (parent of the three above)~~ → the three stories above

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

- [ ] **Custom banks — own the 8 mood banks before trying to invent a 9th**
  *Researched 2026-08-15 against the live DBs. Findings below are measured, not assumed.*

  A "bank" is a row in `macro.db3.macro_pattern`, which is nothing but the cross product
  `energy (1=HIGH, 2=MID, 3=LOW) × pattern (1..8, plus 99)`:
  `1=COOL 2=NATURAL 3=HOT 4=SUBTLE 5=WARM 6=VIVID 7=CLUB1 8=CLUB2`, `99` = the 6-phase
  INTERLUDE set. 3 × 9 = the 27 `macro_pattern` ids. `content.macro_pattern_id` is how a track
  picks one; `macro_assign(macro_pattern_id, phase, macro_id, initial_macro_id)` is how a bank
  picks a macro per phrase slot (11 phases for HIGH, 10 for MID, 6 for LOW/INTERLUDE).

  **The names live nowhere in any database.** Not `macro.db3`, not `user.db3`, not `master.db3` —
  there is no name/label column on `macro_pattern` at all. COOL/NATURAL/… are hardcoded UI strings
  in the rekordbox binary, keyed off the `pattern` integer. So "add a custom bank *with a name*"
  is not something the schema can express.

  **The far more valuable finding:** all 232 `macro_assign` slots across the 27 banks point at
  factory macros (`preset=1`). Zero point at a user macro. The bank mechanism is fully rewritable
  and completely untouched — swap a slot's `macro_id` to a `preset=0` macro (10001+) and that bank
  now plays my programming. Taking over e.g. CLUB1 and CLUB2 across all three energies yields
  6 banks × up to 11 phases = ~62 slots of entirely custom show, today, with no schema risk.
  The label stays "CLUB1"; everything behind it is mine. This is the real feature, and it composes
  with M4 (rebalance decides *which* bank a track gets, this decides *what a bank plays*).

  **A genuinely 9th bank (`pattern=9`, new `macro_pattern` id 28) is speculative.** Inserting the
  row and pointing `content.macro_pattern_id` at it is trivial; whether rekordbox honours it is not
  known. Two failure modes to test for: the mood selector is almost certainly a fixed 8-button row,
  so the bank would be unreachable and unlabeled in the UI, and touching that selector for a track
  would snap it back into 1..8; and rekordbox may prune `macro_pattern`/`content` rows it does not
  recognise on load. Cost to find out is one experiment — insert id 28, point one throwaway track at
  it, launch rekordbox, re-read. Backup first; this touches `content`, which holds 2943 rows of real
  work. **Do the takeover work first — it delivers the same outcome without betting on the unknown.**

  Related: `lighting_property` holds live panel state `MoodLastId=2`, `BankLastId=3`,
  `PhraseLastId=2`, `StrobeLastId=1`. Inferred (needs one glance at the rekordbox UI to confirm):
  the panel's MOOD selector = `pattern`, its BANK selector = `energy`. Worth pinning down before
  writing any user-facing copy, so the tool's vocabulary matches rekordbox's.

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
