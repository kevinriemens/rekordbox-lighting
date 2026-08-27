# E1e — The Phrase→Phase Mapping

**Status: answered, 2026-08-26.** Bounded, read-only probe, fifth in the E1/E1b/E1c/E1d series.
Extends [E1 — The Library Join](E1-library-join.md), [E1b — The Real Denominator](E1b-real-denominator.md),
[E1c — After Full Analysis](E1c-after-full-analysis.md), and directly resolves the open blocker left by
[E1d — Lighting Mode Row Creation](E1d-lighting-mode-row-creation.md). No new manual experiment, no DJ
session — every number below is mined out of the 41,742 `phrase_data` rows, 2,905 tracks, and 27
`macro_pattern`s already sitting in the working copies (current as of E1d/E1d2; **no refresh was
performed for this probe**, per the task's own instruction). Guard confirmed clear
(`pgrep -x rekordbox` exit 1) before this probe ran.

Script: `src/rbxlight/experiments/e1e_phrase_phase_mapping.py`
(`pip install -e ".[experiments]"`, then
`python -m rbxlight.experiments.e1e_phrase_phase_mapping`).

## Verdict — lead answers, as requested

1. **Is `macro_id → phase` reverse lookup unambiguous? Overwhelmingly yes — 95.98% of rows
   (40,065/41,742).** A further 3.94% (1,643/41,742) are genuinely ambiguous (a macro_id appears at
   >1 phase within the same bank), but this ambiguity is **confined to exactly 4 of the 27
   `macro_pattern_id`s** — the CLUB1/CLUB2 banks at HIGH and MID energy (`macro_pattern_id` 19, 20,
   21, 22), which duplicate 3 macro_ids across adjacent phase pairs. The remaining 0.08% (34/41,742)
   don't resolve at all — and **all 34, with no exception, are pre-existing phrase-level overrides**
   (`macro_id ≠ initial_macro_id`, matching E1c's baseline count of 36 overrides library-wide, two of
   which happen to coincidentally match a valid macro_assign entry). **Critically, this ambiguity is a
   validation-methodology artifact, not a forging blocker** — see Verdict point 4.

2. **Is the phrase→phase mapping a stable per-pattern table? Not as `phrase_num → phase` — that
   hypothesis is refuted outright: 0 of 120 (pattern, track-phrase-count) groups with ≥5 tracks
   produced a single consistent sequence, and even when a track's phrase count exactly equals its
   bank's phase count (210/2,890 non-override tracks), the "obvious" identity mapping
   (`phrase_num == phase`) matched on 0/210 tracks.** But reframed one level deeper, the answer flips
   to a strong yes: **`(kind, k1, k2, k3, b) → phase` — the track's own ANLZ phrase-*kind* plus four
   sub-kind flags, not its ordinal position — IS a stable per-`macro_pattern_id` lookup table.**
   Validated against 13,197 of the 41,742 existing rows (1,011 tracks, spanning 19 of the library's 27
   active `macro_pattern_id`s — 8 combinations, all rarely-used, had zero PSSI-readable representatives
   in the current population and are not directly validated): 165/200 distinct subkind keys (82.5%)
   are 100% consistent, and weighted by row count, **13,111/13,197 rows (99.35%) agree with their
   key's majority phase.**

3. **Does ANLZ `PSSI` carry phrase kinds? Yes, explicitly — a per-entry `kind` field (values 1–10
   observed), plus four boolean sub-flags (`k1`, `k2`, `k3`, `b`) that this probe found disambiguate
   exactly the cases where `kind` alone collapses genuinely distinct phases.** `PSSI`'s own `mood`
   field (High=1/Mid=2/Low=3 — already documented in `pyrekordbox`) matches `macro_pattern.energy` on
   1,101/1,123 checked tracks (98.0%). `PSSI.bank` is a separate byte that is 0 on 1,111/1,123 tracks
   (98.9%) and carries no established meaning here — noted, not pursued further.

4. **Is forging viable? Yes, for the phase/macro_id assignment — with two named, bounded gaps.**
   Given a track's `song_id`, a chosen `macro_pattern_id`, `macro_assign`, and its ANLZ `PSSI` data:
   read each `PSSI` entry's `(kind, k1, k2, k3, b)`, look up its phase in the per-`macro_pattern_id`
   table below, then read that bank's `macro_assign` to get the concrete `macro_id` — a **forward**
   lookup that is always unambiguous by construction (`macro_assign`'s primary key is
   `(macro_pattern_id, phase)`, one row each). The reverse-lookup ambiguity in point 1 only matters for
   *validating against existing data* — it never arises when forging forward. `phrase_num` itself is
   just the entry's 1-based ordinal position in `PSSI.entries` (matches `phrase_data.phrase_num`
   directly on 90.0% of checked tracks — see point 5 below for the other 10%) — it is written into the
   row, but it does not participate in deriving the phase. **What remains underivable or unvalidated:**
   (a) a track with no readable `.EXT`/`PSSI` file (38.7% of currently-lit tracks in this library
   already lack one — see Deliverable 3) cannot be forged by this method, full stop; (b) 8 of 27
   `macro_pattern_id`s have no direct validation evidence in the current population (rare combinations,
   near-zero real tracks) — the table's rows for those are absent, not merely low-confidence; and (c)
   ~10% of tracks show `PSSI.len_entries ≠ phrase_data` row count, meaning a track's on-disk musical
   analysis and its stored lighting programme can drift apart over time — a forged row set is only as
   fresh as the `PSSI` it was built from.

