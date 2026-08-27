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

## CRITICAL: the 18 bar cells alone do not form one horizontal sweep surface

Because both L1015 bars are mounted **vertically** on the left and right legs, "a left-to-right sweep built from the 18 bar cells sharing one horizontal axis" is **not** what the bar cells physically do. Each bar's 9 cells produce **vertical rises and falls on its own side of the arch** — bar 1's cells move up/down the left leg, bar 2's cells move up/down the right leg. There is no shared horizontal axis between the two bars' cells.

Any macro design or slot-allocation reasoning that assumed the 18 cells alone form one continuous horizontal surface is **wrong**, and this directly affected the planned `FullArcAI` venue: its earlier justification (freeing slots to enable "a continuous left-to-right sweep across all 18 cells") does not hold in that specific cells-only framing. That narrow rationale needed revisiting — the slot-budget arithmetic below is still correct math, but its stated *goal* needed to change to something the physical rig can actually produce from cell motion alone (e.g. synchronized or offset vertical rises on both legs).

**This does not mean a left-to-right sweep is impossible for the rig as a whole** — see "Named rig gesture: the perimeter sweep" below. A whole-rig sweep exists; it just isn't built from the 18 cells' horizontal motion, because the cells have none.

## Named rig gesture: the perimeter sweep ("left-to-right")

The DJ has a specific gesture in mind that he calls the "left-to-right sweep": a light travelling around the rig's outer perimeter, described in his own words as "the light following the rig from down left, going straight up through the bar lights, then going to the 45 degrees moving head, then the two horizontal moving heads, then 45 degrees down moving head and doing the right side bar."

Mapped onto the documented fixtures, in order:

```
1. bottom of the left 150cm leg     -> bar 1's cells, lowest cell first
2. up the left leg                  -> bar 1's cells, rising (vertical, per-leg motion)
3. left 45° diagonal                -> the LM70S head mounted on that segment
4. horizontal top                   -> the two LM70S heads spaced along that segment
5. right 45° diagonal                -> the LM70S head mounted on that segment
6. down the right leg                -> bar 2's cells, descending (vertical, per-leg motion)
```

This is a **real, buildable gesture**, not a horizontal pan across the room and not a claim that the 18 cells share a horizontal axis. It reads as "left-to-right" at the scale of the whole rig — a path traversing the arch from one side to the other — while every individual fixture along that path only ever does what it can physically do: the two bars move vertically on their own leg, and each LM70S moving head takes over at its own fixed position. The "sweep" is the handoff sequence between fixtures, not a single fixture moving horizontally.

**The general trap this corrects:** a gesture's *name* can describe its overall visual reading (here, "left-to-right") while its *implementation* is per-fixture motion in a different axis entirely (here, vertical rises on two separate legs, chained with fixed-position moving-head handoffs). Do not infer, from a gesture's name, what axis or fixture is doing the moving — check the fixture-by-fixture path. Read a name as an intent description, not a specification of any single fixture's motion. This is exactly the mistake made previously in this file: a gesture named for its horizontal reading was judged impossible because its *components* move vertically, when in fact both are true at once — vertical per-leg motion IS the mechanism the horizontal-reading gesture is built from, not a contradiction of it.

This gesture is the motivating example for breaking the bar mirror (the planned `FullArcAI` venue, see slot budget below): it requires bar 1 and bar 2 to run independent, non-mirrored vertical motion at different points in the phrase (bar 1 rising while the path is on the left, bar 2 descending once the path reaches the right), which the current hard-mirrored cell-to-slot assignment cannot express.

## Layout lives on disk, not in rekordbox

Since rekordbox stores no geometry at all, this tool maintains its **own** layout description on disk: normalized `0..1` positions plus a per-fixture rotation, independent of the rekordbox database. The user can adjust this layout file directly to correct or refine fixture placement — it is the only place physical geometry (as opposed to DMX patch) is tracked.

## Current slot assignment and its ceiling

**Corrected 2026-08-25** against a direct read of `work/user.db3` (venue 2, `FullArcCustomBars`) — supersedes the earlier cell-only, inferred version of this table. The earlier table only listed one bar's 9 cells against slot names and inferred the rest; it missed that a third par and both moving-head/bar-cell pairings physically share slots with other fixtures.

Measured slot occupancy, venue 2:

