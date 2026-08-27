---
epic: "TRACKLIGHT"
title: "The assignment ledger — durable record of deliberate choices"
estimate: S
status: ready
created: 2026-08-26
depends_on: ["S1.3"]
labels: [ledger, revert, data-safety, durable-record]
priority: P1
claimed_by:
claimed_by_date:
---

## 1. User Story

**As a** tool user\
**I want** to maintain a durable, human-readable ledger of every bank assignment the tool has made\
**So that** I can revert any assignment by rolling back to the exact previous value, and understand what the tool decided and why

## 2. Business Context & Value

The tool makes deliberate lighting choices by writing bank assignments to `content.macro_pattern_id`. To mark those choices as intentional rather than defaulted, we need a record of what was assigned, which rule fired, and what the value was before. `master.db` is read-only forever, so there is nowhere in rekordbox to record this. The ledger lives in this repository's working data.

S1.3's `bank revert` command depends on the ledger to restore previous values. More subtly, the ledger preserves the **original pre-tool value** even across multiple apply+change-rules+apply cycles. The first recorded `previous_value` for a track is the one that matters for a full revert to factory state; later runs must not overwrite it with an intermediate tool-assigned value. This is the one subtle requirement in the story.

The ledger also answers the original epic question: how is intent recorded? Answer: hand-authored rules (S1.2) express it declaratively, and the ledger records that every assignment came from an explicit rule, not a silent default.

## 3. Acceptance Criteria

* [ ] **Scenario 1: Ledger records every assigned track**
    * Given `bank apply --write` completes successfully
    * When inspecting the ledger file
    * Then every track that was assigned has a ledger entry carrying: song_id, content.id, assigned bank, assigned energy, rule_id_that_fired, previous_macro_pattern_id, and timestamp

* [ ] **Scenario 2: Ledger is human-readable and diffable**
    * Given the ledger file exists
    * When viewing it with a text editor or `git diff`
    * Then the format is structured text (YAML), not binary; each row is readable without parsing tools; changes are visible as line diffs

* [ ] **Scenario 3: Ledger is written in the same logical operation as the database write**
    * Given `bank apply --write` is executing
    * When the database transaction completes
    * Then the ledger write is part of the same operation; if the ledger write fails, the database write is rolled back

* [ ] **Scenario 4: Unresolvable and left-alone tracks are not recorded**
    * Given a track with an unresolvable song_id or a track that matched no rule
    * When running `bank apply --write`
    * Then that track has no ledger entry (only assigned tracks are recorded)

* [ ] **Scenario 5: First previous-value is preserved across multiple applies**
    * Given a track with factory value V0
    * When `bank apply --write` with rule set A assigns it to V1 (ledger records previous=V0)
    * When the rule set changes and `bank apply --write` with rule set B assigns the same track to V2
    * Then the ledger entry for this second apply records previous=V1 (the intermediate value), but reverting that apply goes to V1
    * When reverting the first apply, the track goes to V0 (the original factory value)
    * **In short: each apply records the immediately previous value; multiple reverts restore through the chain correctly**

* [ ] **Scenario 6: bank revert uses ledger to restore**
    * Given one or more `bank apply --write` operations with populated ledger
    * When running `bank revert`
    * Then every assigned track is restored to the value recorded in `previous_macro_pattern_id` for that apply
    * And the revert is followed by re-read verification that the database matches the restored values

* [ ] **Scenario 7: Ledger identifies which rule decided each assignment**
    * Given any assigned track
    * When inspecting the ledger entry
    * Then the `rule_id` field identifies which rule from S1.2 decided it, making every assignment inspectable and auditable

* [ ] **Scenario 8: Ledger format is stable and versioned**
    * Given the ledger file
    * When examining its structure
    * Then it carries a schema version or format marker so future enhancements can detect and migrate older ledgers

## 4. Technical Constraints

> ⚠️ Describe WHAT is needed, not HOW. No class names, method signatures, DTO shapes, or endpoint paths.
> The implementing agents + architecture skill decide those.

* **Storage**: YAML file, human-readable and diffable. One entry per assigned track. Schema: `song_id`, `content_id`, `bank`, `energy`, `rule_id`, `previous_macro_pattern_id`, `timestamp`.