5. **Does PSSI phrase count match `phrase_data` row count? Yes, on 1,011/1,123 checked tracks
   (90.0%).** The 112 mismatches (`content_id` examples: 10, 37, 44, 46, 81, 108, 124, 133, 148, 160,
   185, 196, 248, 276, 281 — full list in script output) were excluded from the subkind table rather
   than force-aligned, since a positional zip across mismatched lengths would silently corrupt the
   mapping. This 10% gap is presented plainly rather than folded into the headline accuracy number.

## Evidence

### Part 1 — is `macro_id → phase` reverse lookup unambiguous?

For every one of the 41,742 `phrase_data` rows, its `macro_id` was looked up against its own track's
`macro_pattern_id`'s full `macro_assign` set (never derived, always read — per the schema skill's
warning that phase counts are not uniform).

| classification | rows | % of 41,742 |
|---|---|---|
| unambiguous (macro_id → exactly 1 phase) | 40,065 | 95.98% |
| ambiguous (macro_id → >1 phase, same bank) | 1,643 | 3.94% |
| not found in `macro_assign` at all | 34 | 0.08% |

Ambiguous rows by bank — **confined to 4 of 27 `macro_pattern_id`s, all CLUB1/CLUB2 at HIGH/MID**:

| `macro_pattern_id` | bank/energy | ambiguous rows |
|---|---|---|
| 19 | CLUB1/HIGH | 847 |
| 20 | CLUB2/HIGH | 423 |
| 21 | CLUB1/MID | 249 |
| 22 | CLUB2/MID | 124 |

These 4 banks' `macro_assign` genuinely duplicate 3 macro_ids across adjacent phase pairs each (e.g.
bank 19: macro_id 201 at phases {1,2}, macro_id 205 at phases {6,7}, macro_id 207 at phases {9,10} —
first observed in E1d). No other bank duplicates a macro_id across phases.

Of the 34 not-found rows, **all 34 are phrase-level overrides** (`macro_id ≠ initial_macro_id`) — zero
are unexplained. Two of the library's 36 known overrides (E1c's baseline) happen to coincidentally
resolve to a value that IS present in their bank's `macro_assign`, which is why 34 rather than 36 show
up as "not found."

**Why this doesn't block forging:** this classification exists to validate the *existing* dataset by
going macro_id → phase (backward). Forging goes phase → macro_id (forward) via `macro_assign`'s own
primary key `(macro_pattern_id, phase)` — a lookup that has exactly one answer by table definition, no
ambiguity possible. The 3.94%/0.08% figures above describe a limitation of checking our work against
history, not a limitation of the forward direction forging actually needs.

### Part 2 — is `phrase_num → phase` a per-(pattern, N) lookup table?

**No.** 2,890 tracks (2,905 with `phrase_data`, minus 15 with a phrase-level override) were resolved to
a `(phrase_num, phase)` sequence and grouped by `(macro_pattern_id, track_phrase_count)`. Of the 120
groups with ≥5 tracks, **0 produced a single consistent sequence** — every group with a meaningful
sample size shows near-total divergence:

| `macro_pattern_id` | N (phrase count) | tracks | distinct sequences | most-common seq's share |
|---|---|---|---|---|
| 1 (COOL/HIGH) | 13 | 146 | 137 | 1.4% |
| 1 | 12 | 134 | 132 | 1.5% |
| 1 | 11 | 125 | 123 | 1.6% |
| 1 | 10 | 122 | 114 | 2.5% |
| 1 | 14 | 88 | 85 | 2.3% |
| 1 | 9 | 87 | 83 | 2.3% |
| 1 | 15 | 80 | 79 | 2.5% |
| 1 | 8 | 66 | 60 | 3.0% |
| 1 | 16 | 63 | 63 | 1.6% |
| 7 (COOL/MID) | 14 | 62 | 60 | 3.2% |
| 7 | 11 | 54 | 53 | 3.7% |
| 7 | 13 | 50 | 50 | 2.0% |
| 1 | 17 | 47 | 45 | 4.3% |
| 1 | 18 | 42 | 42 | 2.4% |
| 7 | 12 | 42 | 42 | 2.4% |

This kills the "simple lookup by ordinal position" hypothesis outright — a `phrase_num` alone carries no
usable phase signal once more than a handful of tracks are compared.

**Even the narrowest, most favourable case — track phrase count exactly equal to bank phase count
(where a naive "identity" mapping would be the simplest possible rule) — fails completely: 0/210
tracks matched `phrase_num == phase`.**

