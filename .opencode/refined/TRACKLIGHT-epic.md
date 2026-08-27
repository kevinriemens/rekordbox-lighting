# TRACKLIGHT — from stock banks to per-track light shows

## Goal

Rekordbox assigns a lighting bank to every track at analysis time, but the mechanism has never been documented — the observed result is overwhelmingly COOL. Replace that single default with a deliberate, hand-authored mapping from what a track *is* to how it should be lit (identity-first: 27.3% of the library is addressable today), then progressively deepen what "how it should be lit" is allowed to mean. See **"The north star: a light show per track"** in `docs/PROJECT-FOUNDATION.md`.

## Why this epic exists

The rig looks the same all night because rekordbox's bank selector defaults almost everything to COOL, and that default is baked into tracks across the library. No external documentation exists for how or why rekordbox chooses a bank at analysis time — it remains a measured correlation, never a proven rule. Track identity by ID alone is unreliable (only 1,188 of 2,972 content rows resolve; 1,783 carry legacy IDs), but the fingerprint bridge (ANLZ `PSSI` phrase-kind matching) recovers 893 of the 1,784 stranded rows unambiguously at 99.68% precision, bringing the addressable set to 2,081 of 7,615 library tracks (27.3%). This epic replaces the accident of COOL defaults with intention: authoring the bank assignment from the track's own metadata (genre, My Tag categories, measured BPM) for every identifiable track, then progressively replacing the factory macros that play with custom content and finally with per-track phrase data.

## The three levers

Bank assignment, macro content, and phrase-level override compose into an addressable space: 8 banks × 3 energies = 24 combinations, each with a playable sequence of 6–11 macros depending on the bank and energy.

| Lever | Column | What it controls | Stage |
|---|---|---|---|
| Which bank a track gets | `user.db3 content.macro_pattern_id` | the track's mood bank + energy | Stage 1 |
| What a bank plays | `macro.db3 macro_assign.macro_id` | the macro fired for a given bank/energy/phase | Stage 2 |
| What a single phrase plays | `user.db3 phrase_data.macro_id` | per-track, per-phrase override — shadows the other two at playback | Stage 3 |

## Story index

| ID | Story | Size | Depends on | Status |
|---|---|---|---|---|
| **E1** | The library join | S | — | **DONE**, verdict in `docs/experiments/E1-library-join.md` |
| **E1b** | The real denominator | S | E1 | **DONE**, verdict in `docs/experiments/E1b-real-denominator.md` |
| **P0** | Analyse the full library in rekordbox | S | — | **DONE** (manual, no code; the DJ ran lighting analysis across all ~7500 tracks) |
| **E1c** | Re-measure after full analysis + build the rule-authoring matrix | S | P0 | **DONE**, verdict in `docs/experiments/E1c-after-full-analysis.md` |
| **E1d** | Row-creation semantics and metadata validation | S | — | **DONE**, verdict in `docs/experiments/E1d-lighting-mode-row-creation.md` |
| **E1d2** | Row-creation rerun + methodological correction | S | E1d | **DONE**, verdict in `docs/experiments/E1d2-row-creation-rerun.md` |
| **E1e** | Phrase-to-phase mapping (PSSI phrase kinds are the key, not ordinal position) | S | E1d2 | **DONE**, verdict in `docs/experiments/E1e-phrase-phase-mapping.md` |
| **E1f** | Fingerprint bridge at scale (2,081 of 7,615 addressable, 99.68% precision) | S | E1e | **DONE**, verdict in `docs/experiments/E1f-fingerprint-bridge.md` |
| **E2** | The shadow test (phrase_data reconstruction and rig validation) | S | rig access | **BLOCKED on rig session**. Folded into `RIG-calibration-session`. |
| **E3** | The direct phrase-write test | S | rig access | **BLOCKED on rig session**. Folded into `RIG-calibration-session`. |
| **S1.1** | Library reader module (dual-path identity: ID + fingerprint) | M | E1f | Ready to refine |
| **S1.2** | YAML assignment rules + resolver (operates on identified tracks only) | M | S1.1, E1f | Ready to refine |
| **S1.3** | `bank plan` / `bank apply` / `bank revert` CLI (phrase_data rebuild included) | M | S1.2, E2 | Ready to refine |
| **S1.4** | The assignment ledger | S | S1.3 | Ready to refine |
| **S2.1** | Role-based YAML macro recipes | M | — | Ready to refine |
| **S2.2** | Bank takeover (widened) | M | E2 | Refined |
| **S2.3** | FullArcAI venue | L | `RIG-calibration-session` | Refined |
| **S3.1** | Per-track shows | L | E3, S2.1 | Placeholder — not refinable |

## Ordering notes

See [`TRACKLIGHT-EXECUTION-ORDER.md`](./TRACKLIGHT-EXECUTION-ORDER.md) for the complete running order. In brief: book the rig session first (it gates E2 and E3), build S1.1 in parallel while waiting, then follow the stage-by-stage sequence. E2's verdict determines whether Stage 1 writes 7,500 rows or 41,742, so do not build S1.3's apply logic ahead of that result.

## Deliberate assignment: how intent is recorded

This answers the original question of how to mark a bank choice as intentional rather than defaulted:

- **Not via track colour** — killed by E1 (1.5% usage, slots occupied by an unrelated workflow).
- **Not via a new My Tag category** — rejected in refinement: the My Tag panel is a live filtering surface used mid-set, and lighting metadata would tax the thing the DJ actually uses.
- **Via hand-authored YAML rules in this repo.** Intent is expressed as an explicit mapping — for example, `Genres: Urban` + `Mood: Geile muziek` ⇒ `HOT` — rather than as a per-track label. Every assignment is therefore deliberate by construction, and the rule that produced it is inspectable.
- **Plus a repo-side ledger** (S1.4) recording, per track: what was assigned, which rule fired, what the value was before, and when. Because `master.db` is read-only forever, this record cannot live in rekordbox. The ledger also gives free revert, mirroring the `initial_macro_id` pattern the LightingDB schema already uses for exactly this purpose.

## Open questions

- **E2** — does a bank repoint reach playback, or does `phrase_data` shadow it? *(blocking, rig)*
- **E3** — can `phrase_data.macro_id` be written directly and made to fire? *(gates Stage 3, rig)*
- How does rekordbox choose a bank at analysis time? Still entirely undocumented. Observed result is overwhelmingly COOL, but the mechanism has never been instrumented — it remains a correlation, not a proven rule.
- Does rekordbox ever re-sync `macro_assign` into `phrase_data` on re-analysis? Unestablished. Bears directly on whether Stage 1 assignments survive a future re-analysis.
