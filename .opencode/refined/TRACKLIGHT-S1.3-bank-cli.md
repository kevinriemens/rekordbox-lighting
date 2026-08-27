---
epic: "TRACKLIGHT"
title: "bank plan / apply / revert CLI and safe writes"
estimate: M
status: ready
created: 2026-08-26
depends_on: ["S1.2", "E2"]
labels: [cli, database, safety, dry-run, transaction]
priority: P1
claimed_by:
claimed_by_date:
---

## 1. User Story

**As a** tool user\
**I want** to see a before-and-after distribution of bank assignments, apply assignments safely, and revert them if needed\
**So that** I can author rules and see their effect on the library without risking a corrupt database or losing the ability to undo

## 2. Business Context & Value

The whole point of Stage 1 is to spread the library off the COOL bank, where 39.2% of tracks sit today. S1.2 delivers the assignment logic (pure resolver + YAML rules), but someone needs to drive it over the entire library and commit the results safely. This story provides the commands that dry-run, apply, and revert those assignments.

**The distribution shift is the headline number.** Before: two thirds of the library on COOL. After: spread across all 24 bank×energy combinations. The `bank plan` command must display this shift side by side, impossible to miss.

**E2 blocking gate:** E2 answers whether repointing a track's bank actually reaches playback, or whether `phrase_data` shadows it. This story may be built and dry-run before E2 returns, but must not be applied to the live database until E2 has a verdict. If E2 finds that `phrase_data` shadows the bank assignment, this story's write target changes and the story needs revisiting.

## 3. Acceptance Criteria

* [ ] **Scenario 1: bank plan shows identification status and full distribution before and after**
    * Given the working copy of `user.db3` with current state
    * When running `bank plan` (default, dry-run mode)
    * Then the output displays: (a) a headline showing counts of identified vs. ambiguous vs. unidentifiable tracks (so the operator sees what is addressable before proceeding), (b) a per-track table of what would change (limited to identified tracks only), (c) a summary count of how many identified tracks move and how many are left alone, and (d) a **side-by-side distribution table showing the before and after bank×energy count for all 24 combinations**

* [ ] **Scenario 2: bank plan is the default, --write is required to touch database**
    * Given the user runs any bank command
    * When the user does not specify `--write`
    * Then the command performs a dry run, displays the plan, and makes no changes to disk

* [ ] **Scenario 3: bank apply --write commits the plan exactly, rebuilding phrase_data**
    * Given a dry-run plan was displayed
    * When the user runs `bank apply --write`
    * Then exactly the planned changes are written to `user.db3 content.macro_pattern_id`, each affected track's `phrase_data` rows are rebuilt from the new bank's `macro_assign` and the track's own ANLZ `PSSI` phrase kinds, no other columns or tables are touched, `macro_id == initial_macro_id` on all newly-created phrase rows (mirroring rekordbox's own convention)
    * And the write is preceded by a backup and followed by re-read verification

* [ ] **Scenario 4: bank revert restores the ledger's previous value**
    * Given a previous `bank apply --write` that assigned tracks and recorded the ledger
    * When the user runs `bank revert`
    * Then every assigned track is restored to its previous `macro_pattern_id` value as recorded in the ledger
    * And the restoration is preceded by a backup and followed by re-read verification

* [ ] **Scenario 5: Full revert chain — apply, change rules, apply again, revert twice**
    * Given a track was assigned once with rule A (previous value V0, assigned V1)
    * When rule set changes and the track is assigned again with rule B (previous recorded V1, assigned V2)
    * When reverting the second apply (V2 → V1)
    * When reverting the first apply (V1 → V0)
    * Then the track is restored to its original pre-tool value V0, not the intermediate V1

* [ ] **Scenario 6: bank explain for a single track shows metadata, matching rules, result, and rule ID**
    * Given a song_id that exists in the library
    * When running `bank explain <song_id>`
    * Then the output shows: (a) the track's resolved metadata (genre, BPM, My Tags by category), (b) every rule that matched, in order, (c) which one won, (d) the resulting bank and energy, and (e) the rule ID that decided it

