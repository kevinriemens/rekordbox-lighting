---
epic: "FUTURE"
title: "Ninth Bank Experiment — Does rekordbox Honour an Unknown Pattern Value?"
estimate: S
status: ready
created: 2026-08-23
depends_on: [ "FUTURE-bank-takeover-first-pass" ]
labels: [ macro, bank, experiment, observational, reversible ]
priority: P2
claimed_by:
claimed_by_date:
---

## 1. User Story

**As a** lighting engineer\
**I want** to test whether rekordbox will accept and honour a `macro_pattern` row with a `pattern` value (9) that has no UI button and no factory macro names\
**So that** I can answer a standing speculative question definitively and either close the item or promote it to a real feature\

## 2. Business Context & Value

This is deliberately **NOT a feature story**. It is a **bounded, reversible experiment** with a single question to answer:

> Does rekordbox honour a `macro_pattern` row with a `pattern` value it has no UI button for?

The outcome is a documented YES or NO, plus the doc corrections that follow. If the answer is NO, the story still succeeded — it closes a speculative backlog item permanently and stops it resurfacing.

**Why this matters:**
- The bank takeover story (`FUTURE-bank-takeover-first-pass`) delivers the same practical outcome — customised lighting on a bank the user actually plays — without betting on unknown rekordbox behaviour, and it does so on a bank that is already labelled and already selectable.
- The ninth bank only becomes interesting if the takeover proves insufficient.
- If the takeover lands well, consider closing this item rather than running it.
- The cost is one careful hour and a real risk to `content` (2966 rows of user work); the benefit is one bit of information. That is a fair trade only because the answer is otherwise unknowable and the item keeps resurfacing.

**Confirmed schema facts (audited read-only from the live DB, 2026-08-23 — treat as ground truth):**
- `macro_pattern` has exactly 27 rows, `max(id) = 27`. Columns: `id`, `energy`, `pattern`.
- `energy` is **1 = HIGH, 2 = MID, 3 = LOW** (inverted from what the project previously believed — corrected 2026-08-23).
- `pattern` takes values 1..8 (the eight named banks) plus 99 (a separate non-bank case, ids 25/26/27).
- Full current table, grouped as (id, energy, pattern) → number of `macro_assign` phases:
  - pattern 1 (COOL):    id 1 e1 → 11 phases; id 7 e2 → 10; id 13 e3 → 6
  - pattern 2 (NATURAL): id 2 e1 → 11; id 8 e2 → 10; id 14 e3 → 6
  - pattern 3 (HOT):     id 3 e1 → 11; id 9 e2 → 10; id 15 e3 → 6
  - pattern 4 (SUBTLE):  id 4 e1 → 11; id 10 e2 → 10; id 16 e3 → 6
  - pattern 5 (WARM):    id 5 e1 → 11; id 11 e2 → 10; id 17 e3 → 6
  - pattern 6 (VIVID):   id 6 e1 → 11; id 12 e2 → 10; id 18 e3 → 6
  - pattern 7 (CLUB1):   id 19 e1 → **10**; id 21 e2 → 10; id 23 e3 → 6
  - pattern 8 (CLUB2):   id 20 e1 → **10**; id 22 e2 → 10; id 24 e3 → 6
  - pattern 99:          id 25 e1 → 6; id 26 e2 → 6; id 27 e3 → 6
- Note the shape difference: banks 1-6 have 11 phases at HIGH energy, but the two CLUB banks have only 10. So there is no single universal phase count — the story must NOT hardcode 11.
- `macro_assign` has 232 rows. It maps `(macro_pattern_id, phase) → macro_id` and preserves the factory default in `initial_macro_id`. Phase numbers are contiguous from 1.
- `content` has 2966 rows of real user work — the per-track bank assignment. **It is the highest-value data in the whole project and the experiment writes to it.**
- 61 tracks currently point at `macro_pattern_id = 0`, which has no matching `macro_pattern` row. These are pre-existing orphans. They are evidence that rekordbox tolerates dangling `macro_pattern_id` references without visibly exploding — weak but relevant prior evidence.
- `lighting_property` holds live panel state including `MoodLastId=2`, `BankLastId=3`, `MacroVersionNum=1061`, `DbVersionNum=1854`. The version counters are worth recording before and after the experiment: if rekordbox rewrites the DB on launch it may bump them.

