---
epic: RIG
title: Calibrate the visualizer and rig assumptions in one session
estimate: M
status: ready
created: 2026-08-23
depends_on: [ ]
labels: [ rig, calibration, observational, physical-hardware ]
priority: P1
claimed_by:
claimed_by_date:
---

## 1. User Story

**As a** lighting engineer\
**I want** to verify that the visualizer's rendering matches the physical rig's actual behavior, and correct any wrong assumptions about fixture positions and sweep ranges\
**So that** I can trust macro previews to judge whether a macro is any good, and future code changes start from correct hardware facts instead of guesses\

## 2. Business Context & Value

Five backlog items were all blocked on "needs the physical lights wired". The setup cost — rig powered, DMX patched, rekordbox open, a known track cued — is identical for one item as for all five. Batching them means paying that cost once. Three of the five are answered by simply looking at the rig. This story exists so the user never has to re-derive what to look at.

The visualizer carries an honest disclaimer: it "renders this tool's interpretation of the macro format, not rekordbox's actual playback engine. Movement patterns are approximations." This session is the one chance to find out how far off it is, and to raise or lower confidence in every macro generated so far.

## 3. Preparation Checklist

Before starting, verify:

- [ ] Rig powered and DMX patched; all fixtures responding
- [ ] rekordbox open, active venue confirmed as id 2 (`rbxlight venue list`)
- [ ] A known track cued that reliably lands on a COOL/HIGH phrase (e.g., one that triggers macro_id 31 `HIGH CHORUS1 COOL`)
- [ ] Phone or notepad ready — the whole point is recording answers
- [ ] **Critical**: rekordbox must be RUNNING for observation, but must be QUIT before any `--write` command. Plan to observe everything first, then quit rekordbox, then apply all changes together.

## 4. Acceptance Criteria

* [ ] **Item 1 — Visualizer verdict recorded**: For each of the four behaviours (movement shape, colour timing, gobo, tempo), a written verdict is recorded: "matches", "close enough to judge macros by", or "misleading"
* [ ] **Item 2 — Bar sweep direction verified**: Recorded which bars have `tilt_reversal` set and whether that matches physical reality; stale backlog claim corrected
* [ ] **Item 3 — LM70S sweep degrees confirmed**: Actual pan/tilt throw degrees measured and recorded; layout file updated if needed; constants updated if all four heads agree with each other but disagree with defaults
* [ ] **Item 4 — Head-to-segment assignment corrected**: Each of the four LM70S heads is lit individually, physical position recorded, and layout file updated via `layout install` (dry run first, then `--write`)
* [ ] **Item 5 — Panel vocabulary captured**: Verbatim wording from rekordbox UI recorded for bank selector, energy selector, energy values, and phrase/phase terminology
* [ ] **No live database written while rekordbox was running**: All `--write` commands executed only after rekordbox quit
* [ ] **Dry run before every write**: Every `--write` command preceded by the same command without `--write`
* [ ] **Five rig items removed from backlog**: `.opencode/BACKLOG.md` updated to remove items from "Blocked on the rig" section
* [ ] **Skills updated with confirmed facts**: `physical-rig-profile` and `rekordbox-lightingdb-schema` updated with head-to-segment assignment, real pan/tilt degrees, and panel vocabulary

## 5. Technical Constraints

* **Observation happens with rekordbox RUNNING**; all writes happen only after it is QUIT. Never write to a live DB with rekordbox running.
* **Dry run before every `--write`**, without exception.
* **Never write to `master.db3`**. Never touch `macro_old.db3` or `master_old.db3` — those are rekordbox's own pre-upgrade copies.
* **Layout regeneration preserves calibration**: `layout regenerate --write` preserves existing per-fixture pan/tilt calibration via internal `apply_prior_calibration` step — regenerating does NOT wipe calibration.
* **Backup before any write**: This project's mandatory flow is: guard rekordbox not running, back up, write in one transaction, verify by re-read, report the restore command.

## 6. Session Runbook — Execute Top to Bottom

### ITEM 1: Calibrate the visualizer against the real rig

**Goal**: Compare the preview rendering side-by-side with the physical rig playing the same macro, and record a verdict on four specific behaviours.