| slot | physical fixtures on it |
|---|---|
| 16 | bar1 cell 1 + bar2 cell 1 + LPC008S par #3 |
| 5, 2, 6, 3, 7 | bar cells 2, 4, 5, 7, 8 (both bars) |
| 11, 12, 13 | LM70S head #1/#2/#3 **and** bar cells 3, 6, 9 (both bars) |
| 14 | LM70S head #4 — exclusive |
| 17, 18 | LPC008S par #1, par #2 — exclusive |
| 111, 112 | bar 1 / bar 2 tilt block — exclusive, **independently controllable** |
| 1, 4, 8, 9, 10, 15, 19, 101, 102, 105, 106 | nothing — 11 unused slots |

Two facts this correction changes about how macro design must reason about this rig:

1. **Pars are not three independent slots.** The third LPC008S par sits on slot 16 *together with* the bottom bar cells (bar1 cell 1 + bar2 cell 1) — whatever macro curve slot 16 carries drives the floor par and both bars' bottom cell simultaneously. Slot 16 is best read as **"the floor"**, not as a spare par.
2. **The two bars' tilt blocks (slots 111, 112) are independent slots**, so the two bars CAN diverge in movement even though their cells always mirror. The older blanket claim "the two bars always mirror each other" is only true for the 9 cells (slots 16, 5, 2, 6, 3, 7, 11, 12, 13, which both bars share identically) — it does **not** apply to tilt/movement, which each bar controls through its own slot (111 vs 112) and can run out of phase with the other.

Because slots 11/12/13 host a moving head AND both bars' cells at that position simultaneously, movement (`<Position>`) programmed on those slots is "free" for the shared cells — the cells have no pan/tilt hardware and silently discard it (see "What actually renders" below), while the co-patched LM70S head actually moves. Slot 14 is the only moving head with no co-patched cell, so it is the only slot where brightness/colour is exclusively the head's own, not shared with a cell.

Slots left completely unused in venue 2 (11 of 25):

```
Par Light 1, Par Light 4, Bar Light 4, Bar Light 5, Bar Light 6, Strobe, Laser,
Par Light 1 (Simple), Par Light 2 (Simple), Bar Light 1 (Simple), Bar Light 2 (Simple)
```

(macro_fixture_id: 1, 4, 8, 9, 10, 15, 19, 101, 102, 105, 106.) These are exactly the slots available to break the cell mirror without touching anything already in use.

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

**Gobo (measured, 20/20 occurrences in `work/macro.db3`):** `<Gobo>` is always the empty self-closing tag — never populated with a wheel index, a colour, or any other payload. There is no known gobo-wheel payload format for this rig's hardware or macro library. The codebase models `<Gobo>` as presence-only (`gobo_present: bool | None` — `None` when the section is absent for a fixture type that doesn't support it, `False` when present-but-empty for one that does; see rekordbox-lightingdb-schema skill). Do not invent gobo content-generation logic — there is nothing observed to generate.

## Show-diversity baseline (measured, for reference)

2943 tracks total. 60% of them concentrate on just 2 of the 27 `macro_pattern` rows: pattern_id 1 = 39.5% (1162 tracks), pattern_id 7 = 20.7% (610 tracks). Each pattern is an 11-phase loop, so pattern 1 alone is effectively an 11-macro loop repeating across 40% of the library. Top individual macros by fire count: `HIGH CHORUS1 COOL` 5596×, `MID CHORUS COOL` 3517×, `HIGH UP1 COOL` 2924×. 173 of the 190 library macros are used at least once (178 enabled) — the macro *library* is adequate; the *distribution* across patterns/phrases is the actual problem any generation work should target.

## References

- Schema and XML payload details: `rekordbox-lightingdb-schema`
- Backup/write safety rules: `rekordbox-data-safety`

---

**Corrected 2026-08-25:** Replaced the inferred "Current slot assignment and its ceiling" table with a measured slot-occupancy table read directly from `work/user.db3` (venue 2). Two corrections that change macro design: (1) the third LPC008S par shares slot 16 with the bottom bar cells — pars are not three independent slots, slot 16 reads as "the floor"; (2) the bar tilt blocks (slots 111/112) are independent slots and can diverge in movement even though the bars' cells always mirror — the old "the two bars always mirror each other" statement only ever held for the cells. Also added a measured note that `<Gobo>` is always empty (20/20 observed in `work/macro.db3`) and is modeled presence-only.
