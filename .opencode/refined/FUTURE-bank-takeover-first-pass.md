---
epic: "FUTURE"
title: "Bank Takeover First Pass — Prove User Macro Fires on Real Track"
estimate: M
status: ready
created: 2026-08-23
depends_on: [ ]
labels: [ macro, bank, takeover, proof-of-concept ]
priority: P1
claimed_by:
claimed_by_date:
---

## 1. User Story

**As a** lighting engineer\
**I want** to replace one factory macro slot in the COOL bank's HIGH energy with a user-authored macro\
**So that** I can prove end-to-end that user macros fire on real tracks in a real set, and establish the takeover mechanism as safe and reversible\

## 2. Business Context & Value

The bank takeover feature enables users to author custom lighting sequences and inject them into rekordbox's factory macro slots, overriding the built-in behavior on real tracks during playback. This story proves the mechanism works by taking over a single high-impact slot (COOL bank, HIGH energy, phase 6 — the most-fired macro at 5607 phrase firings) and verifying that a user macro fires when a track in that slot plays.

**Why this matters:**
- Establishes that `macro_assign` is the correct takeover mechanism (not bulk `content` rewrites)
- Proves reversibility via `initial_macro_id` (factory defaults are preserved and can be restored)
- Validates that rekordbox does not prune or rewrite `macro_assign` on launch (the main risk to the whole approach)
- Unblocks M4 (phrase/pattern rebalance) by confirming `phrase_data` shadowing is negligible (36 of 41742 rows)
- Provides a repeatable pattern for widening to all 8 phases and other banks

**Live library facts (verified 2026-08-23):**
- COOL bank covers 1888 of 2966 tracks (63.7%)
- COOL / HIGH (`macro_pattern_id = 1`) covers 1162 tracks (39.2%)
- Phase 6 (`macro_id = 31`, `HIGH CHORUS1 COOL`) fires 5607 times — the single most-fired macro
- User macros exist in the library (8 rows, `preset=0`, ids 10001–10008)
- `phrase_data` shadowing is negligible (only 36 rows where `macro_id <> initial_macro_id`)

## 3. Acceptance Criteria

* [ ] **Scenario 1: Single-phase takeover (phase 6, COOL/HIGH)**
    * Given the live LightingDB with `macro_pattern_id = 1` (COOL/HIGH) and phase 6 currently pointing to factory macro 31 (`HIGH CHORUS1 COOL`)
    * When the user runs the takeover command to repoint phase 6 to a user macro (e.g., `10005` or `10006`)
    * Then `macro_assign` row `(1, 6, <user_macro_id>, 31)` is written to the working copy, with `initial_macro_id = 31` preserved

* [ ] **Scenario 2: Dry-run by default**
    * Given the takeover command is invoked without `--write`
    * When the command executes
    * Then no changes are written to the working copy; the command reports what would be changed and exits with success

* [ ] **Scenario 3: Explicit write required**
    * Given the takeover command is invoked with `--write`
    * When the command executes and the working copy is mutated
    * Then `push --write` is required to commit to the live LightingDB; the command reports the exact `push` command to run

* [ ] **Scenario 4: Reversibility via revert command**
    * Given a takeover has been pushed to the live LightingDB
    * When the user runs the revert command for the same (bank, energy, phase)
    * Then `macro_assign.macro_id` is restored to `initial_macro_id` (31 in this case) in the working copy; the command reports the exact `push` command to run

* [ ] **Scenario 5: Manual verification (user-performed)**
    * Given a takeover has been pushed and rekordbox has been relaunched
    * When the user plays a track in the COOL/HIGH category during a set
    * Then the user macro's lighting sequence fires during the phrase that previously fired the factory macro; the user observes the expected lighting change and confirms success

* [ ] **Scenario 6: Orphan tracks (61 tracks with `macro_pattern_id = 0`)**
    * Given the library contains 61 tracks pointing to a non-existent `macro_pattern` row
    * When the takeover command executes
    * Then the command reports the count of orphan tracks as a read-only observation; no attempt is made to fix or rewrite them

