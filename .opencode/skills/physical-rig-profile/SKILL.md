---
name: physical-rig-profile
description: The physical DMX lighting rig (LM70S moving heads, L1015 moving beam bars, LPC008S pars) and how it maps onto rekordbox venue profiles and macro fixture slots. Use when generating macros, building venues, or reasoning about what a light change will actually look like.
metadata:
  skill-type: domain-reference
  project-type: data-tool
---

# Physical Rig Profile

You are the domain reference for the user's actual physical lighting rig — one real DMX universe, patched into rekordbox two different ways. This skill carries no schema detail (see `rekordbox-lightingdb-schema`) and no safety rules (see `rekordbox-data-safety`). Its only job: ground every macro, venue, or slot-assignment decision in what hardware actually exists and how it is wired today. A macro that looks correct in XML but ignores this rig profile will produce nonsense on stage — a cell silently going dark, a moving head jerking to a position it was never sent, a "sweep" that only ever plays on half the rig.

## Physical hardware (one rig, universe 1)

**PHYSICALLY OWNED vs PATCHED IN VENUE 2 are two different counts — do not conflate them.** The table below is the DMX patch (what rekordbox can see and control in the active venue). Ownership and patch match for every fixture type *except* the pars.

| qty owned | qty patched (venue 2) | model | type | channels/fixture | start address(es) | fixture_master_id | mode |
|---|---|---|---|---|---|---|---|
| 4 | 4 | LM70S | Moving head | 14ch | ch1, ch15, ch29, ch43 | 13417 | 1 |
| 2 | 2 | L1015 | Moving beam BAR | 43ch | ch57, ch100 | 29888 | 1 |
| **4** | **3** | LPC008S | Par | 7ch | ch143, ch150, ch157 | 19231 | 0 |
| 1 | 1 | fogger | direct control | — | ch171, button name `"FOG"` | — | — |

**The user owns 4 LPC008S pars, but only 3 are patched into venue 2** (ch143, ch150, ch157). The 4th physical par exists on stage but has **no DMX address in this venue at all** — rekordbox cannot control it, no macro can reach it, and it will never light up from anything this tool generates.

This is a real gap in the user's patch, not a data error to "fix" in code. Never hardcode a physical hardware count into `rbxlight` (e.g. assuming "4 pars" anywhere in generation logic) — **the venue's patched fixture list is the only source of truth for what code can control.** What the user owns and what a given venue exposes are two separate facts, and only the latter is actionable.

The L1015 is a **moving beam bar**, not a moving head: the whole bar tilts as one mechanical unit, but it has **9 individually addressable pixel cells** along its length. Any generation logic that treats an L1015 like a 4th/5th LM70S is wrong — it has no independent pan, and its real expressive surface is the 9 cells, not the tilt.

## Two venue profiles, same hardware

Both venues patch the exact same universe-1 hardware above. They differ only in how the L1015s are declared to rekordbox.

- **venue 3 `FullArc2`** (9 fixtures) — the honest patch. Each L1015 is declared as its real 43ch profile, so rekordbox sees one fixture per bar. Simple, matches the datasheet, but far less expressive — the bar can only be driven as a single block (tilt + one shared colour/brightness), because rekordbox has no native concept of "bar with 9 cells."
- **venue 2 `FullArcCustomBars`** (27 fixtures) — **ACTIVE** (`lighting_property.ExecVenueId = 2`, `LastSelectedVenue = 2`). The deliberate decomposition below, and the reason the live show actually looks good.

Any new venue this tool generates (the planned `FullArcAI`) is built on top of the venue-2 decomposition, not the venue-3 honest patch.

## The L1015 decomposition (the key trick)

Each L1015's 43 channels are re-declared in venue 2 as several *smaller, off-label* fixture profiles, at the right channel offsets, to expose the bar's internals to rekordbox:

```
ch57-62    Super Storm1500B Tilt (6ch, fixture_master_id 17404, mode 8)  -> bar 1 TILT/movement block
ch63-98    9 x 18x10W Pixel Bar (4ch, fixture_master_id 32282, mode 0)   -> bar 1's 9 individual CELLS
ch100-105  Super Storm1500B Tilt (6ch)                                  -> bar 2 TILT/movement block
ch106-141  9 x 18x10W Pixel Bar (4ch)                                   -> bar 2's 9 CELLS
```