Track phrase-count vs. bank phase-count, across the 2,890 resolved (non-override) tracks:

| relationship | tracks | % of 2,890 |
|---|---|---|
| fewer phrases than bank phases | 566 | 19.6% |
| exactly equal | 210 | 7.3% |
| more phrases than bank phases | 2,114 | 73.2% |

**73.2% of tracks have MORE phrases than their bank has phases** — confirming E1d's single-track
observation was not an edge case but the dominant shape of the whole library. E1d's "boundary shift"
theory (the two endpoint phrases move by exactly the phase-count difference) turns out to be a
coincidental description of one track, not a general rule — Part 3 below explains the actual mechanism.

`phrase_num` itself, it's worth being precise about, is not meaningless — it is simply the analysis
entry's 1-based ordinal position (see Part 3: it matches `PSSI` entry index directly). What's refuted
is that *ordinal position by itself* determines *phase*.

### Part 3 — does ANLZ `PSSI` phrase kind predict phase better than `phrase_num`?

**Yes — decisively.** `PSSI` (the "song structure" tag inside a track's own `ANLZ0000.EXT` analysis
cache — reused via the exact file-resolution mechanism `e1d2_candidate_tracks.py` already
demonstrated: `DjmdContent.AnalysisDataPath` → `.EXT` path → `AnlzFile.parse_file` → scan for the PSSI
tag type) exposes, per phrase entry: `index` (ordinal position, 1-based), `beat` (position in the
track), `kind` (an integer 1–10 observed in this library), and five extra byte fields — `k1`, `k2`,
`k3`, `b` turned out to carry signal; `u1`..`u5` were checked and are always zero across 500 sampled
tracks, confirming they are unused padding, not signal this probe missed.

At the struct level (not per-entry), `PSSI` also carries `mood` (a High=1/Mid=2/Low=3 value —
documented in `pyrekordbox` itself) and `bank` (an integer whose meaning is not established here).

| PSSI field | role found | evidence |
|---|---|---|
| `mood` | matches `macro_pattern.energy` | 1,101/1,123 (98.0%) |
| `bank` | no established meaning | 1,111/1,123 (98.9%) are `bank=0`; the rest scatter across 2,3,4,6,7,8 with no pattern found |
| `kind` + `k1`/`k2`/`k3`/`b` | determines `phase` | see subkind table below |
| `u1`..`u5` | unused padding | always 0 across 500 sampled tracks |
| `len_entries` | phrase count | matches `phrase_data` row count on 1,011/1,123 (90.0%) |

**Worked example that shows why `kind` alone is not enough.** For `macro_pattern_id=1` (COOL/HIGH, an
11-phase bank), raw `kind=2` entries land on 4 different phases depending on `k2`/`b`/`k3`:

| `kind` | `k2` | `b` | `k3` | → phase | n observed | consistency |
|---|---|---|---|---|---|---|
| 2 | 0 | 0 | 0 | 3 | 1,218 | 99.4% |
| 2 | 0 | 0 | 1 | 4 | 222 | 98.6% |
| 2 | 1 | 0 | 0 | 5 | 202 | 99.5% |
| 2 | 1 | 1 | 0 | 5 | 309 | 99.0% |

And `kind=1` (the opening entry, always index 1) splits by `k1` into the bank's first two phases:

| `kind` | `k1` | → phase | n observed | consistency |
|---|---|---|---|---|
| 1 | 0 | 2 | 432 | 100.0% |
| 1 | 1 | 1 | 142 | 100.0% |

**This directly explains E1d's "boundary shift" observation.** E1d's track moved from an 11-phase bank
(COOL/HIGH) to a 10-phase bank (CLUB2/HIGH) and its two boundary phrases shifted down by exactly one
phase each. Looking at `macro_pattern_id=20` (CLUB2/HIGH, 10 phases) for the same `kind=1`:

| `kind` | `k1` | → phase | n observed | consistency |
|---|---|---|---|---|
| 1 | 0 | 1 | 9 | 100.0% |
| 1 | 1 | 1 | 4 | 100.0% |

**Both `k1` variants of `kind=1` collapse to the same phase (1) in the 10-phase bank**, where they were
distinct phases (1 vs 2) in the 11-phase bank. This is the actual mechanism behind E1d's "boundary
shift": it isn't an arbitrary shift by the phase-count delta, it's the same `PSSI`-driven lookup
collapsing distinctions that a smaller bank has no room to keep. The rest of E1d's track (interior
phrases) also lines up: E1d's before/after phase sequences differed only at the two boundaries because
only the boundary `kind`s (1 and 6, intro/outro) have a "collapsible" `k1` variant in this data; interior
kinds like `kind=5`/`kind=3` map the same way regardless of bank phase count.

### The complete subkind → phase table

Read directly from 1,011 tracks (13,197 `phrase_data` rows) — every non-override, PSSI-readable,
row-count-matching track in the current library, covering 19 of the 27 active `macro_pattern_id`s.
`n_obs` is the row count backing each key; entries flagged `INCONSISTENT` list their full phase
distribution — every stray value is a single- or low-digit outlier against a dominant majority, never a
genuine 50/50 split except where `n_obs` itself is 1–2 (noted).

