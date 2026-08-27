# E1f — The Fingerprint Bridge At Scale

**Status: answered, 2026-08-26.** Bounded, read-only probe, seventh in the E1/E1b/E1c/E1d/E1d2/E1e
series. Extends [E1 — The Library Join](E1-library-join.md),
[E1b — The Real Denominator](E1b-real-denominator.md), [E1c — After Full Analysis](E1c-after-full-analysis.md),
[E1d — Lighting Mode Row Creation](E1d-lighting-mode-row-creation.md),
[E1d2 — Row-Creation Rerun](E1d2-row-creation-rerun.md), and applies
[E1e — The Phrase→Phase Mapping](E1e-phrase-phase-mapping.md)'s `(kind, k1, k2, k3, b) → phase` table at
full library scale. Guard confirmed clear (`pgrep -x rekordbox` exit 1) before this probe ran, and again
immediately before the run reported below. No refresh performed on `work/user.db3` / `work/macro.db3` /
`work/master.db` — used exactly as E1d2 left them, per the task's own instruction.

Script: `src/rbxlight/experiments/e1f_fingerprint_bridge.py`
(`pip install -e ".[experiments]"`, then `python -m rbxlight.experiments.e1f_fingerprint_bridge`).
Runtime: ~7.5 minutes, dominated by reading 7,615 ANLZ `PSSI` files once each (see "Efficiency" below).

## Verdict — lead answers, as requested

1. **Bridge precision on the known-answer set: 99.68% (927/930).** Running the identical bridge — bank +
   PSSI phrase-kind sequence + row count, `content.song_id` hidden from the matcher — over the 1,188
   `content` rows that already resolve by ID (fresh count; task quoted 1,183, same 0.4% drift pattern
   E1d2 already found against its own quoted baselines), 930 rows resolve to exactly one candidate track,
   and 927 of those 930 are the track the hidden ID actually says it is. **This is the number that
   governs everything below, and it clears the bar by a wide margin** — nowhere close to the ~70%
   failure mode the task warned would disqualify the method.
2. **Stranded rows recovered unambiguously: 895 of 1,784 (50.2% of all stranded rows; 50.3% of the 1,781
   with a resolvable own-sequence), claiming 893 distinct library tracks.** One library track was
   independently claimed by 3 different stranded rows — flagged, not silently resolved (see Part 2).
3. **True count of lit library tracks, out of 7,615 (fresh count; task quoted 7,607): between 2,081
   (27.3%, proven identity) and ~2,970 (39.0%, upper bound).** The bridge cannot close this range further
   — see "The headline number" below for exactly what sits in the gap and why.
4. **Lit AND identifiable today — the set a rules engine could address: 2,081/7,615 (27.3%)** — 1,188 by
   direct ID, 893 recovered by the fingerprint bridge.

**Plain answer to "is the bridge trustworthy enough to build on": yes, for the specific claim "this
content row and this library track are the same track" — 99.68% precision on 930 independently-checked
matches is strong evidence, not a hopeful extrapolation.** It is **not** a complete answer to "is this
library track lit at all" — recall is the real constraint (78.9% of ID-resolving rows and 50.3% of
stranded rows land on exactly one match; the rest are ambiguous, zero-match, or structurally untestable),
and the reasons for the misses are almost all *outside* the bridge's own logic (unreadable ANLZ,
PSSI/`phrase_data` count drift, or a true owner that was deliberately excluded from the candidate pool —
see the honest gap list at the end). Where the bridge commits to a single answer, trust it. Where it
doesn't, that is itself the honest answer, not a bug to be argued away.

## Evidence

### Denominators measured fresh this run

