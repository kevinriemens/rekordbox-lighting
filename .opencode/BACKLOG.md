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
| `FUTURE-bank-takeover-first-pass` | Future | M | COOL bank, HIGH energy (1162 tracks, 39.2%). Repoints `macro_assign` rows; `initial_macro_id` gives free revert. |
| `RIG-calibration-session` | RIG | M | One physical session answering all five rig questions. Observe with rekordbox running, apply every change after quitting it. |
| `FUTURE-fullarcai-venue` | Future | L | Third venue breaking the bar mirror (bars are mounted vertically, not horizontally, so cells form two columns not one surface). Two arch legs can finally do different things. |

**Table pruned 2026-08-25.** It had drifted — `BUGS-ship-margin-fraction-in-preview-payload`,
`REFACTOR-split-preview-layout-module` and `TUI-interactive-menu` were all still listed as ready to
build despite having shipped on 2026-08-24. They are in `CHANGELOG.md` with audit copies in
`completed/`. The rows above are now exactly the three files in `.opencode/refined/`; keep it that way.

**Build order note:** `FUTURE-bank-takeover-first-pass` is the highest-value item in this file and
the one most likely to change the plan. Its finding gates the CLUB1+CLUB2 follow-up and M4. It is now
also the *only* remaining route to customised lighting on a playable bank — see the ninth-bank verdict
below.

## Ready to refine

Design is settled; the story just needs writing. Run `/refine` to move these into `refined/`.

- [ ] **Role-based YAML macro recipes** *(added 2026-08-25)* — **M**

  **Decision that created this item:** content must not be code. The `RETRO70` story generated three
  macros from an 832-line `festive_presets.py`, which put palettes, phase offsets and hold lengths in
  `src/`. That was the wrong home and the file was removed rather than committed. The engine it stood
  on (`compose.py` + the curve vocabulary) was kept.

  **Why it matters beyond tidiness:** the endgame is a shareable tool. `yaml_io.py`'s existing schema
  keys `fixtures:` by *slot id*, which freezes a macro to one rig — `macro_exports/*.yaml` are exactly
  that and are useless to anyone whose venue differs. Keying by **role** instead (`bar_cells`,
  `moving_heads`, `floor`, `bar_tilts`) lets one recipe resolve against whatever venue is active, which
  is the difference between "three macros I made" and "a macro library the tool ships".

  **The DSL does not need inventing.** The vocabulary already exists and is already tested as the
  promoted curve functions: `raised_cosine`, `attack_decay`, `square_wave`, `constant`,
  `hold_then_snap`, `smooth_loop`, plus a movement spec. The recipe schema is a declarative binding to
  those, e.g.

  ```yaml
  name: RETRO70 DISCO INFERNO
  beats: 32
  palette: ["#FF0000", "#FF5500", "#FFD000", "#FF00C8", "#FFFFFF"]
  roles:
    bar_cells:
      brightness: { curve: attack_decay, every: 1, peak: 1.0, floor: 0.15,
                    decay: 0.5, phase_by_index: [0, 0.5] }
      colour:     { curve: hold_then_snap, hold: 2, offset_by_index: 1 }
      strobe:     [[28, 32]]
    moving_heads:
      movement:   { pattern: Circle, period_ms: 5000, width: 70, height: 55,
                    type: Loop, alternate_direction: true }
  ```

  **Scope:** recipe schema + loader, role→slot resolver driven by the active venue, `macro build FILE`
  style CLI (dry-run by default like every other mutating command), the three RETRO70 macros re-expressed
  as recipe files, schema-validation tests only for content. Tests concentrate on loader and resolver.

  **Reference output to reproduce:** `macro_exports/retro70-{glitterball,rainbow-stairs,disco-inferno}.yaml`
  are byte-level exports of the accepted macros (currently `work/macro.db3` ids 10007–10009). Recipes
  should regenerate visually equivalent macros; exact byte equality is not required.

  **Creative spec of the three macros** (all 32 beats, venue 2, bar cells bottom→top `16,5,11,2,6,12,3,7,13`):
  - `GLITTERBALL` — verse/intro. Warm rotation gold `#FFB000` → amber `#FF6A00` → hot pink `#FF2D95` →
    violet `#7B2FF7` at beats 0/8/16/24, smooth. Cell *i* starts the palette at `i % 4`. Raised-cosine
    swell, floor `0.25`, two rises, cell *i* phase-shifted `i*16/9` beats. Heads Circle/20000/Loop
    (13 Backward). Tilts Line2/20000/PingPong opposed. No strobe.
  - `RAINBOW STAIRS` — chorus. Nine hues bottom→top `#FF0000 #FF5A00 #FFA800 #FFE800 #7CFF00 #00E05A
    #00D6D6 #2A4BFF #E000FF`. Four 8-beat rises; cell *i* holds hue `(i+r) % 9` in rise *r*,
    hold-then-snap. Attack staggered `8/9` beats, floor `0.08`, ~60% overlap. Pars alternate on the
    half-bar, 17 warm / 18 cool. Heads Line2/8000/PingPong crossing. Tilts Line/16000/PingPong opposed.
  - `DISCO INFERNO` — drop. Hot palette above. Four-on-the-floor; even-index cells on integer beats,
    odd-index on off-beats (checkerboard). Slot 16 is the floor: white punch every 4th beat, red
    between. Colour flips every 2 beats, cell *i* starts at `i % 5`. Pars baseline `0.85` hitting `1.0`
    each beat, strobe `[6,8) [14,16) [22,24) [28,32)`. Heads Circle/5000/Loop. Tilts Line/4000/PingPong
    opposed — the one place the two bars visibly diverge. Cell strobe burst `[28,32)`.

  **Depends on:** nothing. `compose.py` and the curve vocabulary shipped in the RETRO70 story.

## Open physical sessions

Work that cannot be delegated — it needs the user at the rig or at rekordbox.

Nothing open. New items go here.

- [x] **Ninth-bank experiment — RUN 2026-08-25. Verdict: NO. Closed, do not reopen.**
      A probe bank `(id=28, energy=1, pattern=9)` with 10 `macro_assign` rows cloned from bank 19
      (CLUB1 HIGH) was pushed live and rekordbox was launched.

      **It is invisible.** The bank appeared nowhere — not in performance mode, not in macro mapping
      mode. The mood/bank selector is a fixed 8-button surface, so an unknown `pattern` value has no
      way in and can never be selected or assigned by hand. Stage 2 (force-repointing a track) was
      deliberately skipped: a bank you cannot reach from the CDJs mid-set is not worth having, and the
      bank takeover delivers the same outcome on a bank that is already labelled and already selectable.

      **It was not pruned.** The row survived rekordbox's launch completely intact, version counters
      unchanged, nothing else touched. **Storage tolerates unknown rows; the UI is the hard limit.**
      That rule is the durable result and is recorded in `rekordbox-lightingdb-schema/SKILL.md` and
      `docs/PROJECT-FOUNDATION.md` §6.2. The DB was reverted to baseline and the disposable
      `src/rbxlight/experiments/` package and its tests have been deleted.

      **Runbook erratum:** earlier versions of this item said `pull --write`. `pull` takes no flag —
      it only ever writes the disposable working copy, so there is no dry-run gate on it.

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
