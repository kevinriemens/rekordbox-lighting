---
epic: "TRACKLIGHT"
title: "Stage 2.2 — Bank Takeover (widened scope)"
estimate: M
status: ready
created: 2026-08-26
depends_on: ["E2"]
labels: [macro, bank, takeover, macro_assign, safety]
priority: P1
claimed_by:
claimed_by_date:
---

## 1. User Story

**As a** lighting engineer\
**I want** to replace the complete set of factory macros in one bank×energy slot with a custom-authored macro library\
**So that** I can progressively customize which sequences fire during real performance, starting with the highest-impact slot\

## 2. Business Context & Value

Stage 2 of TRACKLIGHT composes with Stage 1: together they deliver 24 addressable lighting combinations (8 banks × 3 energies). Stage 1 controls **which bank a track gets**; Stage 2 controls **what that bank plays**. Where Stage 1 rebalances the population distribution across banks, Stage 2 authors what happens when a track lands in a given bank×energy pair.

This story widens the takeover scope from a proof-of-concept (one phase of one bank) to one complete bank×energy slot — all 6–11 phases of a given `(pattern, energy)` pair. The mechanism remains unchanged: repoint `macro_assign` rows from factory macros to user macros, preserving `initial_macro_id` as the revert path.

**Why this matters:**
- **Highest-impact single slot**: COOL at HIGH energy fires 5607 phrases—the most heavily populated bank×energy combination in the live library (assuming Stage 1 has not yet redistributed the population).
- **Composable scale**: once this slot is authored, widening to other banks becomes a mechanical repeat of the same workflow.
- **Reversibility**: factory macros are always recoverable via `initial_macro_id`, so experimentation is risk-free.
- **No read-then-reanalyse burden**: `phrase_data` is what fires at playback, and it is populated at analysis time. Only tracks analysed *after* this change are guaranteed to inherit the new macros. Tracks analysed before E2 returns may shadow this change — E2 determines this definitively.

**Live library facts (verified 2026-08-23):**
- COOL bank covers 1888 of 2966 tracks (63.7% of library)
- COOL / HIGH (`macro_pattern_id = 1`) covers 1162 tracks (39.2%)
- **Total `macro_assign` rows across all 27 patterns: 232** (not 27 × 11; phase counts vary by energy and pattern)
- Phase counts by bank and energy (verified direct query against `work/macro.db3`):
  - Patterns 1–6: HIGH=11 phases, MID=10, LOW=6
  - Patterns 7–8 (CLUB banks): HIGH=10 phases, MID=10, LOW=6
  - Pattern 99 (INTERLUDE): 6 phases at every energy
- `phrase_data` shadowing is negligible (36 of 41742 rows differ from their `initial_macro_id`)

## 3. Acceptance Criteria

* [ ] **Scenario 1: Complete bank×energy takeover**
    * Given `user.db3` with `macro_pattern_id = 1` (COOL/HIGH) and its 11 phases currently pointing to factory macros
    * When the user runs the takeover command to repoint all phases of COOL/HIGH to a custom macro library from S2.1 (role-based YAML recipes)
    * Then 11 `macro_assign` rows are written with `initial_macro_id` preserved (the factory macros)

* [ ] **Scenario 2: Phase count is queried, not derived**
    * Given a selected bank×energy pair
    * When the user requests the takeover
    * Then the phase count is read directly from `macro_assign` via `SELECT COUNT(*) FROM macro_assign WHERE macro_pattern_id = ?`, never computed from a formula
    * And the command reports the actual phase count to the user before proceeding

* [ ] **Scenario 3: Dry-run shows all phases before writing**
    * Given a takeover command with no `--write` flag
    * When the command executes
    * Then the complete phase assignment table (phase number, factory macro id, proposed user macro id) is displayed for review, and no changes are written

* [ ] **Scenario 4: Write in a single transaction**
    * Given the takeover command with `--write`
    * When the command executes
    * Then all 6–11 `macro_assign` rows are written in one SQLite transaction; if any row fails, all are rolled back

* [ ] **Scenario 5: Reversibility via revert command**
    * Given a bank×energy takeover has been pushed to live
    * When the user runs `bank revert --bank COOL --energy HIGH`
    * Then all `macro_assign.macro_id` values for that (pattern, energy) are restored to their `initial_macro_id` values in one transaction