| `macro_pattern_id` | bank/energy | n_phases |
|---|---|---|
| 1 | COOL/HIGH | 11 |
| 2 | NATURAL/HIGH | 11 |
| 3 | HOT/HIGH | 11 |
| 4 | SUBTLE/HIGH | 11 |
| 5 | WARM/HIGH | 11 |
| 6 | VIVID/HIGH | 11 |
| 7 | COOL/MID | 10 |
| 8 | NATURAL/MID | 10 |
| 9 | HOT/MID | 10 |
| 10 | SUBTLE/MID | 10 |
| 11 | WARM/MID | 10 |
| 12 | VIVID/MID | 10 |
| 13 | COOL/LOW | 6 |
| 14 | NATURAL/LOW | 6 |
| 18 | VIVID/LOW | 6 |
| 19 | CLUB1/HIGH | 10 |
| 20 | CLUB2/HIGH | 10 |
| 21 | CLUB1/MID | 10 |
| 22 | CLUB2/MID | 10 |

**`macro_pattern_id=1` (COOL/HIGH, 11 phases)** — the highest-volume bank in the library:

| kind | k1 | k2 | k3 | b | → phase | n_obs | consistency |
|---|---|---|---|---|---|---|---|
| 1 | 0 | 0 | 0 | 0 | 2 | 432 | 100.0% |
| 1 | 1 | 0 | 0 | 0 | 1 | 142 | 100.0% |
| 2 | 0 | 0 | 0 | 0 | 3 | 1,218 | 99.4% |
| 2 | 0 | 0 | 1 | 0 | 4 | 222 | 98.6% |
| 2 | 0 | 1 | 0 | 0 | 5 | 202 | 99.5% |
| 2 | 0 | 1 | 0 | 1 | 5 | 309 | 99.0% |
| 3 | 0 | 0 | 0 | 0 | 8 | 721 | 99.3% |
| 3 | 1 | 0 | 0 | 0 | 8 | 1 | 100.0% |
| 4 | 0 | 0 | 0 | 0 | 6 | 3 | 66.7% (n=3, low sample) |
| 5 | 0 | 0 | 0 | 0 | 7 | 326 | 98.8% |
| 5 | 1 | 0 | 0 | 0 | 6 | 2,400 | 99.8% |
| 6 | 0 | 0 | 0 | 0 | 10 | 192 | 98.4% |
| 6 | 1 | 0 | 0 | 0 | 9 | 336 | 99.7% |
| 8 | 0 | 0 | 0 | 0 | 6 | 1 | 100.0% |
| 9 | 0 | 0 | 0 | 0 | 3 | 7 | 42.9% (n=7, unresolved — see below) |
| 10 | 0 | 0 | 0 | 0 | 9 | 2 | 50.0% (n=2, low sample) |

**`macro_pattern_id=2` (NATURAL/HIGH, 11 phases):**

| kind | k1 | k2 | k3 | b | → phase | n_obs | consistency |
|---|---|---|---|---|---|---|---|
| 1 | 0 | 0 | 0 | 0 | 2 | 12 | 100.0% |
| 1 | 1 | 0 | 0 | 0 | 1 | 2 | 100.0% |
| 2 | 0 | 0 | 0 | 0 | 3 | 37 | 100.0% |
| 2 | 0 | 0 | 1 | 0 | 4 | 7 | 100.0% |
| 2 | 0 | 1 | 0 | 0 | 5 | 7 | 100.0% |
| 2 | 0 | 1 | 0 | 1 | 5 | 3 | 100.0% |
| 3 | 0 | 0 | 0 | 0 | 8 | 30 | 100.0% |
| 5 | 0 | 0 | 0 | 0 | 7 | 7 | 100.0% |
| 5 | 1 | 0 | 0 | 0 | 6 | 75 | 100.0% |
| 6 | 0 | 0 | 0 | 0 | 10 | 4 | 100.0% |
| 6 | 1 | 0 | 0 | 0 | 9 | 9 | 100.0% |

**`macro_pattern_id=3` (HOT/HIGH, 11 phases):**

| kind | k1 | k2 | k3 | b | → phase | n_obs | consistency |
|---|---|---|---|---|---|---|---|
| 1 | 0 | 0 | 0 | 0 | 2 | 11 | 100.0% |
| 1 | 1 | 0 | 0 | 0 | 1 | 7 | 100.0% |
| 2 | 0 | 0 | 0 | 0 | 3 | 31 | 100.0% |
| 2 | 0 | 0 | 1 | 0 | 4 | 7 | 100.0% |
| 2 | 0 | 1 | 0 | 0 | 5 | 7 | 100.0% |
| 2 | 0 | 1 | 0 | 1 | 5 | 9 | 100.0% |
| 3 | 0 | 0 | 0 | 0 | 8 | 19 | 100.0% |
| 5 | 0 | 0 | 0 | 0 | 7 | 4 | 100.0% |
| 5 | 1 | 0 | 0 | 0 | 6 | 83 | 100.0% |
| 6 | 0 | 0 | 0 | 0 | 10 | 5 | 100.0% |
| 6 | 1 | 0 | 0 | 0 | 9 | 12 | 100.0% |

