# Backlog

Unrefined ideas and future work, grouped by **what is blocking them** — because the blocker
determines who can move the item forward, and most of these are waiting on the user, not on
engineering.

- **Ready to build** → run `/build <story>`; the spec is written.
- **Blocked on a decision** → one answer from the user unblocks refinement.
- **Blocked on the rig** → needs the physical lights wired; items are batched into refined stories.
- **Not refinable yet** → the idea itself still needs rethinking.
- **Chores** → no story needed, just do it.

Shipped work lives in `CHANGELOG.md` with audit copies in `completed/`. Do not track it here.

---

## Ready to build

Specs are in `.opencode/refined/`. Detail lives in the story files — these are pointers, not summaries.

| Story | Epic | Size | One-line |
|---|---|---|---|
| `BUGS-ship-margin-fraction-in-preview-payload` | Bugs | S | One source of truth for the 5% margin; browser reads it from the payload. |
| `FUTURE-bank-takeover-first-pass` | Future | M | COOL bank, HIGH energy (1162 tracks, 39.2%). Repoints `macro_assign` rows; `initial_macro_id` gives free revert. |
| `REFACTOR-split-preview-layout-module` | Refactor | M | Splits the 955-line `preview/layout.py` into four flat siblings (geometry, segments, placement, io) behind a re-export facade. Pure refactor — all 103 existing tests must pass unmodified. |
| `TUI-extract-shared-write-layer` | TUI | M | Prerequisite refactor. Completes `write_transaction` with an injectable verify, promotes `_working_copy_write` out of `cli.py`, adds typed plan objects. Pure refactor — existing tests must pass unmodified. |
| `TUI-interactive-menu` | TUI | L | `questionary` menu over the domain layer. Full CLI parity, mandatory dry-run → render → confirm on every mutation, louder gate for live writes. |
| `RIG-calibration-session` | RIG | M | One physical session answering all five rig questions. Observe with rekordbox running, apply every change after quitting it. |
| `FUTURE-fullarcai-venue` | Future | L | Third venue breaking the bar mirror (bars are mounted vertically, not horizontally, so cells form two columns not one surface). Two arch legs can finally do different things. |
| `FUTURE-ninth-bank-experiment` | Future | S | Bounded, reversible experiment: does rekordbox honour a `macro_pattern` row with `pattern = 9`? Deliverable is a documented YES or NO, not a shipped command. Run it after the takeover. |

**TUI build order:** ~~`CLI_COMPLETENESS-macro-discovery-commands`~~ (shipped 2026-08-24) → `TUI-extract-shared-write-layer`
→ `TUI-interactive-menu`. The refactor is not optional: without it the TUI hand-rolls safety
sequencing and becomes a second, unguarded write path.

**Build order note:** `BUGS-ship-margin-fraction-in-preview-payload` is independent of everything else and is the cheapest
wins. `FUTURE-bank-takeover-first-pass` is the highest-value item in this file and the one most
likely to change the plan. Its finding gates the CLUB1+CLUB2 follow-up and M4.

**Build order note:** `FUTURE-ninth-bank-experiment` runs after `FUTURE-bank-takeover-first-pass`, and may well be
cancelled by it. The takeover delivers the same practical outcome — customised lighting on a bank
the user actually plays — on a bank that is already labelled and already selectable, without
betting on undocumented rekordbox behaviour. The ninth bank is only worth the risk if the takeover
proves insufficient.

**Dependencies:**
- `FUTURE-fullarcai-venue` depends on `RIG-calibration-session`, specifically the item confirming which physical moving head sits on which truss segment. Designing a new fixture-to-slot assignment on an unverified physical mapping risks designing the wrong show.
- `FUTURE-fullarcai-venue` should follow `FUTURE-bank-takeover-first-pass`. Without the takeover proving a user-authored macro actually fires on a real track, a third venue is just a more elaborate way to play the same factory programming.
- `RIG-calibration-session` is worth doing early and is independent of all code stories. Its visualizer verdict retroactively raises or lowers confidence in every macro generated so far, and item 5 feeds the bank-takeover story's user-facing vocabulary.

---

## Blocked on a decision

Nothing is currently blocked on a decision. This section is where new blocking questions go.

---

## Blocked on the rig

All five items have been batched into `RIG-calibration-session` (see "Ready to build"). The setup cost is identical for one as for five, and three are answered by simply looking at the rig.

**Correction recorded 2026-08-23:** The item "Bar sweep direction may be inverted" proposed flipping `DEFAULT_TILT_BLOCK_ROTATION_DEGREES` from 90° to 270°. This is wrong. Test `test_should_never_give_the_two_tilt_blocks_opposing_mounting_rotations` asserts both bars always receive the SAME mounting rotation. The mirrored sweep seen on stage comes from each fixture's own `tilt_reversal` DMX flag, sourced from `user.db3` `fixture.tilt_reversal` — never from opposing mounting-rotation constants. Flipping both would double-mirror, which is the exact bug that test guards against. Do not re-propose changing `DEFAULT_TILT_BLOCK_ROTATION_DEGREES`.

**Also recorded 2026-08-23:** The "Confirm the rekordbox panel vocabulary" item changed premise. The CLI and README currently use no bank/energy/mood/phase wording at all, so there is nothing to reconcile yet. The item is now about capturing rekordbox's exact on-screen wording BEFORE the bank-takeover story introduces a `bank` command and puts those words in front of the user — cheaper than renaming a shipped command later.


---

## Not refinable yet

- [ ] **M4 — Phrase/pattern rebalance** *(parked behind the bank takeover — 2026-08-23)*
   2966 tracks, but 60% sit on just 2 of 27 macro_patterns (pattern 1 = 39.2%, pattern 7 = 20.7%).
   Each pattern is a phase loop, so a long set cycles the same handful of macros — `HIGH CHORUS1 COOL`
   alone fires 5607×. Spreading tracks across all 27 patterns is the change that most affects how a
   4-hour set feels, and requires no change to how the user plays. Dry-run diff first, fully reversible.

   **Shadowing question answered:** of 41742 `phrase_data` rows across 2905 distinct tracks, only **36** have `macro_id <> initial_macro_id` (user-overridden), and zero have a NULL `macro_id`. Shadowing is negligible, so a rebalance would not be limited to newly-analysed tracks. **Orphan group:** 61 tracks point at `macro_pattern_id = 0`, for which no `macro_pattern` row exists — worth investigating during M4.

  **Parked deliberately, not deprioritised.** Rebalancing today only spreads tracks across banks that
  all still play factory programming — it redistributes the same show. After the takeover lands there
  is something worth spreading onto, and the heuristic can target the banks actually customised.
  Also decided: bank selection should be informed by what the tracks actually *are* (genre/energy,
  looked up externally), not BPM alone — a BPM-only heuristic puts a deep-house record and a
  hard-techno record in the same bank.

  **Down to one item.** This section previously held five items; four have been refined into stories or
  cancelled. M4 is waiting on the bank takeover to land, so there is something worth spreading tracks
  onto. Once the takeover ships, M4 becomes ready to build.



---

## Chores

Nothing open. Completed chores are recorded in `CHANGELOG.md`, not here.

**Noted while clearing the M1 test macros (2026-08-24):** `10002 TEST BAR` (16 beats, `enabled=0`)
also looks like a leftover test macro, but it predates this tool and was not part of the chore's
scope, so it was left alone. Confirm whether it is yours before deleting it.


---