**Setup**:
1. Pick a high-frequency macro that is actually played. Recommendation: `HIGH CHORUS1 COOL` (macro_id 31 — fires 5607 times in this library, the most of any macro).
2. Run `rbxlight preview --venue 2 -o work/preview.html` (rekordbox still running).
3. Open `work/preview.html` in a browser.
4. Cue the known track in rekordbox and play it until it lands on the phrase that triggers the macro.
5. Observe the physical rig and the preview side-by-side.

**Checklist — record a verdict for each**:

- [ ] **Movement shape**: MovementBlock pattern shapes (Circle / Line / Square etc., read from the macro XML) — is the swept path shape and speed right on the real heads?
  - Verdict: ☐ matches | ☐ close enough to judge macros by | ☐ misleading
  - Notes: ___________________________________________________________

- [ ] **Colour transition timing and curve**: Do colours arrive at the same moment and ramp the same way?
  - Verdict: ☐ matches | ☐ close enough to judge macros by | ☐ misleading
  - Notes: ___________________________________________________________

- [ ] **Gobo**: The preview never extracts gobo data (`gobo` is hardcoded `None`). Expect the real rig to show gobo-driven texture the preview simply cannot show. This is a known designed gap, NOT a bug — confirm it is the only unexplained visual difference.
  - Verdict: ☐ gobo is the only difference | ☐ other unexplained differences exist
  - Notes: ___________________________________________________________

- [ ] **Tempo**: The preview uses `DEFAULT_BPM = 128` as a static fallback (rekordbox macros carry no intrinsic BPM). If the preview is run without matching the real track's BPM, animation speed is silently wrong.
  - First, compare using a track at or near 128 BPM to remove this variable.
  - Then, deliberately try one at a very different BPM to confirm the fallback is the cause of any drift.
  - Verdict: ☐ matches at 128 BPM | ☐ drifts at different BPM (fallback confirmed) | ☐ drifts even at 128 BPM
  - Notes: ___________________________________________________________

**Outcome**: A short written verdict per behaviour. The value of this item is retroactive: it raises or lowers confidence in every macro generated so far.

---

### ITEM 2: Bar sweep direction — verify the backlog claim is wrong

**Critical context**: The backlog claimed: "tilt blocks default to a 90 degree mounting rotation, and if the bars sweep the wrong way in practice the default should become 270". **That proposed fix is wrong and must not be applied.**

Research verified: `DEFAULT_TILT_BLOCK_ROTATION_DEGREES = 90.0` is a rendering-only mounting-angle default describing an L1015 mounted vertically on its end on the inside of an arch leg. An existing test, `test_should_never_give_the_two_tilt_blocks_opposing_mounting_rotations`, asserts that BOTH bars always receive the SAME mounting rotation. The left/right mirrored sweep the user actually sees on stage comes from each fixture's own `tilt_reversal` DMX flag (sourced from `user.db3` `fixture.tilt_reversal`), never from giving the two bars opposing mounting-rotation constants. Flipping both the constant and `tilt_reversal` produces a double-mirroring bug, which is exactly what that test guards against.

**Checklist**:

- [ ] **Observe bar tilt orientation**: Look at the two L1015 bars on the vertical legs. Do they sweep in opposite directions (left bar sweeps left-to-right, right bar sweeps right-to-left), or do they sweep in the same direction?
  - Observation: ☐ opposite directions (expected) | ☐ same direction (unexpected)
  - Notes: ___________________________________________________________

- [ ] **If bars sweep correctly**: Record which bars have `tilt_reversal` set in the venue patch (inspect `user.db3` fixture.tilt_reversal for the two bar fixtures). This is the source of the mirroring, not the constant.
  - Left bar (fixture_id ___): tilt_reversal = ☐ 0 | ☐ 1
  - Right bar (fixture_id ___): tilt_reversal = ☐ 0 | ☐ 1
  - Notes: ___________________________________________________________

- [ ] **If bars sweep incorrectly**: Do NOT touch `DEFAULT_TILT_BLOCK_ROTATION_DEGREES`. Instead, inspect `tilt_reversal` on the two bar fixtures in the venue patch. The fix is to flip `tilt_reversal` on one or both bars, not to change the constant.
  - Action taken: ___________________________________________________________