**`macro_pattern_id=4` (SUBTLE/HIGH, 11 phases):**

| kind | k1 | k2 | k3 | b | → phase | n_obs | consistency |
|---|---|---|---|---|---|---|---|
| 1 | 0 | 0 | 0 | 0 | 2 | 3 | 100.0% |
| 1 | 1 | 0 | 0 | 0 | 1 | 8 | 100.0% |
| 2 | 0 | 0 | 0 | 0 | 3 | 28 | 100.0% |
| 2 | 0 | 0 | 1 | 0 | 4 | 1 | 100.0% |
| 2 | 0 | 1 | 0 | 0 | 5 | 6 | 100.0% |
| 2 | 0 | 1 | 0 | 1 | 5 | 5 | 80.0% |
| 3 | 0 | 0 | 0 | 0 | 8 | 8 | 100.0% |
| 5 | 0 | 0 | 0 | 0 | 7 | 7 | 100.0% |
| 5 | 1 | 0 | 0 | 0 | 6 | 52 | 98.1% |
| 6 | 0 | 0 | 0 | 0 | 10 | 2 | 100.0% |
| 6 | 1 | 0 | 0 | 0 | 9 | 9 | 100.0% |

**`macro_pattern_id=5` (WARM/HIGH, 11 phases):**

| kind | k1 | k2 | k3 | b | → phase | n_obs | consistency |
|---|---|---|---|---|---|---|---|
| 1 | 0 | 0 | 0 | 0 | 2 | 11 | 100.0% |
| 1 | 1 | 0 | 0 | 0 | 1 | 10 | 100.0% |
| 2 | 0 | 0 | 0 | 0 | 3 | 40 | 92.5% |
| 2 | 0 | 0 | 1 | 0 | 4 | 7 | 100.0% |
| 2 | 0 | 1 | 0 | 0 | 5 | 8 | 100.0% |
| 2 | 0 | 1 | 0 | 1 | 5 | 16 | 100.0% |
| 3 | 0 | 0 | 0 | 0 | 8 | 18 | 94.4% |
| 5 | 0 | 0 | 0 | 0 | 7 | 10 | 100.0% |
| 5 | 1 | 0 | 0 | 0 | 6 | 101 | 96.0% |
| 6 | 0 | 0 | 0 | 0 | 10 | 6 | 100.0% |
| 6 | 1 | 0 | 0 | 0 | 9 | 14 | 100.0% |

**`macro_pattern_id=6` (VIVID/HIGH, 11 phases):**

| kind | k1 | k2 | k3 | b | → phase | n_obs | consistency |
|---|---|---|---|---|---|---|---|
| 1 | 0 | 0 | 0 | 0 | 2 | 9 | 100.0% |
| 1 | 1 | 0 | 0 | 0 | 1 | 6 | 100.0% |
| 2 | 0 | 0 | 0 | 0 | 3 | 22 | 100.0% |
| 2 | 0 | 0 | 1 | 0 | 4 | 9 | 100.0% |
| 2 | 0 | 1 | 0 | 0 | 5 | 6 | 100.0% |
| 2 | 0 | 1 | 0 | 1 | 5 | 10 | 100.0% |
| 3 | 0 | 0 | 0 | 0 | 8 | 24 | 100.0% |
| 5 | 0 | 0 | 0 | 0 | 7 | 20 | 100.0% |
| 5 | 1 | 0 | 0 | 0 | 6 | 47 | 100.0% |
| 6 | 0 | 0 | 0 | 0 | 10 | 4 | 100.0% |
| 6 | 1 | 0 | 0 | 0 | 9 | 10 | 100.0% |

**`macro_pattern_id=7` (COOL/MID, 10 phases)** — no HIGH-bank-style sub-flag splitting; `kind` alone
carries the phase directly, except `kind=8`/`kind=9` which swap relative to their numeric order:

| kind | → phase | n_obs | consistency |
|---|---|---|---|
| 1 | 1 | 287 | 100.0% |
| 2 | 2 | 483 | 99.2% |
| 3 | 3 | 345 | 99.4% |
| 4 | 4 | 269 | 99.3% |
| 5 | 5 | 188 | 95.2% |
| 6 | 6 | 130 | 99.2% |
| 7 | 7 | 80 | 96.2% |
| 8 | 9 | 296 | 99.7% |
| 9 | 8 | 1,504 | 99.6% |
| 10 | 10 | 162 | 100.0% |

**`macro_pattern_id=8` (NATURAL/MID, 10 phases):**