**Bank names:**
- There is **no name column anywhere** on `macro_pattern`. Bank names are recoverable only as the final token of factory macro names, in the shape `<ENERGY> <PHASE> <BANK>` — e.g. `HIGH CHORUS1 COOL`, `MID VERSE1 COOL`, `CHORUS CLUB1`.
- The consequence, which is central to this story: **a new `pattern = 9` has no name source at all.** Even if rekordbox honours the row, the bank would be unlabeled in the UI, because the label is keyed off the pattern integer and there is no ninth entry.

**The two predicted failure modes (the actual hypotheses under test):**

1. **Unreachable via the mood selector.** The panel's mood/bank selector is almost certainly a fixed 8-button row. A `pattern=9` bank would have no button, so the user could never select it manually. Worse: touching that selector for an affected track would likely snap it back into the 1..8 range, silently destroying the assignment.
2. **Pruning on load.** rekordbox may drop or rewrite `macro_pattern` / `macro_assign` / `content` rows it does not recognise when it loads the DB. If so, the experiment's rows vanish — and the concern is whether it prunes *only* the unknown rows or takes a heavier hand.

Both are falsifiable in one launch of rekordbox.

## 3. Acceptance Criteria

* [ ] **Scenario 1: Backup exists and restore command is recorded**
    * Given the experiment is about to begin
    * When the user runs the backup command
    * Then a timestamped backup of `macro.db3` and `user.db3` is created; the exact restore command is recorded in the story's results section before any write

* [ ] **Scenario 2: Dry run proves the blast radius**
    * Given the experiment's INSERT and UPDATE statements are prepared
    * When the user runs them in dry-run mode (no `--write`)
    * Then the command reports exactly what would change: +1 `macro_pattern` row, +10 `macro_assign` rows, 1 `content` row repointed; no actual write occurs

* [ ] **Scenario 3: Single transaction with rekordbox confirmed not running**
    * Given the dry run is approved
    * When the user runs the write command with `--write`
    * Then rekordbox is confirmed not running; all changes are written in a single transaction; the command re-reads to verify all rows are present

* [ ] **Scenario 4: Row counts after Phase 1 match expected delta**
    * Given Phase 1 (insert) is complete
    * When the user re-reads the DB
    * Then `macro_pattern` count is baseline + 1; `macro_assign` count is baseline + 10; `content` count is baseline + 0 (only one row repointed, not added)

* [ ] **Scenario 5: Observation in Phase 2 is recorded verbatim**
    * Given rekordbox is launched and the throwaway track is loaded
    * When the user observes the track's behaviour
    * Then the following are recorded verbatim: track loads or errors; mood/bank selector display; whether lighting plays; whether touching the selector snaps the track back to 1..8

* [ ] **Scenario 6: Verdict is written into the schema skill, dated**
    * Given Phase 3 (re-read and verdict) is complete
    * When the user writes the verdict
    * Then the verdict (YES or NO) is recorded in `.opencode/skills/rekordbox-lightingdb-schema/SKILL.md` with the date 2026-08-23; the finding is permanent and dated

* [ ] **Scenario 7: Phase 4 cleanup restores all counts to baseline exactly**
    * Given Phase 4 (cleanup) is executed
    * When the user deletes row 28 and its `macro_assign` rows, and restores the throwaway track's original `macro_pattern_id`
    * Then `macro_pattern` count, `macro_assign` count, and `content` count all match the Phase 0 baseline exactly; the DB is left in its original state

* [ ] **Scenario 8: If rekordbox appears to have rewritten data beyond the experiment's own rows, restore from backup**
    * Given Phase 3 (re-read) reveals unexpected changes outside the experiment's scope
    * When the user detects this
    * Then the runbook stops immediately; the user restores from the backup created in Phase 0 rather than continuing