* [ ] **Scenario 7: User macro must exist and be valid**
    * Given the takeover command is invoked with a user macro ID that does not exist or is a factory macro (`preset=1`)
    * When the command executes
    * Then the command rejects the input with a clear error message and exits without mutating the working copy

* [ ] **Scenario 8: Backup and recovery**
    * Given the takeover is about to be pushed to the live LightingDB
    * When the push command executes
    * Then a backup of the current `macro.db3` and `user.db3` is created before any write; the command reports the backup path and the exact restore command

* [ ] **Scenario 9: Write atomicity and verification**
    * Given a takeover is being pushed
    * When the write completes
    * Then all changes are written in a single transaction; the command re-reads the live DB to verify the write succeeded; if verification fails, the backup is reported and the user is instructed to restore

* [ ] **Scenario 10: Rekordbox must not be running**
    * Given the takeover is about to be pushed
    * When the push command checks for a running rekordbox process
    * Then if rekordbox is running, the command exits with an error and instructions to quit rekordbox first; if not running, the push proceeds

## 4. Technical Constraints

* **Database**: Mutate `macro_assign` rows for `macro_pattern_id = 1` (COOL/HIGH), repointing `macro_id` to a user macro while preserving `initial_macro_id` as the factory default. Write in a single transaction. Never write `preset=1` factory macros (ids 1–916, -1, 10000). User macros are `preset=0`, id >= 10001.

* **Working copy model**: Follow the existing two-tier write model — mutate the working copy on disk, then `push --write` commits to the live LightingDB. Query logic must be in a repo module so the planned TUI can call it directly.

* **Safety**: Guard that rekordbox is not running before any live-DB write. Back up `macro.db3` and `user.db3` before writing. Verify the write by re-reading the live DB. Report the restore command. Never modify `master.db3` (read-only).

* **Reversibility**: `macro_assign.initial_macro_id` is the factory value and must never be written. Revert is `UPDATE macro_assign SET macro_id = initial_macro_id WHERE macro_pattern_id = ? AND phase = ?`. Provide a first-class revert command, not just a backup.

* **CLI surface**: Propose a `bank` command group with subcommands:
  - `bank list` — read-only: show the 8 banks × 3 energies, resolved names, track counts, current macro assignments
  - `bank takeover` — repoint one or more phases of one (bank, energy) to a user macro; dry-run by default, `--write` required for mutation
  - `bank revert` — restore `initial_macro_id` for one or more phases; dry-run by default, `--write` required