**Outcome**: Confirm that the rendered bar tilt orientation matches physical reality. Record which bars have `tilt_reversal` set. In `.opencode/BACKLOG.md`, correct the stale claim and remove this item from "Blocked on the rig".

---

### ITEM 3: Confirm LM70S pan/tilt sweep degrees

**Goal**: Measure the actual mechanical range of one LM70S head and compare against the assumed defaults.

**Current assumed defaults**: `DEFAULT_PAN_DEGREES = 540.0`, `DEFAULT_TILT_DEGREES = 270.0`. There is no datasheet; these are guesses. The code comment is explicit that rekordbox does not record this — it is a hardware property the user corrects per fixture in the layout file.

**Effect if wrong**: A head's rendered sweep is too wide or too narrow versus its real mechanical range — it visually overshoots positions it cannot physically reach, or undersells a wider real throw.

**Checklist**:

- [ ] **Drive one LM70S to its pan extremes**: Using rekordbox or direct DMX control, move one head's pan to its leftmost position, then its rightmost position. Estimate the total degrees of throw.
  - Head used: MH___ (DMX channel ___)
  - Observed pan throw: approximately _____ degrees
  - Notes: ___________________________________________________________

- [ ] **Drive the same head to its tilt extremes**: Move the head's tilt to its lowest position, then its highest position. Estimate the total degrees of throw.
  - Observed tilt throw: approximately _____ degrees
  - Notes: ___________________________________________________________

- [ ] **If throw differs from 540 / 270**: Correct `pan_degrees` / `tilt_degrees` per fixture in `work/layouts/layout_venue_2.json`. The layout file is human-readable JSON; edit directly or use the visualizer drag-and-export flow.
  - Correction applied: ☐ yes | ☐ no (defaults are correct)
  - New values (if corrected): pan = _____, tilt = _____
  - Notes: ___________________________________________________________

- [ ] **If ALL FOUR heads are the same model and agree with each other but disagree with the defaults**: Also update the two constants (`DEFAULT_PAN_DEGREES` and `DEFAULT_TILT_DEGREES`) so future venues start correct.
  - Constants updated: ☐ yes | ☐ no (defaults are correct)
  - New values (if updated): pan = _____, tilt = _____
  - Notes: ___________________________________________________________

**Outcome**: Actual pan/tilt throw degrees recorded. Layout file and/or constants updated if needed. Changes survive a subsequent `layout regenerate --write` (calibration is preserved).

---

### ITEM 4: Which physical moving head sits on which truss segment

**Goal**: Map each of the four LM70S heads to its physical position on the truss.

**Current layout logic**: `generate_layout` sorts fixtures by DMX `start_addr` (never by list order). The lowest-address heads, as many as there are diagonal segments, are placed one per diagonal at that segment's midpoint and angle; remaining heads distribute evenly across the horizontal top run.

**The conflict to resolve**: The generated layout puts heads 1 and 2 on the diagonals, but the user refers to MH1 and MH4 as the tilted ones. Only the user can say which is true.

**Checklist**:

- [ ] **Light one head at a time**: The four LM70S are at DMX channels 1, 15, 29, 43. Use rekordbox or direct DMX control to light each head individually (e.g., set it to a bright white, all other heads to black).
  - Head at DMX channel 1: Physical position = ☐ left diagonal | ☐ right diagonal | ☐ horizontal top (left) | ☐ horizontal top (right)
  - Head at DMX channel 15: Physical position = ☐ left diagonal | ☐ right diagonal | ☐ horizontal top (left) | ☐ horizontal top (right)
  - Head at DMX channel 29: Physical position = ☐ left diagonal | ☐ right diagonal | ☐ horizontal top (left) | ☐ horizontal top (right)
  - Head at DMX channel 43: Physical position = ☐ left diagonal | ☐ right diagonal | ☐ horizontal top (left) | ☐ horizontal top (right)

- [ ] **Correct the layout if needed**: If the generated layout does not match physical reality, correct it. The supported path is:
  1. Open the visualizer: `rbxlight preview --venue 2 -o work/preview.html`
  2. Drag each fixture to its true position in the preview
  3. Export the layout from the visualizer
  4. Run `rbxlight layout install <exported-path> --venue 2` (dry run first)
  5. If dry run looks correct, run `rbxlight layout install <exported-path> --venue 2 --write`
  
  Alternatively, hand-edit `work/layouts/layout_venue_2.json` directly (format is human-readable).
  
  - Layout corrected: ☐ yes | ☐ no (generated layout is correct)
  - Method used: ☐ visualizer drag-and-export | ☐ hand-edit JSON
  - Notes: ___________________________________________________________