## 4. Technical Constraints

* **Database**: Insert one `macro_pattern` row (`id = 28`, `energy = 1`, `pattern = 9`). Insert 10 `macro_assign` rows (`macro_pattern_id = 28`, phases 1..10, pointing to existing factory macros from `macro_pattern_id = 19` / CLUB1 HIGH). Repoint one `content` row to `macro_pattern_id = 28`. All in a single transaction. Never write `preset=1` factory macros.

* **Safety**: Guard that rekordbox is not running before any write. Back up `macro.db3` and `user.db3` before writing. Verify the write by re-reading the live DB. Report the restore command. Never modify `master.db3` (read-only).

* **Reversibility**: All changes must be reversible by deleting row 28 and its `macro_assign` rows, and restoring the throwaway track's original `macro_pattern_id`. This must happen regardless of the verdict — a positive result does not license leaving the experiment in place.

* **Dry-run by default**: Every mutating command prints a diff/plan and changes nothing unless an explicit `--write` flag is passed. There is no implicit write, anywhere, ever.

* **Testing**: Tests must never touch the live rekordbox directory, not even for reads. Use fixtures (in-memory or temporary SQLite files).

## 5. Design & UI/UX

N/A — this is an observational experiment, not a feature build.

## 6. Scope & Context

**What changes:**
- One new `macro_pattern` row (id 28, pattern 9) is inserted
- 10 new `macro_assign` rows are inserted, mapping phases 1..10 to existing factory macros
- One `content` row (the throwaway track) is repointed to the new pattern
- `lighting_property` version counters are recorded before and after

**What does NOT change:**
- No other `content` rows are touched
- No factory macros are modified
- No `preset=1` rows are written
- `master.db3` is never touched
- The experiment is fully reversible

**Domain concepts:**
- **Pattern**: A value in `macro_pattern.pattern` (1..8 for named banks, 99 for a separate case, 9 for this experiment)
- **Macro pattern**: A row in `macro_pattern` that defines a (bank, energy) combination and its phases via `macro_assign`
- **Macro assign**: A row mapping `(macro_pattern_id, phase)` to a concrete `macro_id`
- **Content**: A row mapping a track to a `macro_pattern_id`

**Known pitfalls:**
- Rekordbox may prune or rewrite `macro_pattern` / `macro_assign` / `content` rows it does not recognise on load (the main risk)
- The ninth bank has no name source, so even if rekordbox honours it, the UI would show it as unlabeled
- The mood/bank selector is almost certainly a fixed 8-button row, making pattern 9 unreachable manually

**Existing behavior affected:**
- If the experiment succeeds, one throwaway track will fire lighting from pattern 9 instead of its original pattern
- If the experiment fails, rekordbox may prune the rows, and the track may snap back to its original pattern or to a default

## 7. Test Impact Analysis

N/A — this is an observational experiment, not a code change. No existing tests are modified.

---

## 8. Experiment Runbook — Execute Top to Bottom

### Phase 0 — Prepare

**Goal**: Establish a safe restore point and record baseline state.

**Checklist**:

- [ ] **Quit rekordbox fully** (not just switch views)
- [ ] **Take a full backup** via the project's existing safety path:
  ```bash
  rbxlight backup --trigger "FUTURE-ninth-bank-experiment Phase 0"
  ```
  Record the exact restore command printed by the backup tool and paste it into the story's results section before touching anything.

- [ ] **Record baseline counts**:
  ```bash
  sqlite3 ~/Library/Application\ Support/Pioneer/rekordbox6/LightingDB/macro.db3 "SELECT COUNT(*) FROM macro_pattern;"
  sqlite3 ~/Library/Application\ Support/Pioneer/rekordbox6/LightingDB/macro.db3 "SELECT COUNT(*) FROM macro_assign;"
  sqlite3 ~/Library/Application\ Support/Pioneer/rekordbox6/LightingDB/user.db3 "SELECT COUNT(*) FROM content;"
  ```
  Record these three numbers.