* [ ] **Scenario 6: Rekordbox must not be running before push**
    * Given the takeover is about to be pushed to live
    * When the `push --write` command checks for a running rekordbox process
    * Then if rekordbox is running, the command exits with clear instructions to quit first; if not running, the push proceeds with backup and transaction guards

* [ ] **Scenario 7: Backup and restore on live write**
    * Given the takeover is about to be pushed to live
    * When the push executes
    * Then `macro.db3` and `user.db3` are backed up timestamped before any write, and the exact restore command is reported to the user on success

* [ ] **Scenario 8: Already-analysed tracks may not be affected**
    * Given this takeover has been pushed
    * When a track that was analysed before this change plays
    * Then its `phrase_data` rows may continue to fire the old factory macros (because `phrase_data` was populated at analysis time)
    * And this is not a bug — E2 settles whether `phrase_data` shadows `macro_assign` at playback, and Stage 1 assignments are only guaranteed to affect tracks analysed *after* E2 returns

## 4. Technical Constraints

> ⚠️ Describe WHAT is needed, not HOW. No class names, method signatures, DTO shapes, or endpoint paths.
> The implementing agents + architecture skill decide those.

* **Database**: Mutate `macro_assign` rows for one selected `(macro_pattern_id, energy)` pair, repointing `macro_id` to user macros from the S2.1 YAML library while preserving `initial_macro_id` as the factory default. Write in a single transaction. Never write `preset=1` factory macros (ids 1–916, -1, 10000). User macros are `preset=0`, id >= 10001.

* **Phase count discovery**: Read phase counts directly from the database via query, never derive them. Document which patterns have 11, 10, or 6 phases at each energy (see the schema skill for the verified breakdown).

* **Macro source**: The macros that replace the factory ones must come from S2.1 (role-based YAML recipes), not be hand-built in Python. The constraint is that *content should not be code* — the engine that repoints `macro_assign` is code, but what actually plays is YAML, reviewable and versionable separately.

* **Safety**: Guard that rekordbox is not running before any live-DB write. Back up `macro.db3` and `user.db3` before writing. Verify the write by re-reading the live DB. Report the restore command. Never modify `master.db3` (read-only) or `preset=1` factory macros.

* **Reversibility**: `macro_assign.initial_macro_id` is the factory value and must never be written. Revert is `UPDATE macro_assign SET macro_id = initial_macro_id WHERE macro_pattern_id = ? AND energy = ?`. Provide a first-class revert command.

* **Working copy model**: Mutate the working copy on disk. Only `push --write` commits to the live LightingDB. No direct live-DB writes outside of `sync.push()`.

* **Dry-run and CLI**: Default behavior is dry-run (no write). `--write` flag required for mutation. CLI must render the complete phase assignment table for review before the user confirms.

## 5. Design & UI/UX

**Workflow:**

1. User lists current bank assignments: `bank list` (read-only)
   - Output shows all 8 banks × 3 energies, resolved names, track counts
   - Recommends COOL/HIGH as the starting point (if Stage 1 has not yet redistributed its population significantly)

2. User reviews the proposed macro library from S2.1
   - Consults the YAML roles and the macros they define
   - Decides which slot to take over first

3. User previews the takeover: `bank takeover --bank COOL --energy HIGH` (dry-run, no `--write`)
   - Output shows all 11 phases and their proposed macro assignments
   - Reports the exact `push --write` command to commit

4. User commits: `push --write` (after reviewing the dry-run)
   - Checks rekordbox is not running
   - Backs up `macro.db3` and `user.db3`
   - Writes all 11 rows in one transaction
   - Re-reads to verify
   - Reports success and the restore command

5. User manually verifies in performance
   - Tracks analysed after this change are certain to inherit the new macros
   - Tracks analysed before may continue to play the factory macros (answer depends on E2)

6. If needed, user reverts: `bank revert --bank COOL --energy HIGH` (dry-run), then `push --write`

**Error handling:**
- Bank/energy does not exist → clear message
- Rekordbox is running → instructions to quit first
- Write verification fails → report backup path and restore command
- User macro library (S2.1) not yet ready → clear message; build is blocked until S2.1 ships

## 6. Scope & Context

### What changes