| kind | → phase | n_obs | consistency |
|---|---|---|---|
| 1 | 1 | 7 | 100.0% |
| 2 | 2 | 8 | 100.0% |
| 3 | 3 | 11 | 100.0% |
| 4 | 4 | 5 | 100.0% |
| 5 | 5 | 10 | 100.0% |
| 6 | 6 | 3 | 100.0% |
| 7 | 7 | 1 | 100.0% |
| 8 | 9 | 3 | 100.0% |
| 9 | 8 | 40 | 100.0% |
| 10 | 10 | 2 | 100.0% |

**`macro_pattern_id=9` (HOT/MID, 10 phases):**

| kind | → phase | n_obs | consistency |
|---|---|---|---|
| 1 | 1 | 8 | 100.0% |
| 2 | 2 | 11 | 100.0% |
| 3 | 3 | 14 | 100.0% |
| 4 | 4 | 19 | 100.0% |
| 5 | 5 | 8 | 100.0% |
| 6 | 6 | 7 | 100.0% |
| 7 | 7 | 3 | 100.0% |
| 8 | 9 | 7 | 100.0% |
| 9 | 8 | 44 | 100.0% |
| 10 | 10 | 7 | 100.0% |

**`macro_pattern_id=10` (SUBTLE/MID, 10 phases):**

| kind | → phase | n_obs | consistency |
|---|---|---|---|
| 1 | 1 | 12 | 100.0% |
| 2 | 2 | 16 | 100.0% |
| 3 | 3 | 21 | 100.0% |
| 4 | 4 | 14 | 92.9% |
| 5 | 5 | 10 | 100.0% |
| 6 | 6 | 8 | 100.0% |
| 7 | 7 | 7 | 100.0% |
| 8 | 9 | 9 | 100.0% |
| 9 | 8 | 50 | 98.0% |
| 10 | 10 | 6 | 83.3% |

**`macro_pattern_id=11` (WARM/MID, 10 phases):**

| kind | → phase | n_obs | consistency |
|---|---|---|---|
| 1 | 1 | 9 | 100.0% |
| 2 | 2 | 11 | 100.0% |
| 3 | 3 | 8 | 100.0% |
| 4 | 4 | 5 | 100.0% |
| 5 | 5 | 5 | 100.0% |
| 8 | 9 | 5 | 100.0% |
| 9 | 8 | 67 | 100.0% |
| 10 | 10 | 6 | 100.0% |

(`kind` 6/7 not observed with a resolvable row for this bank in the current population — absent, not
inconsistent.)

**`macro_pattern_id=12` (VIVID/MID, 10 phases):**

| kind | → phase | n_obs | consistency |
|---|---|---|---|
| 1 | 1 | 16 | 100.0% |
| 2 | 2 | 20 | 100.0% |
| 3 | 3 | 18 | 100.0% |
| 4 | 4 | 18 | 100.0% |
| 5 | 5 | 13 | 100.0% |
| 6 | 6 | 10 | 100.0% |
| 7 | 7 | 8 | 100.0% |
| 8 | 9 | 7 | 100.0% |
| 9 | 8 | 102 | 99.0% |
| 10 | 10 | 9 | 100.0% |

**`macro_pattern_id=13` (COOL/LOW, 6 phases)** — a fundamentally different shape: multiple `kind`
values collapse onto the *same* phase, since a 6-phase bank has far fewer slots than the ~10-kind
vocabulary:

| kind | → phase | n_obs | consistency |
|---|---|---|---|
| 1 | 1 | 41 | 100.0% |
| 2 | 2 | 69 | 100.0% |
| 3 | 2 | 78 | 100.0% |
| 4 | 2 | 45 | 100.0% |
| 5 | 3 | 23 | 100.0% |
| 6 | 3 | 19 | 100.0% |
| 7 | 3 | 8 | 100.0% |
| 8 | 5 | 41 | 100.0% |
| 9 | 4 | 271 | 100.0% |
| 10 | 6 | 15 | 100.0% |

**`macro_pattern_id=14` (NATURAL/LOW, 6 phases)** — same collapse pattern as bank 13, smaller sample:

| kind | → phase | n_obs | consistency |
|---|---|---|---|
| 1 | 1 | 3 | 100.0% |
| 2 | 2 | 4 | 100.0% |
| 3 | 2 | 2 | 100.0% |
| 4 | 2 | 2 | 100.0% |
| 5 | 3 | 2 | 100.0% |
| 6 | 3 | 1 | 100.0% |
| 7 | 3 | 1 | 100.0% |
| 8 | 5 | 3 | 100.0% |
| 9 | 4 | 37 | 100.0% |
| 10 | 6 | 1 | 100.0% |

**`macro_pattern_id=18` (VIVID/LOW, 6 phases)** — very small sample (this bank has only 16 tracks
library-wide, see Deliverable 2 crosstab):

| kind | → phase | n_obs | consistency |
|---|---|---|---|
| 1 | 1 | 1 | 100.0% |
| 2 | 2 | 2 | 100.0% |
| 3 | 2 | 1 | 100.0% |
| 8 | 5 | 1 | 100.0% |
| 9 | 4 | 1 | 100.0% |
| 10 | 6 | 1 | 100.0% |