- [ ] **Record baseline version counters**:
  ```bash
  sqlite3 ~/Library/Application\ Support/Pioneer/rekordbox6/LightingDB/user.db3 "SELECT key, value FROM lighting_property WHERE key IN ('MacroVersionNum', 'DbVersionNum');"
  ```
  Record these two values.

- [ ] **Pick ONE throwaway track** — a track the user does not care about. Record its `content.id` and its current `macro_pattern_id`:
  ```bash
  sqlite3 ~/Library/Application\ Support/Pioneer/rekordbox6/LightingDB/user.db3 "SELECT id, macro_pattern_id FROM content WHERE id = <chosen_id>;"
  ```
  Record both values in writing — this is the value to restore in Phase 4.

**Outcome**: Backup exists, restore command recorded, baseline counts and version counters recorded, throwaway track identified.

---

### Phase 1 — Insert

**Goal**: Insert one new `macro_pattern` row and its `macro_assign` rows, and repoint the throwaway track.

**Checklist**:

- [ ] **Prepare the INSERT statements** (dry run first, no `--write`):
  ```bash
  rbxlight experiment ninth-bank --dry-run
  ```
  This should report:
  - INSERT 1 row into `macro_pattern`: `id = 28`, `energy = 1`, `pattern = 9`
  - INSERT 10 rows into `macro_assign`: `macro_pattern_id = 28`, phases 1..10, `macro_id` and `initial_macro_id` pointing to existing factory macros from `macro_pattern_id = 19` (CLUB1 HIGH)
  - UPDATE 1 row in `content`: repoint the throwaway track to `macro_pattern_id = 28`

- [ ] **Review the dry-run output** and confirm the blast radius is exactly as expected.

- [ ] **Execute the write** (with `--write`):
  ```bash
  rbxlight experiment ninth-bank --write
  ```
  The command should:
  - Confirm rekordbox is not running
  - Back up `macro.db3` and `user.db3` (if not already done in Phase 0)
  - Execute all changes in a single transaction
  - Re-read the DB to verify all rows are present
  - Report success and the restore command

- [ ] **Verify by re-read**:
  ```bash
  sqlite3 ~/Library/Application\ Support/Pioneer/rekordbox6/LightingDB/macro.db3 "SELECT * FROM macro_pattern WHERE id = 28;"
  sqlite3 ~/Library/Application\ Support/Pioneer/rekordbox6/LightingDB/macro.db3 "SELECT COUNT(*) FROM macro_assign WHERE macro_pattern_id = 28;"
  sqlite3 ~/Library/Application\ Support/Pioneer/rekordbox6/LightingDB/user.db3 "SELECT macro_pattern_id FROM content WHERE id = <throwaway_id>;"
  ```
  Confirm: row 28 exists with `energy = 1, pattern = 9`; 10 `macro_assign` rows exist; throwaway track points to 28.

**Outcome**: Row 28 and its 10 `macro_assign` rows are inserted; throwaway track is repointed; all changes verified by re-read.

---

### Phase 2 — Observe

**Goal**: Launch rekordbox, load the throwaway track, and record what happens.

**Checklist**:

- [ ] **Launch rekordbox** and load the throwaway track.

- [ ] **Observe and record verbatim**:
  - Does the track load at all, or does rekordbox error?
  - What does the mood/bank selector display for it — a blank, a fallback to bank 1, something else?
  - Does the lighting actually play, and does it play the macros assigned to pattern 9?
  - Touch the mood selector once. Does the track snap back into 1..8?

- [ ] **Record the observation** in the story's results section.

- [ ] **Quit rekordbox** fully.

**Outcome**: Observation recorded verbatim.

---

### Phase 3 — Re-read and Verdict

**Goal**: Re-read the DB and determine whether row 28 survived.

**Checklist**:

- [ ] **Re-read the DB**:
  ```bash
  sqlite3 ~/Library/Application\ Support/Pioneer/rekordbox6/LightingDB/macro.db3 "SELECT * FROM macro_pattern WHERE id = 28;"
  sqlite3 ~/Library/Application\ Support/Pioneer/rekordbox6/LightingDB/macro.db3 "SELECT COUNT(*) FROM macro_assign WHERE macro_pattern_id = 28;"
  sqlite3 ~/Library/Application\ Support/Pioneer/rekordbox6/LightingDB/user.db3 "SELECT macro_pattern_id FROM content WHERE id = <throwaway_id>;"
  sqlite3 ~/Library/Application\ Support/Pioneer/rekordbox6/LightingDB/user.db3 "SELECT key, value FROM lighting_property WHERE key IN ('MacroVersionNum', 'DbVersionNum');"
  ```

- [ ] **Compare against Phase 0 baseline**:
  - Is row 28 still present?
  - Are its 10 `macro_assign` rows intact?
  - Did `content.macro_pattern_id` for the throwaway track survive?
  - Did `MacroVersionNum` / `DbVersionNum` change?

- [ ] **Write the verdict** into the story's results section:
  - **YES**: rekordbox honoured the row. The track loaded, the selector displayed it (or a fallback), and the lighting played. The row survived rekordbox's launch and did not get pruned.
  - **NO**: rekordbox pruned or rewrote the row. The track either errored, snapped back to 1..8, or the row disappeared from the DB.

- [ ] **Update `.opencode/skills/rekordbox-lightingdb-schema/SKILL.md`** with the verdict, dated 2026-08-23.

**Outcome**: Verdict recorded and documented.

---

### Phase 4 — Clean Up

**Goal**: Restore the DB to its original state, regardless of the verdict.

**Checklist**:

- [ ] **Restore the throwaway track's original `macro_pattern_id`**:
  ```bash
  rbxlight experiment ninth-bank --revert --write
  ```
  This should:
  - Restore the throwaway track's `macro_pattern_id` to its original value (recorded in Phase 0)
  - Delete row 28 from `macro_pattern`
  - Delete all 10 `macro_assign` rows for `macro_pattern_id = 28`

- [ ] **Verify by re-read**:
  ```bash
  sqlite3 ~/Library/Application\ Support/Pioneer/rekordbox6/LightingDB/macro.db3 "SELECT COUNT(*) FROM macro_pattern;"
  sqlite3 ~/Library/Application\ Support/Pioneer/rekordbox6/LightingDB/macro.db3 "SELECT COUNT(*) FROM macro_assign;"
  sqlite3 ~/Library/Application\ Support/Pioneer/rekordbox6/LightingDB/user.db3 "SELECT COUNT(*) FROM content;"
  sqlite3 ~/Library/Application\ Support/Pioneer/rekordbox6/LightingDB/user.db3 "SELECT macro_pattern_id FROM content WHERE id = <throwaway_id>;"
  ```
  Confirm: all three counts match the Phase 0 baseline exactly; throwaway track's `macro_pattern_id` is restored.

**Outcome**: DB is restored to its original state; all counts match baseline.

---

## 9. Mandatory Skills to Load

- `rekordbox-data-safety` (MANDATORY — this story writes to live DBs)
- `rekordbox-lightingdb-schema`

---

## 10. In-Scope Doc Corrections

Per the project's standing rule that correcting a stale doc discovered mid-story is in scope, never deferred:

- Record the verdict in `.opencode/skills/rekordbox-lightingdb-schema/SKILL.md`, dated 2026-08-23
- Update `.opencode/BACKLOG.md` to reflect the outcome — either closing the item or promoting the follow-up

---

## 11. Ordering and Standing

This story runs AFTER `FUTURE-bank-takeover-first-pass`. **Reason**: The takeover delivers the same practical outcome — customised lighting on a bank the user actually plays — without betting on unknown rekordbox behaviour, and it does so on a bank that is already labelled and already selectable. The ninth bank only becomes interesting if the takeover proves insufficient. If the takeover lands well, consider closing this item rather than running it.