That's 42 of the bar's 43 channels declared (ch99 and ch142 are the one spare channel per bar, unused). Rekordbox has no fixture concept of "pixel bar with cells" — declaring fake sub-fixtures at the right DMX offsets is the *only* way to address the 9 cells independently through the macro system. Each cell is then assigned to a **different** macro fixture slot (`macro_fixture_id`), so it inherits a different factory macro's brightness/colour curve when a phrase fires — producing per-cell chases across the bar from macros that were never designed with "bar cells" in mind at all.

**This is not a misconfiguration — do not "fix" it.** Any tool that reads, regenerates, or rebuilds a venue must preserve this decomposition: real 43ch L1015 profile stays in venue 3 only; venue 2 (and any successor venue) keeps the tilt-block + 9-cell split.

## Physical truss geometry (rekordbox does not store this)

Rekordbox has no concept of physical position — every fixture in the schema records a centred placeholder position, regardless of where it actually sits. The truss is a 5-segment arch, described left to right **as seen from the audience**:

```
1. 150cm vertical        — up from the ground (left leg)
2. 100cm at 45°          — up and to the right
3. 100cm horizontal      — across the top
4. 100cm at 45°          — down and to the right
5. 150cm vertical        — down to the ground (right leg)
```

Connection pieces join adjacent segments. Overall bounding box: approximately **241cm wide × 221cm tall**.

```
              ____________________
             /                    \
            / 100cm horizontal     \
           /                        \
     100cm/ 45°                 45°  \100cm
         /                            \
        |                              |
   150cm|                              |150cm
        |                              |
      ==+==                          ==+==
      ground                        ground
    (left leg)                    (right leg)
```

## Where each fixture physically mounts

- **Both L1015 moving beam bars are mounted VERTICALLY**, on the **inside face** of the two vertical (150cm) segments — one bar on the left leg, one on the right leg. Their 9 cells therefore run **UP THE POLE**, not horizontally across the stage. The bar's tilt/movement block is co-located with its own bar (left tilt block on the left leg, right tilt block on the right leg).
- **One LM70S moving head on each of the two 45° diagonal segments** — these are the two fixtures the user refers to as "tilted 45 degrees."
- **Two LM70S moving heads spaced along the horizontal top segment.**
- **Pars stand on the ground outside the arch footprint**, two to the left of the left leg, two to the right of the right leg. (Only 3 of these 4 physical pars are patched — see the ownership note above.)
- **A smoke machine sits on the ground.** It has **no DMX presence** in the venue fixture list — it must never be invented as a fixture, macro target, or slot in generated venues.

## CRITICAL: the bars do not form one horizontal sweep surface

Because both L1015 bars are mounted **vertically** on the left and right legs, "a left-to-right sweep across the arc" is **not** what the bar cells physically do. Each bar's 9 cells produce **vertical rises and falls on its own side of the arch** — bar 1's cells move up/down the left leg, bar 2's cells move up/down the right leg. There is no shared horizontal axis between them.

Any macro design or slot-allocation reasoning that assumed the 18 cells form one continuous horizontal surface is **wrong**, and this directly affects the planned `FullArcAI` venue: its earlier justification (freeing slots to enable "a continuous left-to-right sweep across all 18 cells") no longer holds, because the physical geometry doesn't support that motion in the first place. That rationale must be revisited before `FullArcAI` is built — the slot-budget arithmetic below is still correct math, but its stated *goal* needs to change to something the physical rig can actually produce (e.g. synchronized or offset vertical rises on both legs, rather than a horizontal sweep).

## Layout lives on disk, not in rekordbox

Since rekordbox stores no geometry at all, this tool maintains its **own** layout description on disk: normalized `0..1` positions plus a per-fixture rotation, independent of the rekordbox database. The user can adjust this layout file directly to correct or refine fixture placement — it is the only place physical geometry (as opposed to DMX patch) is tracked.

## Current slot assignment and its ceiling

Cell → macro fixture slot sequence in venue 2, **identical for both bars**:

| cell # | macro fixture slot | type |
|---|---|---|
| 1 | Mirrorball Spot | t5 |
| 2 | Bar Light 1 | t2 |
| 3 | Moving Head 1 | t3 |
| 4 | Par Light 2 | t1 |
| 5 | Bar Light 2 | t2 |
| 6 | Moving Head 2 | t3 |
| 7 | Par Light 3 | t1 |
| 8 | Bar Light 3 | t2 |
| 9 | Moving Head 3 | t3 |