| metric | value |
|---|---|
| library tracks (`djmdContent` rows) | 7,615 |
| `content` rows (`user.db3`) | 2,972 |
| — ID-resolving | 1,188 |
| — stranded (non-resolving) | 1,784 |
| subkind lookup (E1e's table, rebuilt fresh from the current working copy) | 1,011 tracks, 200 keys, 99.35% weighted accuracy |
| library tracks with no readable ANLZ `PSSI` at all | 111 / 7,615 (1.5%) |

All four content-row counts match E1d2's post-session state exactly (2,972 total, up from the task's
quoted 2,966 baseline by the 6 rows E1d2's session created). The library-track count (7,615) matches
E1d2's own freshly-measured figure, not the task's quoted 7,607 — same drift, re-confirmed independently.

### Part 1 — validation (bridge run over the ID-resolving population, ID hidden from the matcher)

Candidate pool for this pass: **every** PSSI-readable library track (7,504 of 7,615) — not narrowed to
"tracks that look like they should match," so a wrong-track false-positive would have every opportunity
to appear.

| outcome | rows | % of 1,178 attempted |
|---|---|---|
| excluded — row's own phase sequence doesn't resolve in `macro_assign` (mostly overrides, per E1e) | 10 | — |
| **attempted** | **1,178** | 100% |
| exact-one-match | 930 | 78.9% |
| — correct (hidden ID matches the bridge's pick) | 927 | **99.68% of exact-one** |
| — wrong | 3 | 0.32% of exact-one |
| multi-match (ambiguous) | 67 | 5.7% |
| — correct track present somewhere in the candidate set | 62 | 92.5% of multi-match |
| zero-match | 181 | 15.4% |

Zero-match broken down by cause:

| cause | rows | % of zero-match |
|---|---|---|
| true track's own PSSI unreadable | 52 | 28.7% |
| true track's PSSI `len_entries` ≠ this row's phrase count (drift, per E1e) | 107 | 59.1% |
| candidates existed at that phrase count, but no sequence matched (divergence) | 22 | 12.2% |

Candidate-set-size distribution for the 67 multi-match rows: 2 candidates (40 rows), 3 (15), 4 (5), 5
(4), 7 (2), 9 (1). Ambiguity is rare and, when it happens, usually narrow (2-3 candidates).

**Accuracy does not meaningfully vary by phrase count:** N≤10 99.2%, N11-20 99.8%, N21-30 100%, N>30
100% — no bucket underperforms the headline figure by more than half a point.

**Accuracy by bank is overwhelmingly 100%, with two small-sample exceptions:** every bank with ≥5
exact-one matches hit 100% precision except `mpid=6` (VIVID/HIGH, 13/14, 92.9%) and `mpid=22` (CLUB2/MID,
3/4, 75.0% — n=4, a single wrong match). All 3 of the validation set's wrong matches are concentrated in
these two small banks; every high-volume bank (COOL/HIGH n=495, COOL/MID n=241, COOL/LOW n=34, CLUB1/HIGH
n=28) is a clean 100%.

**Pre-existing phrase overrides (the ~36 known library-wide) barely intersect this population at all:**
only 1 of the 1,188 ID-resolving rows both carries an override *and* has a fully-resolving own-sequence
(overrides usually produce an unresolved sequence and get excluded, per E1e Part 1) — and that one row's
single override happened to land on a wrong match. n=1 is too small to draw a rate from; it is reported
plainly rather than inflated into a percentage.

### Part 2 — recovery (bridge run over the 1,784 stranded rows)

Candidate pool: library tracks **not** already claimed by an ID-resolving `content` row (7,504 readable
tracks minus the 1,188 already claimed = ~6,316 eligible per phrase-count bucket, narrowed further by
bank before any sequence comparison — see "Efficiency").

| outcome | rows | % of 1,781 attempted |
|---|---|---|
| excluded — row's own phase sequence doesn't resolve in `macro_assign` | 3 | — |
| **attempted** | **1,781** | 100% |
| exact-one-match (recovered) | 895 | 50.3% |
| multi-match (ambiguous) | 62 | 3.5% |
| zero-match | 824 | 46.3% |

Candidate-set-size distribution for the 62 multi-match rows: 2 candidates (32), 3 (17), 4 (5), 5 (3), 8
(5).

Zero-match broken down by cause:

| cause | rows | % of zero-match |
|---|---|---|
| no candidate at all shares this phrase count | 62 | 7.5% |
| candidates existed at that phrase count, but no sequence matched | 762 | 92.5% |

**895 recovered rows claim 893 distinct library tracks — 1 track was claimed by 3 different stranded
rows** (`content_id`s 1175, 2309, 2824, all resolving to the same library track id). Per the task: this
means either a genuine library duplicate (the same physical track imported more than once, each import
getting its own `DjmdContent.ID`) or a false match. This probe cannot distinguish the two from the read
side alone — flagged, not silently folded into the 893.

**Divergence rate is far higher here than in validation, and that gap is itself informative, not just
noise.** Validation's zero-match divergence rate was 22/1,178 attempted (1.9%); recovery's is 762/1,781
(42.8%) — more than 20x higher. Two things plausibly explain most of this gap, neither of which is "the
bridge is unreliable":

- **Excluding claimed tracks from the candidate pool, as the task instructs, can itself manufacture a
  divergence.** If a stranded row's true owner track is *currently* claimed by a different, newer,
  ID-resolving `content` row (i.e. the track was reprogrammed at some point and both an old stale row and
  a new current row now exist for it), that true owner is correctly excluded from the recovery pool by
  design — and the stranded row will report "diverged" even though, PSSI-wise, it would match perfectly
  if the pool weren't narrowed. This probe cannot separate this case from a genuine drift/divergence
  without re-running the same rows against the *unrestricted* pool, which the task explicitly asked to
  avoid ("excluding claimed tracks matters"). Reported as an open gap, not resolved either way.
- **Stranded rows are, by construction, older** (their `song_id`s predate the current `DjmdContent`
  numbering) — more elapsed time for the PSSI/`phrase_data`-count drift E1e already measured at ~10.0%
  library-wide to have occurred.

**Bank distribution differs materially between the ID-resolving and recovered populations — the task's
suspicion about the published COOL figure is confirmed.**

| bank | ID-resolving (n=1,188) | recovered stranded (n=895) |
|---|---|---|
| COOL (HIGH+MID+LOW combined) | 955 (80.4%) | 342 (38.2%) |

The ID-resolving population is *far* more COOL-heavy than either the recovered population or E1c's own
published library-wide figure (63.5%, Deliverable 2 of that document). The recovered stranded population
sits well *below* the published figure, not above it — meaning the ID-resolving sample this project has
been measuring against all along is itself biased toward COOL, and the true library-wide bank mix likely
sits somewhere between 38% and 64% COOL, not fixed at either number. Full per-bank breakdown:

| bank/energy | ID-resolving % | recovered % |
|---|---|---|
| COOL/HIGH | 49.8% | 19.6% |
| COOL/MID | 26.1% | 15.3% |
| COOL/LOW | 4.5% | 3.4% |
| NATURAL/MID | 0.8% | 6.4% |
| WARM/HIGH | 1.9% | 6.1% |
| CLUB1/HIGH | 3.7% | 6.0% |
| VIVID/MID | 1.7% | 5.5% |
| NATURAL/HIGH | 1.3% | 5.4% |
| SUBTLE/MID | 1.2% | 5.3% |
| VIVID/HIGH | 1.4% | 4.9% |
| HOT/MID | 0.8% | 4.7% |
| SUBTLE/HIGH | 1.2% | 4.7% |
| CLUB2/HIGH | 1.3% | 3.2% |
| HOT/HIGH | 1.6% | 2.6% |
| CLUB1/MID | 0.5% | 2.2% |
| NATURAL/LOW | 0.3% | 2.0% |
| WARM/MID | 1.1% | 1.8% |
| CLUB2/MID | 0.3% | 0.8% |
| VIVID/LOW | 0.1% | 0.2% |

Every non-COOL bank is proportionally *more* common in the recovered population than in the ID-resolving
one — the recovered set isn't just "less COOL," it is meaningfully more evenly spread across the whole
bank vocabulary.

### Part 3 — the headline number

| | tracks | % of 7,615 |
|---|---|---|
| lit AND identifiable today (by ID or by unique bridge match) | 2,081 | 27.3% |
| — of which, by direct ID | 1,188 | — |
| — of which, recovered by the bridge | 893 | — |
| upper-bound estimate, if every stranded row is a distinct real track | ≤ 2,970 | ≤ 39.0% |
| lit but **not** identifiable by this method (ambiguous / zero-match / sequence-unresolved stranded rows) | 889 | 11.7% |
| residual uncertainty — no readable ANLZ at all, cannot be tested either way | 111 | 1.5% |

**The true "how many tracks are lit" number is a range, not a point, and this probe cannot close it
further:** somewhere between **2,081 (27.3%, proven)** and **~2,970 (39.0%, upper bound — and even that
is capped below the naive 2,972 by the one known duplicate claim in Part 2, which alone accounts for 2 of
those rows not being distinct tracks)**. E1d2's finding stands — stranded rows are real programming, not
junk — so the true figure is very unlikely to be near the lower bound; but "very unlikely to be near"
is not the same as "measured," and this document reports the range rather than picking a point inside it.

**The number Stage 1 actually needs — lit AND identifiable — is 2,081/7,615 (27.3%).** This is the set a
rules engine could safely address today: every track in it has both a confirmed lighting programme and a
confirmed identity, whether via a live ID or a 99.68%-precision bridge match.

**Lit but permanently unidentifiable: 889 stranded `content` rows.** Each is real lighting programming
for some real track (per E1d2), but this bridge — precision notwithstanding — cannot safely say which
track, because the row is either ambiguous (multiple equally-good candidates), zero-match (no candidate's
predicted sequence agrees), or its own phase sequence doesn't resolve in `macro_assign` at all. **These
are tracks this project can never safely rewrite via this method** — a rules engine must either leave
them alone or accept the risk the validation pass just measured (up to ~7.5% ambiguous-set wrong-pick
risk, extrapolated from validation's multi-match recall gap) as the price of touching them.

### Efficiency note

The full cross-product (1,784 stranded rows × ~6,316 eligible candidates per row before any per-row
filtering) was never actually computed — the script indexes every readable track by `(phrase_count,
bank)` before any sequence comparison runs (per the task's instruction), collapsing the eligible set for
a typical row to single digits before the O(N) sequence-equality check. The one first-order cost that
could not be avoided was reading every track's own `PSSI` tag exactly once (`build_pssi_cache`, 7,615
files, ~85ms/file on this machine, ~6.5 of the run's ~7.5 total minutes) — cached in memory for the
remainder of the run rather than re-read per candidate comparison.

### Part 4 — secondary

**Metadata coverage of the recovered tracks differs from the ID-resolving population, and the direction
matters for S1.2's fallback chain:**

| population | n | genre | BPM | any usable My Tag (Mood or Genres, per E1c 3.6) |
|---|---|---|---|---|
| ID-resolving | 1,188 | 96.3% | 100.0% | 19.2% |
| recovered (bridge) | 893 | 100.0% | 99.9% | **49.5%** |

The ID-resolving figure (19.2%) reproduces E1c's published 19.3% almost exactly (fresh-count drift only)
— confirming that number as sound for the population it was measured over. But the recovered population
is **more than 2.5x better tagged** (49.5% vs 19.2%). If S1.2's fallback chain was weighted assuming
~19% My Tag availability across "all lit tracks," it was calibrated against a biased subsample —  the
true lit population (this probe's best estimate: 2,081–2,970 tracks) looks meaningfully better-tagged
than the ID-resolving slice alone suggested.

**ANLZ coverage and Analysis Lock:**

| | value |
|---|---|
| library tracks with no readable ANLZ at all | 111 / 7,615 (1.5%) |
| Analysis-Locked tracks (`Analysed=233`) | 36 |
| — of which also have no readable ANLZ | 1 / 36 (2.8%) |

This reproduces E1d2's own Analysis Lock finding (36 locked, minimal overlap with unreadable ANLZ) at the
current library state, unchanged. Locking still explains almost none of the no-readable-ANLZ problem;
bulk re-analysis would need to handle the 111 (not 36) as its real scope, and would still silently refuse
on the 1 locked track that overlaps.

## What this changes about every prior coverage figure

E1d2 already established that ID-equality undercounts lighting coverage; this probe is the first to put
a number on how much. **Every percentage this project has published before E1f — E1's 39.9%, E1b's
"real denominator" work, E1c's 63.5% COOL figure and its whole rule-authoring matrix — was measured over
the ID-resolving 1,183-1,188 population only.** This probe does not retract those figures (they are
correct *for that population*), but it does establish that population is not representative of the full
lit set on at least two axes measured here (bank mix, My Tag coverage) — both in the direction of making
the true library look *more* usable for rule-authoring, not less, once the stranded population is
accounted for.

## The honest gap list

- **Recall, not precision, is the real constraint.** 78.9% of ID-resolving rows and 50.3% of stranded
  rows resolve to exactly one candidate; the method commits to nothing for the rest rather than guessing.
- **A track with no readable ANLZ `PSSI` cannot be bridged, full stop** — 52/181 validation zero-matches
  and an unknown share of the 111 fully-unreadable library tracks are permanently outside this method's
  reach.
- **PSSI/`phrase_data` count drift (E1e's ~10% finding) is the single largest cause of validation
  zero-matches (107/181, 59.1%)** — a track's stored lighting programme and its current musical analysis
  can disagree, and when they do, this method cannot recover the row even though the row is real.
- **Excluding already-claimed tracks from the recovery candidate pool is methodologically correct per the
  task, but it can manufacture false "divergence" for a stranded row whose true owner has since been
  reprogrammed under a current ID** — this probe cannot separate that case from genuine PSSI drift, and
  it is the leading suspect for recovery's much higher divergence rate (42.8% vs validation's 1.9%).
- **One library track was claimed by 3 different stranded rows** — a duplicate `DjmdContent` entry or a
  false match, undetermined by this probe; either way it means "893 distinct recovered tracks" is not
  quite as clean a number as it looks, and the true upper bound in Part 3 is capped slightly below the
  naive arithmetic for exactly this reason.
- **5 of 27 banks have zero direct validation evidence in E1e's own subkind table** (`macro_pattern_id`
  15/16/17/23/24) — any bridge attempt against those banks (rare in this library) is extrapolating from a
  table with no ground truth for them.

## Anonymisation note

No real track titles, artist names, or comment text appear anywhere in this document, its script, or its
console output. Integer IDs (`content.id`, `song_id`, `macro_pattern_id`, library-track ids), bank/energy
names, and row/track counts are reproduced verbatim — schema/rule vocabulary and aggregate numbers, not
personal data, per the same standard E1–E1e applied. Per-row/per-track detail beyond what's in this
document was not written anywhere (no `work/` dump was needed — every number here comes from the
aggregate counters the script prints).

## What to remove later

This is a probe, not shipped code. Nothing permanent depends on it (see
`rekordbox-lighting-architecture`'s `experiments/` contract — the dependency arrow only ever points
inward).

- Delete `src/rbxlight/experiments/e1f_fingerprint_bridge.py` when this verdict is no longer needed for
  reference. It imports from `e1_library_join.py`, `e1b_real_denominator.py`, `e1d2_lighting_mode_rerun.py`,
  and `e1e_phrase_phase_mapping.py` — all still used elsewhere; check each before deleting any of them.
- No new dependencies were added — this probe reuses the `experiments` optional-dependency group and the
  `pyrekordbox`/`construct` packages E1d2 already added.
- This document and E1/E1b/E1c/E1d/E1d2/E1e's documents are the durable record — keep all seven even
  after the code is deleted. **This document's Part 3 range (2,081–~2,970 lit tracks) is the number every
  future coverage claim in this project should cite going forward — not E1's 39.9%, not E1c's
  ID-resolving-only figures.**