**`macro_pattern_id=19` (CLUB1/HIGH, 10 phases)** — the CLUB banks combine both behaviours seen above
(sub-flag splitting on `kind=1,2,5,6`, direct mapping elsewhere), and are also where Part 1's ambiguous
macro_ids live — the isolated inconsistent rows below cluster on exactly the phases (3/8, 6/9) that
`macro_assign` duplicates for this bank:

| kind | k1 | k2 | k3 | b | → phase | n_obs | consistency |
|---|---|---|---|---|---|---|---|
| 1 | 0 | 0 | 0 | 0 | 1 | 27 | 100.0% |
| 1 | 1 | 0 | 0 | 0 | 1 | 11 | 100.0% |
| 2 | 0 | 0 | 0 | 0 | 3 | 76 | 100.0% |
| 2 | 0 | 0 | 1 | 0 | 4 | 19 | 100.0% |
| 2 | 0 | 1 | 0 | 0 | 5 | 9 | 100.0% |
| 2 | 0 | 1 | 0 | 1 | 5 | 15 | 100.0% |
| 3 | 0 | 0 | 0 | 0 | 8 | 49 | 95.9% |
| 4 | 0 | 0 | 0 | 0 | 8 | 1 | 100.0% |
| 5 | 0 | 0 | 0 | 0 | 6 | 4 | 75.0% (n=4, low sample) |
| 5 | 1 | 0 | 0 | 0 | 6 | 149 | 100.0% |
| 6 | 0 | 0 | 0 | 0 | 9 | 17 | 94.1% |
| 6 | 1 | 0 | 0 | 0 | 9 | 16 | 100.0% |
| 8 | 0 | 0 | 0 | 0 | 6 | 1 | 100.0% |
| 9 | 0 | 0 | 0 | 0 | 6 | 6 | 83.3% (n=6, low sample) |

**`macro_pattern_id=20` (CLUB2/HIGH, 10 phases)** — this is the exact bank E1d's track moved to:

| kind | k1 | k2 | k3 | b | → phase | n_obs | consistency |
|---|---|---|---|---|---|---|---|
| 1 | 0 | 0 | 0 | 0 | 1 | 9 | 100.0% |
| 1 | 1 | 0 | 0 | 0 | 1 | 4 | 100.0% |
| 2 | 0 | 0 | 0 | 0 | 3 | 48 | 100.0% |
| 2 | 0 | 0 | 1 | 0 | 4 | 10 | 90.0% |
| 2 | 0 | 1 | 0 | 0 | 5 | 6 | 100.0% |
| 2 | 0 | 1 | 0 | 1 | 5 | 5 | 80.0% |
| 3 | 0 | 0 | 0 | 0 | 8 | 31 | 100.0% |
| 5 | 0 | 0 | 0 | 0 | 6 | 11 | 100.0% |
| 5 | 1 | 0 | 0 | 0 | 6 | 33 | 100.0% |
| 6 | 0 | 0 | 0 | 0 | 9 | 5 | 100.0% |
| 6 | 1 | 0 | 0 | 0 | 9 | 7 | 100.0% |

**`macro_pattern_id=21` (CLUB1/MID, 10 phases):**

| kind | → phase | n_obs | consistency |
|---|---|---|---|
| 1 | 1 | 2 | 100.0% |
| 2 | 2 | 3 | 100.0% |
| 3 | 3 | 2 | 100.0% |
| 4 | 4 | 2 | 100.0% |
| 5 | 2 | 8 | 100.0% |
| 6 | 3 | 2 | 100.0% |
| 7 | 4 | 2 | 100.0% |
| 8 | 9 | 3 | 100.0% |
| 9 | 8 | 6 | 100.0% |
| 10 | 10 | 1 | 100.0% |

**`macro_pattern_id=22` (CLUB2/MID, 10 phases):**

| kind | → phase | n_obs | consistency |
|---|---|---|---|
| 1 | 1 | 3 | 100.0% |
| 2 | 2 | 6 | 100.0% |
| 3 | 3 | 5 | 100.0% |
| 4 | 4 | 3 | 100.0% |
| 5 | 2 | 1 | 100.0% |
| 6 | 3 | 1 | 100.0% |
| 7 | 4 | 1 | 100.0% |
| 8 | 9 | 2 | 100.0% |
| 9 | 8 | 10 | 100.0% |
| 10 | 10 | 1 | 100.0% |

**Not directly validated (zero PSSI-readable representatives in the current population's non-override
subset):** `macro_pattern_id` 15 (HOT/LOW), 16 (SUBTLE/LOW), 17 (WARM/LOW), 23 (CLUB1/LOW), 24
(CLUB2/LOW). These 5 banks hold 9, 7, 3, 3, and 2 `content` rows respectively (library-wide — see
Deliverable table below) — small enough that PSSI availability (38.7% library-wide, Deliverable 3) and
the override exclusion plausibly zeroed out the eligible sample entirely, rather than indicating
anything structurally different about these banks. `macro_pattern_id` 25/26/27 (INTERLUDE, all
energies) hold **zero** `content` rows — this pattern is not in use anywhere in the library.