* **Testing**: Tests must never touch the live rekordbox directory, not even for reads. Use fixtures (in-memory or temporary SQLite files). Never modify `preset=1` factory macros. Preserve the 25-row invariant per macro write (if applicable to this story's scope).

* **Verification**: The story ends with a manual, user-performed verification step (quit rekordbox, push, relaunch, play a COOL/HIGH track, watch the chosen phase). Software cannot self-verify that the lights changed. Define exactly what the user should look for and what a failure looks like.

## 5. Design & UI/UX

**CLI interaction flow:**

1. User lists current bank state: `bank list` (read-only, no `--write` needed)
   - Output shows all 8 banks × 3 energies, resolved names (e.g., "COOL / HIGH"), track counts, and current macro assignments
   - Highlights phase 6 (COOL/HIGH) as the recommended starting point (5607 firings)

2. User previews the takeover: `bank takeover --bank COOL --energy HIGH --phase 6 --macro 10005` (dry-run)
   - Output shows what would change: "Phase 6 (HIGH CHORUS1 COOL) → user macro 10005"
   - Reports the exact `push --write` command to commit

3. User commits the takeover: `push --write` (after reviewing the dry-run)
   - Checks rekordbox is not running
   - Backs up `macro.db3` and `user.db3`
   - Writes the change in a single transaction
   - Re-reads to verify
   - Reports success and the restore command

4. User manually verifies: quit rekordbox, relaunch, play a COOL/HIGH track, watch phase 6
   - User observes the user macro's lighting sequence fire during the phrase
   - User confirms success or reports failure

5. If needed, user reverts: `bank revert --bank COOL --energy HIGH --phase 6` (dry-run), then `push --write`
   - Restores `macro_id = 31` (the factory default)

**Error handling:**
- User macro does not exist → reject with clear message
- User macro is a factory macro (`preset=1`) → reject with clear message
- Rekordbox is running → reject with instructions to quit first
- Write verification fails → report backup path and restore command

**N/A sections:**
- No TUI work in this story (planned separately)
- No changes to preview/visualizer
- No bulk `content.macro_pattern_id` rewriting (that is M4)

## 6. Scope & Context

**What changes:**
- `macro_assign` rows for `macro_pattern_id = 1` (COOL/HIGH) are repointed from factory macros to user macros
- `initial_macro_id` is preserved as the factory default and never written
- The working copy is mutated; `push --write` commits to the live LightingDB

**What does NOT change:**
- `content.macro_pattern_id` (that is M4, separate story)
- `phrase_data` (shadowing is negligible and not a blocker)
- `preset=1` factory macros (never written)
- `master.db3` (read-only, never written)
- `macro_old.db3` and `master_old.db3` (rekordbox's own pre-upgrade copies, never touched)

**Domain concepts:**
- **Bank**: A named set of 8 factory macro slots (COOL, NATURAL, HOT, SUBTLE, WARM, VIVID, CLUB1, CLUB2), corresponding to `macro_pattern.pattern` values 1–8
- **Energy**: A 3-step axis (HIGH, MID, LOW), corresponding to `macro_pattern.energy` values 1, 2, 3 respectively
- **Phase**: One of 8 phases within a (bank, energy) slot, corresponding to `macro_assign.phase` values 1–8 (INTRO1, INTRO2, UP1, UP2, UP3, CHORUS1, CHORUS2, DOWN)
- **Macro pattern**: A row in `macro_pattern` that defines a (bank, energy) combination and its 8 phases via `macro_assign`
- **Factory macro**: A preset macro (`preset=1`), ids 1–916, -1, 10000; never written by the user
- **User macro**: A custom macro (`preset=0`), id >= 10001; can be authored and used in takeovers
- **Takeover**: Repointing a phase's `macro_id` from a factory macro to a user macro, preserving `initial_macro_id` as the revert path

**Known pitfalls:**
- Rekordbox may prune or rewrite `macro_assign` on launch (the main risk; manual verification answers this)
- User macro's `beats` may need to match the factory macro it replaces for phase timing to line up (open question; manual verification will reveal this)
- `macro.enabled` may need to be 1 for a macro to fire (open question; manual verification will reveal this)
- 61 tracks point to `macro_pattern_id = 0` (non-existent); treat as read-only observation, do not fix

**Existing behavior affected:**
- When a COOL/HIGH track plays, phase 6 will fire the user macro instead of the factory macro (if takeover is active)
- Reverting restores the factory macro without data loss (via `initial_macro_id`)

## 7. Test Impact Analysis

**Existing tests affected:**

N/A — this is a greenfield feature. No existing tests assert behavior that changes.

**Test modification policy:**

- [ ] No existing tests should be modified (greenfield)

**Existing files impacted:**

N/A — no existing behavior is changed, only new functionality added.

---

## Open Questions (to be answered by manual verification or implementation)

1. **Does `macro.enabled` need to be 1 for a macro to fire?** The live library has user macros with `enabled=0`. Manual verification will reveal whether the user macro fires regardless of this flag.

2. **Does rekordbox prune or rewrite `macro_assign` on launch?** This is the main risk to the whole approach. Manual verification (quit rekordbox, push, relaunch, play a track) will answer this definitively.

3. **Must the user macro's `beats` match the factory macro it replaces for phase timing to line up?** The user macro may have a different beat count. Manual verification will reveal whether timing is affected.

4. **Are there any other constraints on user macros that prevent them from firing?** (e.g., fixture compatibility, pattern constraints). Manual verification will reveal this.

---

## Documentation Corrections (dated 2026-08-23)

The following stale or incorrect documentation must be corrected in this story:

1. **`rekordbox-lightingdb-schema` skill:**
   - Document `macro_assign` fully, including the `initial_macro_id` column and its semantics (factory default, revert path)
   - Correct the energy mapping: `energy = 1` is HIGH, `energy = 2` is MID, `energy = 3` is LOW (not the reverse)
   - Correct the claim that bank names live nowhere in the DB — they are encoded as the suffix of factory macro names (8 banks: COOL, NATURAL, HOT, SUBTLE, WARM, VIVID, CLUB1, CLUB2)
   - Document the factory macro naming convention: `<ENERGY> <PHASE> <BANK>` (e.g., `HIGH CHORUS1 COOL`, `MID VERSE1 COOL`, `LOW CHORUS COOL`, `CHORUS CLUB1`)
   - Document the `macro.enabled` column and its purpose

2. **`.opencode/BACKLOG.md`:**
   - Mark the decision "Which bank and energy to prove the takeover on?" as resolved: **COOL bank, starting at HIGH energy (`macro_pattern_id = 1`)**
   - Update the stale track count from 2943 to **2966** (as of 2026-08-23)
   - Record that the `phrase_data` shadowing question is answered: **36 of 41742 rows are overridden** (negligible); this finding unparks the M4 phrase/pattern rebalance question
   - Correct the text "bank names live nowhere in any database" — they are encoded in factory macro names
   - Note that the speculative 9th-bank item is now even less attractive because the 8 bank names are fixed and `macro_assign` gives a clean takeover path

3. **`physical-rig-profile` skill:**
   - If it asserts an energy ordering, correct it to: **1 = HIGH, 2 = MID, 3 = LOW**

---

## Implementation Notes for Agents

**Mandatory skills to load:**
- `.opencode/skills/rekordbox-data-safety/SKILL.md` (MANDATORY before any DB code)
- `.opencode/skills/rekordbox-lightingdb-schema/SKILL.md`
- `.opencode/skills/physical-rig-profile/SKILL.md`
- `.opencode/skills/rekordbox-lighting-architecture/SKILL.md`

**Recommended starting point:**
- Start with a single phase (phase 6, COOL/HIGH) to keep the proof minimal and unmistakable
- Once the single-phase proof lands and is verified, widen to all 8 phases in a follow-up story

**Query logic placement:**
- Bank query logic (list, resolve names, count tracks) must be in a repo module so the planned TUI can call it directly
- Follow the pattern established by the macro-discovery story

**Two-tier write model:**
- Mutate the working copy on disk
- `push --write` commits to the live LightingDB
- Never write directly to the live DB outside of `push`

**Safety checklist:**
- [ ] Guard that rekordbox is not running before any live-DB write
- [ ] Back up `macro.db3` and `user.db3` before writing
- [ ] Write in a single transaction
- [ ] Re-read the live DB to verify the write succeeded
- [ ] Report the backup path and restore command
- [ ] Never modify `preset=1` factory macros or `master.db3`
- [ ] Tests use fixtures, never touch the live rekordbox directory

**Verification checklist (user-performed):**
- [ ] Quit rekordbox
- [ ] Run `push --write` to commit the takeover
- [ ] Relaunch rekordbox
- [ ] Play a COOL/HIGH track during a set
- [ ] Watch phase 6 (CHORUS1) and confirm the user macro's lighting sequence fires
- [ ] If successful, the takeover is proven; if not, report the failure and restore via `bank revert`