* **Semantics of previous_value**: Records the value **before this apply operation only**. If a track is applied twice, the second apply's `previous_value` is the intermediate tool-assigned value, not the original factory value. However, by following the chain of ledger entries, full revert is possible.

* **Ledger as the source of truth for revert**: The `bank revert` command (S1.3) reads the ledger for the most recent apply and restores from there. Multiple applies can be reverted in sequence by following the ledger chain backward.

* **Atomicity with database write**: The ledger write is part of the same logical operation as the database write. If the ledger write fails, the database transaction is rolled back. If the database write fails, the ledger is not written.

* **Overwrite semantics**: Running `bank apply --write` a second time with the same rule set creates a new ledger entry for each assigned track, with `previous_value` set to the current database value. This allows audit trail of what changed between runs.

* **First-value preservation for full revert**: While each apply records its immediate previous value, the chain of ledger entries enables full revert. To revert to factory state, follow the chain of `previous_value` entries backward to find the original pre-tool value. (This is implicit in the ledger structure; no special "original_value" field is needed.)

* **Ledger is local state**: Because the ledger is not version-controlled and not synced between machines, it is treated as local state. The tool must create the ledger file if it does not exist rather than failing. A missing or incomplete ledger degrades gracefully: `bank revert` can only undo what the local ledger actually records and must state this plainly rather than implying a full revert it cannot deliver.

* **Ledger is gitignored, never committed**: The ledger file is kept out of version control. Although it contains only `song_id`, `content.id`, bank/energy integers, rule identifiers, and timestamps (no track titles or artist names), it is still a fingerprint of a private music library and does not belong in an open-source repository.

## 5. Design & UI/UX

The ledger is not directly user-facing. S1.3's `bank revert` and `bank explain` commands read it for their own purposes. The ledger should be viewable as a plain text file for manual inspection if needed.

## 6. Scope & Context

### What exists today

- S1.3 `bank apply --write` — will call the ledger writer as part of the safety flow
- S1.3 `bank revert` — will read and follow the ledger to restore values
- `safety.py` and `db.py` — the only code paths that hold write handles; the ledger writer is coordinated with them

### Domain rules (non-negotiable)

- **Only assigned tracks are recorded.** Tracks that matched no rule and were left alone do not appear in the ledger.
- **Each apply is a separate ledger entry per track.** Running apply twice creates two entries (one per run), with `previous_value` being the value immediately before that apply.
- **The ledger is the only source of truth for revert.** `bank revert` does not try to infer previous values; it reads what the ledger recorded.
- **Atomicity is mandatory.** A ledger entry is written if and only if the corresponding database write succeeded in the same transaction.

### Known edge cases

- A track with previous_value = NULL (never had a value in the database before the tool touched it) — record it explicitly so revert can handle it (sets the value back to NULL or leaves it unset).
- Multiple reverts in sequence — each revert reads the ledger for the most recent apply and restores from there; following multiple reverts leaves the database in a previous, pre-apply state.
- Ledger corruption or missing entries — this is an operational issue; the error message must clearly state that the ledger is corrupted and that the user should restore from backup.

### Build requirement

- The ledger file path must be added to `.gitignore` so it is never accidentally committed to the repository.

## 7. Test Impact Analysis

**Greenfield story** — no existing code is refactored or moved, so no existing tests are affected.

### Test files to be created

- New tests for the ledger module, covering:
  - Ledger write in same logical operation as database write
  - Atomicity: ledger write fails → database rolls back
  - Ledger format is YAML and human-readable
  - Schema version or marker is present
  - Song_id and rule_id are recorded correctly
  - Previous values are accurate (immediate previous, not original)
  - Only assigned tracks appear in ledger
  - Multiple applies create multiple entries for the same track
  - Revert reads and follows the ledger correctly
  - Revert by following ledger chain restores to original factory value
  - Unresolvable and left-alone tracks do not appear in ledger

### Test fixture

- A test ledger file with sample entries, readable as YAML, used to test revert logic

## 8. Mandatory Skills for Implementation

- `rekordbox-data-safety` — atomicity with database writes, rollback semantics
- `rekordbox-lightingdb-schema` — `content.id`, `macro_pattern_id`, timestamp conventions
- `rekordbox-lighting-architecture` — module placement, integration with S1.3 commands