---

## 12. Results Section (to be filled in during execution)

### Phase 0 Baseline

- Backup command: `[paste restore command here]`
- `macro_pattern` count: ___
- `macro_assign` count: ___
- `content` count: ___
- `MacroVersionNum`: ___
- `DbVersionNum`: ___
- Throwaway track: `content.id = ___`, original `macro_pattern_id = ___`

### Phase 1 Verification

- Row 28 inserted: ✓ / ✗
- 10 `macro_assign` rows inserted: ✓ / ✗
- Throwaway track repointed: ✓ / ✗

### Phase 2 Observation

- Track loads: ✓ / ✗
- Mood/bank selector display: ___________________________________________________________
- Lighting plays: ✓ / ✗
- Touching selector snaps track back to 1..8: ✓ / ✗
- Additional notes: ___________________________________________________________

### Phase 3 Verdict

- Row 28 survived: ✓ / ✗
- 10 `macro_assign` rows survived: ✓ / ✗
- Throwaway track's `macro_pattern_id` survived: ✓ / ✗
- `MacroVersionNum` changed: ✓ / ✗ (new value: ___)
- `DbVersionNum` changed: ✓ / ✗ (new value: ___)

**VERDICT**: rekordbox honours pattern 9: **YES / NO**

### Phase 4 Cleanup

- Throwaway track restored: ✓ / ✗
- Row 28 deleted: ✓ / ✗
- 10 `macro_assign` rows deleted: ✓ / ✗
- All counts match baseline: ✓ / ✗

---

## 13. Open Questions (to be answered by the experiment)

1. **Does rekordbox honour a `pattern = 9` row at all?** The experiment answers this directly.
2. **If yes, is the bank selectable via the UI, or is it unreachable?** Phase 2 observation answers this.
3. **If yes, does rekordbox prune the row on launch, or does it persist?** Phase 3 re-read answers this.
4. **If yes, does touching the mood/bank selector snap the track back to 1..8?** Phase 2 observation answers this.

---

## 14. Documentation Corrections (dated 2026-08-23)

The following stale or incorrect documentation must be corrected in this story:

1. **`.opencode/skills/rekordbox-lightingdb-schema/SKILL.md`:**
   - Add a dated entry (2026-08-23) recording the verdict: "Does rekordbox honour a `pattern = 9` row? **[YES/NO]**"
   - If YES, note that the bank is unlabeled in the UI (no name source exists)
   - If NO, note that rekordbox prunes unknown pattern values on load

2. **`.opencode/BACKLOG.md`:**
   - If YES: promote this to a real feature story (FUTURE-ninth-bank-full-implementation) or close it if the bank takeover proves sufficient
   - If NO: close the item permanently with the dated verdict

---

## 15. Implementation Notes for Whoever Picks This Up

**Mandatory skills to load:**
- `.opencode/skills/rekordbox-data-safety/SKILL.md` (MANDATORY before any DB code)
- `.opencode/skills/rekordbox-lightingdb-schema/SKILL.md`

**Key implementation details:**
- The experiment is fully reversible — Phase 4 cleanup must happen regardless of the verdict
- Use the same `macro_id` values as `macro_pattern_id = 19` (CLUB1 HIGH) for the 10 `macro_assign` rows, since both have 10 phases
- The throwaway track must be a real track the user does not care about — never use a track that is actually played in a set
- All changes must be in a single transaction — if any step fails, the whole thing rolls back
- Dry-run must be the default — `--write` is required for any mutation

**Safety checklist:**
- [ ] Guard that rekordbox is not running before any live-DB write
- [ ] Back up `macro.db3` and `user.db3` before writing
- [ ] Write in a single transaction
- [ ] Re-read the live DB to verify the write succeeded
- [ ] Report the backup path and restore command
- [ ] Never modify `preset=1` factory macros or `master.db3`
- [ ] Tests use fixtures, never touch the live rekordbox directory
