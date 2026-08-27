---
epic: "TRACKLIGHT"
title: "Stage 3.1 — Per-track shows (placeholder — NOT REFINABLE YET)"
estimate: L
status: placeholder
created: 2026-08-26
depends_on: ["E3", "S2.1"]
labels: [placeholder, per-track, phrase_data, not-refinable]
priority: P0
claimed_by:
claimed_by_date:
---

## ⚠️ This is a placeholder, not a refined story

This file exists so the north star stays visible in the story index rather than living only in someone's head. It will be replaced by real stories once the checklist at the end is satisfied.

**Do not attempt to refine or build this story until all blockers are cleared.** The three unknowns listed below are load-bearing: each one changes the shape of the work, and none can be resolved without external evidence.

---

## 1. The Goal

The north star of the whole TRACKLIGHT project: a bespoke light show per track, generated from that track's own analysed structure.

Today, a track's lighting is determined by:
1. **Which bank it lands in** (Stage 1) — ~24 addressable patterns across 8 banks × 3 energies
2. **What that bank plays** (Stage 2) — custom macros replacing factory ones

That is 24 lights shows, applied across ~2900 tracks. The bank stops being the entire show and becomes only a starting point.

Stage 3 would make it possible to author one show per track: to read `(content_id, phrase_num)` pairs from the analysed structure and write a bespoke macro assignment for each phrase, rather than reusing the bank's sequence.

## 2. The Mechanism (as currently understood)

`user.db3 phrase_data`, keyed `(content_id, phrase_num)`, holds one row per analysed phrase with a `macro_id` and an `initial_macro_id`. It is the layer that actually fires during playback and it shadows both `macro_assign` and the track's bank.

**Measured baseline (2026-08-23):**
- 41,742 rows across 2,905 tracks
- Roughly 14 phrases per track on average
- Each row represents a single phrase of a single track that will fire a specific macro during playback
- 36 of the 41,742 rows already differ from their `initial_macro_id`, meaning *something* has written per-phrase overrides in this library before — most likely the DJ through rekordbox's own UI

Writing per-phrase macros there is what "a show per track" would concretely mean: replacing the bank's phase sequence with a track-specific one.

## 3. Why It Is Not Refinable (three load-bearing unknowns)

### Unknown 1: Does rekordbox honour externally-written `phrase_data`?

**The question:** Can this tool write to `phrase_data.macro_id` and have rekordbox actually fire those macros at playback?

**Current evidence:** The 36 existing rows that differ from `initial_macro_id` prove that *something* has written to `phrase_data` before. That proves the field is meaningful, not that *our* writes are honoured. The most likely source is the DJ authoring overrides via rekordbox's own UI.

**Why it matters:** If rekordbox ignores externally-written `phrase_data`, then the entire Stage 3 approach is dead and must be rethought from first principles. E3 (the direct phrase-write test, folded into `RIG-calibration-session`) is designed to answer this definitively.

### Unknown 2: Is there enough macro diversity to make per-phrase selection meaningful?

**The question:** Choosing a macro per phrase is only interesting when there are many distinct macros to choose between. How many macros will S2.1 deliver, and how much do they differ from each other?

**Current evidence:** The factory library has 173 enabled macros. That is adequate for 24 banks × 3 energies, but it is not abundant. If S2.1 delivers only a handful of custom macros per bank, then per-phrase selection would be shuffling the same few looks across 41,742 rows. That is not a show per track; that is per-phrase colouring of the bank.

**Why it matters:** A per-track writer is only worth building if it has meaningful content to work with. S2.1 must deliver a substantial, varied library first.

### Unknown 3: What does `phrase_num` mean musically, and is the numbering stable?

**The question:** `phrase_num` has been observed in the range 1..99, but what each value means musically, how rekordbox derives them, and whether the numbering is stable across re-analysis are all unknown.

**Current evidence:**
- 41,742 rows exist; the observed range is 1..99
- The meaning of individual phrase numbers (e.g., "is phrase 3 always a verse?") is not established
- Whether rekordbox re-derives phrase numbers on re-analysis is unknown — if it does, and re-analysis shifts the numbering, per-track work could silently be destroyed

**Why it matters:** A per-track show cannot be authored against phrase positions whose meaning is not established. The vocabulary must be mapped — likely a separate small experiment of its own, which should be added to the epic when Stage 2 is underway. E2c in `RIG-calibration-session` partially addresses re-analysis behaviour, but the full phrase vocabulary remains unmapped.

---

## 4. What Would Make This Refinable (explicit checklist)

- [ ] **E3 returns a positive verdict.** `RIG-calibration-session` includes a test that writes a `phrase_data.macro_id` and confirms it fires during playback on the real rig. A "no" ends Stage 3; a "yes" unblocks it.

- [ ] **S2.1 has produced a macro library with enough diversity.** The macro recipes (role-based YAML) have been authored and delivered. The resulting macro library contains enough distinct looks per bank to make per-phrase selection meaningful. "Meaningful" is a judgment call, but the bar is: would a DJ find it compelling to author a custom phrase sequence, or does it feel like shuffling the same handful of options?

- [ ] **The `phrase_num` vocabulary has been mapped.** The phrase numbering scheme is documented — what each observed value (1, 2, 3, ... 99) represents musically, how it correlates with musically recognizable track structure (verse, chorus, bridge, etc.), and whether the mapping is consistent across different tracks or depends on the specific analysis. This is likely a separate small experiment of its own; it should be added to the epic and scheduled as part of the Stage 2 workstream.

- [ ] **The re-analysis question is settled.** Does rekordbox rebuild `phrase_data` on re-analysis, and would it therefore silently destroy per-track work? E2c in `RIG-calibration-session` partially answers this (by analysing a track that was previously analysed and checking whether `phrase_data` was rewritten). If the answer is "yes, phrase_data is rebuilt", then per-track work becomes temporal — it needs to be re-authored on every re-analysis, which is a different kind of problem (still solvable, but a different workflow). The answer needs to be explicit so Stage 3 work can be designed around it.

---

## 5. Why This Placeholder Exists

This placeholder is intentional. It serves two purposes:

1. **The north star stays visible.** A bespoke light show per track is the dream that makes Stage 1 and Stage 2 worthwhile. Without Stage 3 in the story index, that intention only lives in someone's head and is easy to forget. By documenting it here with its blockers explicit, the goal becomes a checklist rather than a hope.

2. **The blockers are transparent.** Anyone opening this file will immediately understand that it cannot be built yet and *why*. The three unknowns are all stated; the evidence for each is recorded; and the exact conditions for refinement are listed. This prevents the common failure mode: someone picks up Stage 3 halfway through, makes assumptions about the unknowns, and ships work that depends on answers that were never established.

When all four items on the checklist above are satisfied, this file will be replaced by real stories with design, acceptance criteria, and implementation guidance. Until then, it is a reminder that the north star is still there, and what it will take to reach it.

---

## Mandatory Skills for Implementation

(To be determined when this becomes refinable. Current candidates: `rekordbox-data-safety`, `rekordbox-lightingdb-schema`, `rekordbox-lighting-architecture`, `physical-rig-profile`, `S2.1-output-whatever-shape-it-takes`.)