* [ ] **Scenario 7: Unidentifiable and ambiguous tracks are skipped and reported**
    * Given a `content` row that the library reader marked as unidentifiable or ambiguous (multiple candidates)
    * When running `bank plan` or `bank apply`
    * Then the track is skipped, never guessed at or rewritten, and the final report breaks out counts of unresolvable/ambiguous/unidentifiable vs. identified tracks, so the operator sees what is out of reach before approving anything

* [ ] **Scenario 8: pattern=99 (INTERLUDE) is never assigned**
    * Given any rule result or BPM fallback
    * When generating assignments
    * Then no assignment ever chooses `pattern=99`, and if such a result is calculated it is explicitly filtered out with a warning

* [ ] **Scenario 9: Pre-existing orphan content rows are left alone**
    * Given 61 `content` rows pointing at `macro_pattern_id = 0` (pre-existing orphans)
    * When running `bank plan`, `bank apply`, or `bank revert`
    * Then these rows are never modified; they are counted separately in coverage reports

* [ ] **Scenario 10: Safety flow is mandatory: guard → backup → transaction → re-read verify**
    * Given any write command is about to execute
    * When the command reaches the write point
    * Then the sequence is: (1) guard that rekordbox is not running, (2) call `backup_all()`, (3) open a single transaction, (4) verify by re-read after commit
    * And the verify step confirms that every row written matches the planned assignment exactly

* [ ] **Scenario 11: Only safety.py and db.py hold write handles**
    * Given the implementation is complete
    * When inspecting where database writes occur
    * Then all write operations go through the safety and database layers, never directly opened elsewhere in this command

* [ ] **Scenario 12: Dry-run leaves working copy unchanged**
    * Given the working copy file size and modification time before `bank plan`
    * When running `bank plan` (default)
    * Then the working copy file size and modification time are identical afterward

## 4. Technical Constraints

> ⚠️ Describe WHAT is needed, not HOW. No class names, method signatures, DTO shapes, or endpoint paths.
> The implementing agents + architecture skill decide those.

* **Commands**: Three commands are needed: `bank plan` (default, dry-run), `bank apply --write` (commit), `bank revert` (restore from ledger), and `bank explain <song_id>` (debug single track).

* **Distribution display**: The before-and-after distribution must show all 24 bank×energy combinations in a side-by-side table, with counts of tracks in each. This is the value metric of Stage 1 and must be visually impossible to miss.

* **Write target and phrase_data reconstruction**: `user.db3 content.macro_pattern_id` and each affected track's `phrase_data` rows. Rebuild `phrase_data` by: (1) reading the track's ANLZ file via `DjmdContent.AnalysisDataPath`, (2) extracting PSSI phrase kinds, (3) looking up each phrase's predicted phase via the E1e-validated `(kind, k1, k2, k3, b) → phase` table, (4) looking up each phase's `macro_id` from the new bank's `macro_assign`, (5) creating or updating `phrase_data` rows with `macro_id == initial_macro_id` (matching rekordbox's own convention on creation). This mirrors exactly what rekordbox does on a UI bank change. Never write `macro.db3` or `master.db`. The integer pattern value encodes both bank (1–8) and energy (1=HIGH, 2=MID, 3=LOW). The mapping from rule result to integer is consistent with S1.2.

* **Safety flow**: Guard rekordbox-not-running → backup_all() → single transaction → verify by re-read. This sequence is non-negotiable and is the only way writes touch the database.

* **Ledger integration**: Writes to `user.db3` are accompanied by a ledger write in the same logical operation (S1.4 dependency). The ledger records song_id, content.id, assigned bank, assigned energy, rule_id_that_fired, previous_macro_pattern_id, and timestamp. If the ledger write fails, the database write is rolled back.

* **Resolver usage**: Call the S1.2 resolver for every identified track in the library, passing the track metadata from S1.1. The resolver returns (bank, energy, rule_id) or (None, None, None) for "no assignment". Unidentifiable and ambiguous tracks bypass the resolver and are reported separately.

* **Coverage reporting**: Track and report: total content rows, resolvable tracks, unresolvable song_ids, tracks left alone by rules, tracks moved by rules.

* **Bank-name vocabulary**: The on-screen bank names (COOL, NATURAL, HOT, SUBTLE, WARM, VIVID, CLUB1, CLUB2) are provisional, based on factory macro naming conventions. If the `RIG-calibration-session` has captured the exact names rekordbox uses in the UI, use those instead and flag which names are final vs provisional in the output.