`content.macro_pattern_id` distribution, for reference (sums to 2,966, matching the E1c/E1d baseline
exactly):

| `macro_pattern_id` | tracks | `macro_pattern_id` | tracks |
|---|---|---|---|
| 0 (orphan) | 61 | 13 | 112 |
| 1 | 1,159 | 14 | 23 |
| 2 | 70 | 15 | 9 |
| 3 | 53 | 16 | 7 |
| 4 | 67 | 17 | 3 |
| 5 | 89 | 18 | 16 |
| 6 | 67 | 19 | 110 |
| 7 | 611 | 20 | 58 |
| 8 | 83 | 21 | 35 |
| 9 | 72 | 22 | 13 |
| 10 | 87 | 23 | 3 |
| 11 | 70 | 24 | 2 |
| 12 | 86 | 25–27 | 0 |

## Verdict for forging — the honest gap list

**Given (a) `song_id`, (b) a chosen `macro_pattern_id`, (c) `macro_assign`, and (d) the track's ANLZ
`PSSI` data, a `phrase_data` row set is constructible as follows:**

1. Read the track's `PSSI` tag (via `DjmdContent.AnalysisDataPath`, exactly as `e1d2_candidate_tracks`
   already does). If no `.EXT` file is readable — **stop; this track cannot be forged by this method.**
   38.7% of currently-lit tracks in this library already have this problem (Deliverable 3), so it is
   not a rare edge case to plan around.
2. For each `PSSI` entry, in order: its 1-based position becomes `phrase_num`. Its `(kind, k1, k2, k3,
   b)` looks up a `phase` in the table above, for the chosen `macro_pattern_id`. If that
   `macro_pattern_id` is one of the 5 unvalidated banks (15/16/17/23/24) or a subkind combination never
   observed even in a validated bank, the lookup has no confirmed answer — extrapolating from a
   structurally similar bank is possible but unverified.
3. That `phase` looks up a concrete `macro_id` in `macro_assign` for `(macro_pattern_id, phase)` — a
   single, unambiguous row by the table's own primary key.
4. `initial_macro_id` is set equal to `macro_id` (a freshly-forged row has no override yet, by
   definition — matching every non-override row observed in this dataset).
5. `content_id`/`song_id`/`master_db_id` follow E1's already-established constants; `macro_pattern_id`
   is the caller's choice.

**What remains genuinely underivable, stated plainly rather than glossed over:**

- **A track with no readable ANLZ `PSSI` cannot be forged at all** — there is no fallback signal
  anywhere in `user.db3`/`macro.db3` for phrase kind. This affects a non-trivial fraction of the
  library today (38.7% of tracks with an existing `content` row) and would presumably affect a similar
  or higher fraction of never-lit tracks.
- **5 of 27 banks (15, 16, 17, 23, 24) have zero direct validation** in the current population — small
  natural sample sizes, not a sign of a different mechanism, but not proven either.
- **A forged row set reflects `PSSI` at forge time only.** 10.0% of currently-lit tracks already show
  `PSSI.len_entries ≠ phrase_data` row count, meaning rekordbox's own musical analysis and a track's
  stored lighting programme can drift apart after the fact (most plausibly: the track was re-analysed
  after its lighting programme was written). A forged programme carries the same risk going forward.
- **Whether rekordbox accepts and correctly plays a forged row set is untested by any read-only probe**
  — this remains, as E1d already stated, a question only the physical rig can answer.

## Anonymisation note

No real track titles, artist names, or comment text appear anywhere in this document, its script, or
its console output. Integer IDs (`content.id`, `song_id`, `macro_id`, `macro_pattern_id`), phase/kind
numeric codes, bank/energy names, and row counts are reproduced verbatim — schema/rule vocabulary and
aggregate numbers, not personal data, per the same standard E1/E1b/E1c/E1d applied.

## What to remove later

This is a probe, not shipped code. Nothing permanent depends on it (see
`rekordbox-lighting-architecture`'s `experiments/` contract — the dependency arrow only ever points
inward).

- Delete `src/rbxlight/experiments/e1e_phrase_phase_mapping.py` when this verdict is no longer needed
  for reference. It imports from `e1_library_join.py` and `e1b_real_denominator.py` (both still used by
  other probes — check before deleting either) and reuses the `ANLZ`-reading mechanism
  `e1d2_candidate_tracks.py` first demonstrated, but does not import from `e1d2` directly.
- No new dependencies were added — this probe reuses E1's `experiments` optional-dependency group,
  E1's `work/master.db` copy helper, and the `pyrekordbox`/`construct` packages `e1d2` already added.
- This document and E1/E1b/E1c/E1d's documents are the durable record — keep all five even after the
  code is deleted. **This document is the specification Stage 1 and Stage 3 forging code should be
  built directly against** — the subkind table above is not illustrative, it is the intended lookup
  table.