- [ ] **Verify correction persists**: After correcting the layout, run `rbxlight layout regenerate --venue 2` (dry run, no `--write` yet). The regenerated layout should preserve your corrections.
  - Verification: ☐ corrections preserved | ☐ corrections lost (investigate)
  - Notes: ___________________________________________________________

**Important**: Correcting this does NOT require re-patching DMX addresses in rekordbox. The layout file is the only place physical position is tracked.

**Outcome**: Each of the four LM70S heads is mapped to its physical position. Layout file updated via `layout install` (dry run first, then `--write`). Corrections survive a subsequent `layout regenerate --write`.

---

### ITEM 5: Confirm the rekordbox panel vocabulary

**Goal**: Capture rekordbox's exact on-screen wording for bank, energy, and phrase terminology.

**Context reframe**: The premise changed. Research confirmed the CLI and README currently use NO bank/energy/mood/phase vocabulary at all. There is no "our wording" to compare against rekordbox's yet, so there is nothing to fix today. What this item becomes: capture rekordbox's exact on-screen wording NOW, before the bank-takeover story introduces a `bank` command and starts putting these words in front of the user. Getting the vocabulary right the first time is far cheaper than renaming a shipped command.

**Ground truth already established from the database** (for comparison):
- `macro_pattern.energy` is 1=HIGH, 2=MID, 3=LOW (this is INVERTED from what was previously assumed)
- `macro_pattern.pattern` 1..8 are the 8 banks, named COOL, NATURAL, HOT, SUBTLE, WARM, VIVID, CLUB1, CLUB2
- These names are encoded as the final token of factory macro names in the shape `<ENERGY> <PHASE> <BANK>`, e.g. `HIGH CHORUS1 COOL`
- `pattern = 99` is a separate non-bank case (INTERLUDE)
- Phase count varies by energy (11/10/6/6) — do not hardcode 11
- The live panel state currently reads `MoodLastId=2`, `BankLastId=3`, `PhraseLastId=2`, `StrobeLastId=1`
- The long-standing inference is that the panel's MOOD selector maps to `pattern` and its BANK selector maps to `energy` — note that this is the OPPOSITE of what the names suggest, which is exactly why it needs confirming with eyes on the UI

**Checklist**:

- [ ] **Open the rekordbox lighting panel** and look at the selector controls.

- [ ] **Bank selector**: What is the label of the selector that chooses between the 8 banks?
  - Label: ___________________________________________________________
  - Values shown: ___________________________________________________________
  - Notes: ___________________________________________________________

- [ ] **Energy selector**: What is the label of the selector that chooses energy?
  - Label: ___________________________________________________________
  - Is energy presented as HIGH/MID/LOW or as numbers (1/2/3)?
  - Values shown: ___________________________________________________________
  - Notes: ___________________________________________________________

- [ ] **Phrase/Phase terminology**: What does rekordbox call a phrase/phase?
  - Terminology used: ☐ phrase | ☐ phase | ☐ other: ___________
  - Label of the selector: ___________________________________________________________
  - Notes: ___________________________________________________________

- [ ] **Mood selector** (if present): What is the label and what does it control?
  - Label: ___________________________________________________________
  - Controls: ___________________________________________________________
  - Notes: ___________________________________________________________

**Outcome**: Verbatim wording from rekordbox UI recorded for bank selector, energy selector, energy values, and phrase/phase terminology. This feeds the bank-takeover story and ensures the CLI vocabulary matches rekordbox's.

---

## 7. Post-Session: Apply Changes and Update Documentation

**CRITICAL**: All changes below happen AFTER rekordbox is quit. Never write to a live DB with rekordbox running.

### Step 1: Backup

```bash
# Backup the active venue's database files
cp ~/.config/Pioneer/rekordbox/master.db3 ~/.config/Pioneer/rekordbox/master.db3.backup-$(date +%Y%m%d-%H%M%S)
cp ~/.config/Pioneer/rekordbox/user.db3 ~/.config/Pioneer/rekordbox/user.db3.backup-$(date +%Y%m%d-%H%M%S)
```