(Bar 2's assignment shifts slightly around cell 7-9 in the raw data, but is effectively the same sequence.) Because both bars run this same sequence, cell N of bar 1 and cell N of bar 2 always play the identical macro curve at the identical moment — **the two bars always mirror each other**. A chase can ripple across one bar's 9 cells, but it can never diverge from its mirror pair. That mirrored-pair limitation is the known ceiling of the current patch, and the reason the planned `FullArcAI` venue exists — *"left-to-right sweep" was the original framing for breaking the mirror, but see "CRITICAL: the bars do not form one horizontal sweep surface" above: the bars are vertical, on opposite legs, so the actual motion to design for is vertical rise/fall per leg, not a horizontal sweep.*

Slots left completely unused in venue 2 (11 of 25):

```
Par Light 1, Par Light 4, Bar Light 4, Bar Light 5, Bar Light 6, Strobe, Laser,
Par Light 1 (Simple), Par Light 2 (Simple), Bar Light 1 (Simple), Bar Light 2 (Simple)
```

These are exactly the slots available to break the mirror without touching anything already in use.

## Slot budget arithmetic (for the planned FullArcAI venue)

**Caveat:** the arithmetic below is still correct — 27 fixtures need slots, only 25 exist, 2 collisions are unavoidable. But the stated *goal* of "a continuous left-to-right sweep across all 18 cells" is questionable — see "CRITICAL: the bars do not form one horizontal sweep surface" above. The bars are mounted vertically on opposite legs of the arch, so there is no shared horizontal axis to sweep across. Use this arithmetic for the slot-count problem; do not use the sweep framing to justify how slots are assigned until that goal is revisited.

The rig needs:

```
 4  LM70S moving heads        -> Moving Head 1-4 (t3, full slots — real pan/tilt)
 2  bar tilt blocks           -> Moving Head 1-2 (Simple) (t103) or similar — real tilt-only movement
18  pixel cells (9 x 2 bars)  -> any slot type, see below
 3  LPC008S pars              -> Par-type slots
-----------------------------
27  slots needed
```

Only **25 slots exist**. Therefore exactly **2 collisions are unavoidable** — some fixtures must share a `macro_fixture_id` with another fixture, and both will play that slot's macro curve simultaneously.

Recommended resolution:
- Let the 3 LPC008S pars share slots (they're low-priority, uniform wash lights — sharing costs little).
- And/or double up only the two **outermost** cells (cell 1 and cell 9) across the two bars, instead of mirroring all 9. That reduces the mirrored-pair count from 9 down to 2, and frees the other 7 cell-pairs per bar to run on distinct slots — letting each bar diverge from its mirror (per the caveat above, frame this as independent left-leg/right-leg vertical motion, not a horizontal sweep).

Constraint on WHERE things can go:
- The 4 LM70S need full **Moving Head** slots (t3) because they genuinely pan/tilt — a Simple slot (t103) works too since t103 also supports Gobo/Position, but t101/t102 do not and must never host an LM70S.
- The 2 bar tilt blocks only need tilt movement, so **Moving Head Simple** (t103) is the natural fit — no need to spend a full t3 slot on a fixture that only tilts.
- Cells only ever need Brightness/Colour/Strobe (see below) — they can occupy **any** slot type, full or Simple, including t101/t102. This is the flexibility that makes the 27-into-25 budget solvable at all: cells are the only fixtures in the rig that can go anywhere.

## What actually renders

A cell assigned to a Moving Head slot **silently discards** that macro's `<Position>` (and `<Rotate>`/`<Gobo>`) data — the 4ch `18x10W Pixel Bar` profile has no pan/tilt/gobo channels behind it, so only `<Brightness>`, `<Colour>`, and `<Strobe>` actually reach the fixture. This is expected, not a bug: it's precisely why assigning cells to varied slot types (Mirrorball, Bar, Moving Head, Par) produces visual variety in the first place — each slot type's macro was authored with a different brightness/colour personality even where its movement data goes nowhere. Never "fix" this by rewriting a cell's slot to something with matching sections only — the mismatch is the feature.

## Show-diversity baseline (measured, for reference)

2943 tracks total. 60% of them concentrate on just 2 of the 27 `macro_pattern` rows: pattern_id 1 = 39.5% (1162 tracks), pattern_id 7 = 20.7% (610 tracks). Each pattern is an 11-phase loop, so pattern 1 alone is effectively an 11-macro loop repeating across 40% of the library. Top individual macros by fire count: `HIGH CHORUS1 COOL` 5596×, `MID CHORUS COOL` 3517×, `HIGH UP1 COOL` 2924×. 173 of the 190 library macros are used at least once (178 enabled) — the macro *library* is adequate; the *distribution* across patterns/phrases is the actual problem any generation work should target.

## References

- Schema and XML payload details: `rekordbox-lightingdb-schema`
- Backup/write safety rules: `rekordbox-data-safety`