## 5. Design & UI/UX

### bank plan

Display:
- Per-track table (limit to first 50 rows or paginate): song_id, old pattern, new pattern, rule that matched, why or "left alone"
- Summary: "X tracks move, Y left alone, Z unresolvable"
- **Distribution before/after**: all 24 combinations, side-by-side counts

### bank apply --write

Same as plan output, then: "Backup created at [path]. Changes committed. Restore with: bank revert"

### bank revert

Show which tracks are being restored, counts of restored vs never-assigned, summary. Confirm before executing.

### bank explain <song_id>

Show:
- Resolved metadata (genre, BPM, My Tags grouped by category)
- Every rule that matched (in order)
- Which rule won and why
- Result bank and energy
- Rule ID
- Current and previous `macro_pattern_id`

## 6. Scope & Context

### What exists today

- S1.1: library reader (done) — returns track metadata
- S1.2: rules resolver (done) — takes metadata, returns (bank, energy, rule_id)
- S1.4: assignment ledger module (done) — records assignments for revert

### Domain rules (non-negotiable)

- **Dry-run is the default.** `--write` is always explicit. This is consistent with every other command in the tool.
- **Only identified tracks may be written.** Unidentifiable and ambiguous tracks are reported and skipped — never guessed at or silently dropped. `bank plan` reports the identification split upfront.
- **phrase_data must be rebuilt, never left stale.** A bank change means rebuilding that track's `phrase_data` rows from the new bank's `macro_assign` and the track's ANLZ `PSSI` phrase kinds, exactly mirroring what rekordbox does on a UI bank change. An external write to `content.macro_pattern_id` alone will leave `phrase_data` stale and playback unchanged.
- **phrase_num → phase is not ordinal.** It must be derived from ANLZ `PSSI` kinds, never assumed from ordinal position. A track keeps its own native phrase count even where the bank defines fewer phases (73.2% of the library has more phrases than their bank has phases).
- **E2 blocks apply.** Until E2 returns a verdict, `bank plan` and `bank explain` can run, but `bank apply --write` must be guarded with an explicit gate. E2 now also validates that reconstructed `phrase_data` is accepted and fires.
- **Unidentifiable and ambiguous tracks are expected loss.** Some lit tracks have no resolvable ID and cannot be matched by fingerprint (zero matches, unreadable ANLZ, or PSSI/phrase-count drift). Report them; do not error.
- **pattern=99 (INTERLUDE) is never assigned.** It is reserved, not user-selectable.
- **The orphan rows pointing at macro_pattern_id=0 are pre-existing and left alone.** They are incidental browser artifacts; do not "fix" them.
- **Single transaction per apply.** If anything fails mid-write (including ledger write), the whole thing rolls back. No partial writes.

### Known edge cases

- A track with no My Tags, no matching genre, and no BPM — resolver returns (None, None, None), track is left alone.
- A rule that matches but is superseded by an earlier rule — the earlier rule wins; this is correct by design.
- Master.db is in use (rekordbox running) — fail before touching anything.
- Ledger write fails — roll back the database write.

## 7. Test Impact Analysis

**Greenfield story** — no existing code is refactored or moved, so no existing tests are affected.

### Test files to be created

- New tests for the CLI commands, covering:
  - Dry-run shows plan without writing
  - Apply with --write commits exactly the planned changes
  - Apply triggers safety flow (backup, transaction, verify)
  - Revert restores previous value
  - Full revert chain (apply, change rules, apply, revert, revert)
  - Explain shows complete track assignment context
  - Distribution display (before/after side-by-side)
  - Unresolvable tracks are skipped and reported
  - pattern=99 is never assigned
  - Orphan rows left alone
  - Ledger integration (assignments recorded for revert)
  - Guard against E2 verdict (gate for apply)

## 8. Mandatory Skills for Implementation

- `rekordbox-data-safety` — safety flow, backups, transaction guards, restore commands
- `rekordbox-lightingdb-schema` — `user.db3` schema, `content.macro_pattern_id`, `phrase_data` shadow mechanism (for E2 gate)
- `physical-rig-profile` — bank names and how they map to the physical rig (for vocabulary)
- `rekordbox-lighting-architecture` — CLI command structure, S1.1/S1.2/S1.4 integration points