### Step 2: Apply layout corrections (if any)

If you corrected the layout in Item 4:

```bash
# Dry run first
rbxlight layout install <path-to-exported-layout> --venue 2

# If dry run looks correct, apply with --write
rbxlight layout install <path-to-exported-layout> --venue 2 --write
```

### Step 3: Regenerate layout to preserve calibration (if you updated pan/tilt in Item 3)

If you corrected pan/tilt degrees in Item 3:

```bash
# Dry run first
rbxlight layout regenerate --venue 2

# If dry run looks correct, apply with --write
rbxlight layout regenerate --venue 2 --write
```

### Step 4: Update `.opencode/BACKLOG.md`

- Remove the five rig items from the "Blocked on the rig" section
- Correct the stale bar-sweep-direction claim (Item 2): explain that the mirroring comes from `tilt_reversal`, not from the constant
- Record the outcomes from Items 1, 3, 4, 5

### Step 5: Update `.opencode/skills/physical-rig-profile/SKILL.md`

Record confirmed facts:
- Head-to-segment assignment (Item 4)
- Real pan/tilt degrees (Item 3)
- Panel vocabulary (Item 5)

### Step 6: Update `.opencode/skills/rekordbox-lightingdb-schema/SKILL.md`

Record the confirmed panel vocabulary mapping (Item 5):
- What rekordbox calls the bank selector and what it controls
- What rekordbox calls the energy selector and what it controls
- Confirmed terminology for phrase/phase

### Step 7: Verify by re-read

After writing, verify the changes persisted:

```bash
# Verify layout file
cat work/layouts/layout_venue_2.json | jq '.entries[] | {fixture_id, label, x, y, pan_degrees, tilt_degrees}'

# Verify backlog was updated
grep -A 20 "Blocked on the rig" .opencode/BACKLOG.md
```

### Step 8: Report the restore command

If anything goes wrong, restore from backup:

```bash
# Restore from backup
cp ~/.config/Pioneer/rekordbox/master.db3.backup-<timestamp> ~/.config/Pioneer/rekordbox/master.db3
cp ~/.config/Pioneer/rekordbox/user.db3.backup-<timestamp> ~/.config/Pioneer/rekordbox/user.db3
```

---

## 8. Design & UI/UX

N/A — this is an observational session, not a feature build.

---

## 9. Scope & Context

**What existing behavior is affected**:
- The layout file (`work/layouts/layout_venue_2.json`) is the single source of truth for physical fixture positions and sweep ranges. Corrections here affect all subsequent previews and macro generation.
- The visualizer's rendering confidence is retroactively raised or lowered based on Item 1's verdict. If the preview is misleading on any behaviour, all macros generated so far are suspect.
- The backlog's "Blocked on the rig" section is cleared, unblocking the bank-takeover story (Item 5 feeds it).

**Domain rules**:
- DMX addresses are never changed by this story — only physical positions and sweep ranges.
- `tilt_reversal` is the source of bar mirroring, not the mounting-rotation constant.
- Layout regeneration preserves per-fixture calibration via `apply_prior_calibration`.
- Rekordbox must be quit before any `--write` command.

**Known pitfalls**:
- Confusing the mounting-rotation constant with the `tilt_reversal` flag (Item 2).
- Forgetting to dry-run before `--write`.
- Writing to the database while rekordbox is running.
- Inventing fixture positions instead of measuring them (Item 4).

---

## 10. Test Impact Analysis

N/A — this is an observational session, not a code change. No existing tests are modified.

However, the existing test `test_should_never_give_the_two_tilt_blocks_opposing_mounting_rotations` (in the test suite) guards against the double-mirroring bug described in Item 2. This test should continue to pass after the session.

---

## 11. Mandatory Skills for Whoever Picks This Up

- `rekordbox-data-safety` — mandatory safety rules for reading/writing rekordbox LightingDB files
- `physical-rig-profile` — the physical rig layout and fixture positions
- `rekordbox-lightingdb-schema` — schema of macro.db3, user.db3, and the LightingEditModel XML macro format