- `macro_assign` rows for one selected `(macro_pattern_id, energy)` pair are repointed from factory macros to custom macros from S2.1
- `initial_macro_id` is preserved as the factory default and never written
- The working copy is mutated; `push --write` commits to the live LightingDB

### What does NOT change

- `content.macro_pattern_id` (that is Stage 1 / S1 stories)
- `phrase_data` (unchanged; shadowing behavior is determined by E2)
- `preset=1` factory macros (never written)
- `master.db3` (read-only, never written)
- Tracks analysed before this change (their `phrase_data` was populated at analysis time; whether E2 proves they are affected is unknown until E2 returns)

### Domain concepts

- **Bank**: A named set of 8 factory macro slots (COOL, NATURAL, HOT, SUBTLE, WARM, VIVID, CLUB1, CLUB2), corresponding to `macro_pattern.pattern` values 1–8
- **Energy**: A 3-step axis (HIGH, MID, LOW), corresponding to `macro_pattern.energy` values 1, 2, 3 respectively
- **Phase**: One of 6–11 phases within a (bank, energy) slot, corresponding to `macro_assign.phase` values; **the count is queried, not derived**, and varies by pattern and energy
- **Macro pattern**: A row in `macro_pattern` that defines a (bank, energy) combination and its phases via `macro_assign`
- **Factory macro**: A preset macro (`preset=1`), ids 1–916, -1, 10000; never written by the user
- **User macro**: A custom macro (`preset=0`), id >= 10001; sourced from S2.1 YAML recipes
- **Takeover**: Repointing phases' `macro_id` values from factory macros to user macros, preserving `initial_macro_id` as the revert path

### Known pitfalls

- **Phase count is never uniform and never derivable from energy alone.** Patterns 1–6 and patterns 7–8 have different phase counts at HIGH energy (11 vs 10). Only the database knows the truth; read it. Code that computes the phase count is wrong by definition.
- **Already-analysed tracks are unproven territory.** Their `phrase_data` was populated from `macro_assign` at analysis time. Whether a repoint of `macro_assign` reaches playback on those tracks is unknown until E2 returns. This is not a blocker (Stage 1 assignments only affect newly analysed tracks regardless), but it is a gap: the full scope of the takeover's reach is not yet known.
- rekordbox may prune or rewrite `macro_assign` on launch (unlikely, but unverified — manual verification will reveal this)

### Independence and parallel buildability

- **This story touches `macro.db3` only** — it needs no `master.db`, no library join, and no rules engine
- **It is entirely independent of Stage 1** and can be built in parallel once E2 returns
- **It depends on S2.1** delivering the YAML macro recipes — content authoring is separate from the infrastructure that rewrites `macro_assign`

### Target-selection guidance

COOL at HIGH energy is the highest-impact single slot by a wide margin — 1162 tracks (39.2% of library) sit in that bank×energy pair. **However, note the tension explicitly**: if Stage 1 lands first, that population drops sharply by design, because Stage 1's entire purpose is moving tracks off COOL. So the choice of which slot to take over first should be re-evaluated against the actual distribution *at the time this story is built*, not fixed now.

## 7. Test Impact Analysis

### Existing tests affected by this change

N/A — this is a greenfield feature. No existing tests assert behavior that changes.

### Test modification policy

- [ ] No existing tests should be modified (greenfield)

### Existing files impacted

N/A — no existing behavior is changed, only new functionality added.

---

## Dependencies and Sequencing

- **Depends on E2** (the shadow test, folded into `RIG-calibration-session`) — determines whether already-analysed tracks are affected by a `macro_assign` repoint, and whether Stage 1 and Stage 2 both become 41742-row writes or just ~7500-row writes.

- **Depends on S2.1** (role-based YAML macro recipes) — the source of the custom macros that replace the factory ones.

- **Independent of Stage 1** — can be built in parallel once E2 returns. Stage 1 is sequenced first only because it delivers more audible variety for less work.

---

## Mandatory Skills for Implementation

- `rekordbox-data-safety` — backup, restore, process guard, transaction model
- `rekordbox-lightingdb-schema` — `macro.db3` schema, `macro_assign` structure, phase count facts
- `rekordbox-lighting-architecture` — module layout, repo layer, working copy model, two-tier write pattern
- `physical-rig-profile` — rig context (what the 232 phases actually control)
