# E1b — The Real Denominator

**Status: answered, 2026-08-26.** Bounded, read-only probe, extends [E1 — The Library Join](E1-library-join.md). No production code shipped — see "What to remove later" at the end.

Script: `src/rbxlight/experiments/e1b_real_denominator.py` (`pip install -e ".[experiments]"`, then `python -m rbxlight.experiments.e1b_real_denominator`).

Every number below comes from one live run against the same working copy E1 used: `work/user.db3` (2966 `content` rows), `work/macro.db3`, and the read-only `work/master.db` copy of the live rekordbox main library (7615 `DjmdContent` rows, confirmed unchanged since E1). No database was written. Track titles, artist names, and playlist names are never quoted here — see the anonymisation note at the end.

## Verdict

**The dead-weight hypothesis is REFUTED, on both halves of it, and the real number is worse than the headline.**

E1's 39.9% join rate was the wrong number to be reassured by. The tracks that actually matter — the DJ's own playlists — join at **only 22.6%** (742/3282), *below* the library-wide headline, not above it. Play history joins slightly better at 30.4% (623/2051) but is still far short of "mostly fine." Of the 1183 `content` rows that currently resolve, only 784 (66.3%) are even in a playlist or history at all — a third of the "good" set is neither played nor organised. **Coverage is not an artifact of counting stale rows; it is a real gap, and it is worse over the denominator that matters than over the denominator E1 measured.**

The other half of the hypothesis — that the 1783 stale rows are dead migration debris — is also refuted. 96.6% of them (1722/1783) carry `phrase_data` rows, and on a per-row basis they carry *more* phrase-level programming than the currently-joining rows (14.64 rows/content vs 13.22), not less. Only 61 of 1783 (3.4%) are true orphans pointing at `macro_pattern_id = 0` — the same 61 already known from E1's schema notes. The other 1722 have a real, valid bank assignment and a *more* diverse bank distribution than the joining set (COOL 53.8% vs 81.2%), which if anything suggests these were tracks the DJ paid *more* manual attention to, not less. These are not dead rows; they are fully-realized past lighting work stranded by an ID remap, most likely a library re-import.

**The good news is on the signal side, not the join side.** Measured over the correct denominator (3282 playlist tracks, whether or not they currently have a `content` row), genre/BPM/key are effectively fully populated (99.0% / 99.9% / 100%), and My Tag coverage is *better* than E1's joined-only numbers suggested (39.5% any-tag vs E1's 23.2%, 26.0% carry a Mood tag, 13.5% a Situation tag). The taxonomy itself is not the problem — the join is. And the join problem is arithmetically fixable: analysing the 2540 playlist tracks that have never been sent through lighting analysis at all would take overall content-table coverage from 39.9% to **67.6%**, and playlist coverage from 22.6% to 100% (§ Q3) — no data cleanup, no ID-matching heuristic, just running analysis on tracks that have never been analysed.

**Design implication:** build the fallback path anyway — it's needed for a majority of playlist tracks today (77.4% have no `content` row) — but stop treating 39.9%/1183-tracks as "the population that matters." The real target set is the 3282 playlist tracks (or the 3417 played-or-playlisted union), most of which are metadata-rich (genre/BPM/key near-universal, My Tag present on ~40%) and simply haven't been run through rekordbox's own lighting analysis yet. That is a DJ-side action (run analysis), not a data-quality problem this tool needs to work around with more join logic.

On the taxonomy-consistency questions this probe also measured: My Tag conflicts are common enough that a rules engine must resolve them, not assume they're rare — 44.6% of Mood-tagged tracks carry more than one Mood tag (§ Q5). rekordbox's own energy verdict tracks Situation only weakly and inconsistently — it's directionally right at the extremes (`Afbouw` → LOW, `Big Impact`/`Laatste kwartier` → HIGH-skewed) but flat or even backwards in the middle (`Begin`, intuitively lower-energy, actually sits *below* the library's HIGH-heavy baseline the least of any tag; `Background` doesn't separate from baseline at all) — while BPM separates Situation more cleanly and monotonically (§ Q6, Q7). **Recommendation: keep energy as originally planned, but do not lean on it for `Begin`/`Background` specifically, and treat BPM as the stronger secondary signal for tracks with no My Tag, not energy.**

## Evidence

### Q1 — the real denominator

Two new tables exist and have real data: `djmdPlaylist`/`djmdSongPlaylist` (184 playlists, 16018 song-playlist rows) and `djmdHistory`/`djmdSongHistory` (333 history sessions, 6734 song-history rows). All 16018 `djmdSongPlaylist` rows belong to ordinary playlists (`djmdPlaylist.Attribute = 0`) — smart playlists (`Attribute = 4`, 13 of them) compute membership dynamically and have no materialized song rows; folders (`Attribute = 1`, 26 of them) hold no songs directly. No filtering was needed; this was verified, not assumed.

| set | distinct tracks | joined (have a `content` row) | no `content` row at all |
|---|---|---|---|
| playlist tracks | 3282 | **742 (22.6%)** | 2540 (77.4%) |
| history-played tracks | 2051 | **623 (30.4%)** | 1428 (69.6%) |
| union (playlist or history) | 3417 | **784 (22.9%)** | 2633 (77.1%) |

Both figures are *below* E1's 39.9% headline, not above it. Every playlist/history `ContentID` resolves to a currently-live `DjmdContent.ID` (0 stale references in either direction — checked directly), so "joined" here has no ambiguity: it means the track has ever been run through rekordbox's own lighting analysis at all.

Cross-checking against E1's 1183 currently-joining `content` rows in the other direction: only **784 of 1183 (66.3%)** of the tracks that DO join are in a playlist or history at all. **399 of 1183 (33.7%) are neither** — analysed at some point, but not organised or played since. If "the tracks that matter" means playlist/history tracks, a third of the currently-"good" set doesn't qualify.

### Q2 — are the stale rows dead weight? No.

| | stale (1783) | joined (1183) |
|---|---|---|
| have >=1 `phrase_data` row | 1722 (96.6%) | 1183 (100%) |
| total `phrase_data` rows | 26101 | 15641 |
| avg `phrase_data` rows / content row | **14.64** | 13.22 |
| `macro_pattern_id = 0` (true orphan) | 61 (3.4%) | 0 |
| real (non-zero) `macro_pattern_id` | 1722 (96.6%) | 1183 (100%) |

The 61 known orphans (E1/schema-skill's pre-existing `macro_pattern_id = 0` rows) account for only 3.4% of the stale set. The remaining 1722 stale rows have a real bank assignment and *more* per-track phrase programming on average than the rows that currently resolve. This is the opposite of what "dead weight from a migration" would look like — dead rows would carry little or no programming; these carry the most.

**Bank distribution, stale (excl. the 61 orphans) vs joined:**

| bank | stale (n=1722) | joined (n=1183) |
|---|---|---|
| COOL | 927 (53.8%) | 961 (81.2%) |
| NATURAL | 148 (8.6%) | 27 (2.3%) |
| SUBTLE | 133 (7.7%) | 28 (2.4%) |
| VIVID | 131 (7.6%) | 37 (3.1%) |
| WARM | 127 (7.4%) | 35 (3.0%) |
| HOT | 105 (6.1%) | 27 (2.3%) |
| CLUB1 | 98 (5.7%) | 49 (4.1%) |
| CLUB2 | 53 (3.1%) | 19 (1.6%) |

The stale set is *more* diverse (COOL only 53.8%, vs 81.2% in the joined set, which E1 already flagged as dominated by what looks like a default value). If anything this points to the stale tracks having received more deliberate, varied hand-assignment historically — the opposite of neglect.

**`content.id` bands (match rate, 10 roughly-equal bands of ~296-302 rows):**

| band (`content.id`) | n | matched | rate |
|---|---|---|---|
| 1..296 | 296 | 148 | 50.0% |
| 297..592 | 296 | 45 | 15.2% |
| 593..888 | 296 | 134 | 45.3% |
| 889..1184 | 296 | 143 | 48.3% |
| 1185..1480 | 296 | 157 | 53.0% |
| 1481..1776 | 296 | 150 | 50.7% |
| 1777..2072 | 296 | 4 | **1.4%** |
| 2073..2368 | 296 | 37 | 12.5% |
| 2369..2664 | 296 | 182 | **61.5%** |
| 2665..2966 | 302 | 183 | 60.6% |

Match rate is bursty, not a smooth decay — consistent with distinct historical batches written under different ID regimes (same read as E1's), not gradual staleness. `content` carries no timestamp column, so the batches can't be dated directly.

**Plainly: nothing distinguishes a stale row from a joining one except the id failing to resolve.** Phrase-data presence, phrase-data volume, and bank diversity all point the *other* direction from "dead" — the stale rows look like real, at-the-time-complete lighting work, orphaned by an ID remap (most plausibly a library re-import), not neglected or abandoned tracks.

### Q3 — coverage forecast (the arithmetic)

Today: 1183/2966 (39.9%) of all `content` rows join; 742/3282 (22.6%) of playlist tracks have any `content` row. 2540 playlist tracks have never been sent through lighting analysis at all.

If the DJ ran lighting analysis on those 2540 tracks, each would get a fresh `content` row keyed to its current (live) `DjmdContent.ID` — E1 already established that new rows join cleanly because they're written against the current ID scheme, not the legacy one.

```
content rows today:            2966  (1183 joined, 1783 stale)
+ new rows (never-lit playlist tracks): 2540  (all would join — current IDs)
= content rows after:          5506
= joined rows after:            3723   (1183 + 2540)
= overall join rate after:      3723 / 5506 = 67.6%   (was 39.9%)
= playlist join rate after:     3282 / 3282 = 100%    (was 22.6%)
```

No cleanup of the 1783 stale rows is needed to get from 39.9% to 67.6% — clearing the playlist backlog alone nearly doubles overall coverage. The stale rows stay exactly as unrecoverable as E1 found them (no ID-remap table exists — `uuidIDMap` is empty in this library); they just stop being the main story.

### Q4 — signal coverage over playlist tracks (n=3282)

Measured over playlist tracks regardless of whether they currently have a `content` row — this is "over how many of the tracks that matter," per the framing of this probe.

| signal | populated |
|---|---|
| genre | 99.0% |
| BPM | 99.9% |
| key | 100.0% |
| any My Tag | 39.5% |
| **Mood** tag (>=1) | **26.0%** |
| **Situation** tag (>=1) | **13.5%** |

All of these are higher than E1's joined-only figures (genre 96.3%, My Tag 23.2% over the 1183). The taxonomy is not thin over the real target set — it's thinner than genre/BPM/key, as expected for a hand-applied tag system, but far from unusable, and it's *better* than the number E1 could see through the join.

### Q5 — My Tag co-occurrence within Mood

Measured library-wide (any track carrying >=1 Mood tag, n=950) — this is a taxonomy-consistency question, independent of the join/coverage question, so the full library gives the most reliable read. (84 exact duplicate `(ContentID, MyTagID)` rows exist in `djmdSongMyTag` — a data quirk, de-duplicated via set semantics before counting; without dedup, self-pairs like `(90s, 90s)` appear spuriously.)

**Tag-count-per-track distribution, tracks with >=1 Mood tag:**

| Mood tags on track | tracks | % |
|---|---|---|
| 1 | 526 | 55.4% |
| 2 | 244 | 25.7% |
| 3 | 114 | 12.0% |
| 4 | 43 | 4.5% |
| 5 | 16 | 1.7% |
| 6 | 6 | 0.6% |
| 7 | 1 | 0.1% |

**44.6% of Mood-tagged tracks carry more than one Mood tag.** A rules engine resolving Mood -> bank cannot assume single-tag input; conflict resolution is the common case, not the edge case.

**Top 15 co-occurring Mood pairs:**

| pair | count | pair | count |
|---|---|---|---|
| Fout / Party | 88 | Fout / Guilty Pleasure | 28 |
| 00s / Party | 56 | 80s / Party | 23 |
| Meezingers / Party | 51 | Feel Good / Fout | 22 |
| 90s / Fout | 49 | 00s / Fout | 22 |
| Fout / Meezingers | 45 | Meezingers / Smartlappen | 20 |
| Feel Good / Party | 43 | 90s / Feel Good | 19 |
| 90s / Party | 35 | | |
| 80s / Fout | 30 | | |
| 00s / Feel Good | 30 | | |

`Fout` ("guilty-pleasure/cheesy") pairs with almost everything in the top 15 (`Party`, `90s`, `Meezingers`, `Guilty Pleasure`, `80s`, `Feel Good`, `00s`) — it reads as a modifier tag layered onto an era or vibe tag, not a standalone mood competing for the same bank. `Feel Good` vs `Hard` (the conflict named in the task) does not appear in the top 15 at all, i.e. it's not a common real-world collision in this library — but the general phenomenon of multi-tag Mood tracks is common (44.6%), so the conflict strategy still needs to exist; it just won't be exercised most often by that specific pair.

### Q6 — Situation tag vs rekordbox's current energy verdict

Measured over the 1183 currently-joined tracks (energy requires `content.macro_pattern_id`, which only exists for joined rows). Baseline energy distribution across all 1183 joined tracks: **HIGH 62.6%, MID 32.6%, LOW 4.8%** — the comparison point for whether a Situation tag shifts energy away from that default.

| Situation tag | n | HIGH | MID | LOW |
|---|---|---|---|---|
| Peaktime | 122 | 69.7% | 28.7% | 1.6% |
| Buildup | 73 | 63.0% | 35.6% | 1.4% |
| Begin | 34 | 55.9% | 44.1% | 0.0% |
| Big Impact | 28 | 71.4% | 28.6% | 0.0% |
| Background | 19 | 57.9% | 42.1% | 0.0% |
| Laatste kwartier | 16 | 81.2% | 12.5% | 6.2% |
| Afterparty | 8 | 100.0% | 0.0% | 0.0% |
| Afbouw | 3 | 0.0% | 0.0% | 100.0% |
| Kids | 2 | 0.0% | 100.0% | 0.0% |
| Dansje | 1 | 100.0% | 0.0% | 0.0% |

Reading this against the 62.6/32.6/4.8 baseline, not in isolation:

- **Clean, directionally correct signal at the extremes**: `Afbouw` (cooldown) is 100% LOW against a 4.8% baseline — the strongest result in the dataset, though n=3 is tiny. `Laatste kwartier` (peak/closer) and `Big Impact` skew HIGH more than baseline (81.2% and 71.4% vs 62.6%).
- **Flat or backwards in the middle.** `Begin` (start of a set — intuitively lower energy) is 55.9% HIGH, *below* baseline but only barely, and MID at 44.1% is the highest MID share of any tag — a weak, not absent, signal in the expected direction. `Background` sits close to baseline (57.9% vs 62.6%) rather than skewing LOW as the label would suggest — no real separation from the library-wide default.
- `Buildup` (63.0% HIGH) is statistically indistinguishable from baseline (62.6%) — rekordbox's energy carries no information about "buildup" specifically, in this data.

**Verdict on the story's proposed design ("keep energy, only override the bank"): partially defensible.** The extremes (`Afbouw`, `Big Impact`, `Laatste kwartier`) show real, if not huge, separation from the HIGH-heavy default and are safe to trust. `Begin`, `Background`, and `Buildup` show no meaningful separation from baseline — for those tags specifically, rekordbox's energy is not a validated signal, it is closer to the same default value E1 already found dominating bank assignment. Sample sizes for the weaker tags (n=19–34) are not large enough to rule out a real but smaller effect, but they are not large enough to claim one either.

### Q7 — BPM per Situation tag

Same 1183-joined-track scope as Q6, same Situation tags, tracks with populated BPM.

| Situation tag | n | median | IQR | min | max |
|---|---|---|---|---|---|
| Peaktime | 122 | 128.0 | [123.0, 145.0] | 92.0 | 175.0 |
| Buildup | 73 | 126.0 | [109.8, 130.0] | 94.0 | 172.0 |
| Begin | 34 | 125.0 | [114.5, 128.0] | 91.0 | 162.0 |
| Big Impact | 28 | 137.4 | [125.0, 151.2] | 92.5 | 170.0 |
| Background | 19 | **120.0** | [109.5, 126.0] | 95.0 | 132.0 |
| Laatste kwartier | 16 | **152.7** | [138.0, 162.5] | 109.7 | 200.0 |
| Afterparty | 8 | 145.0 | [136.8, 163.5] | 116.0 | 174.0 |
| Afbouw | 3 | 109.7 | [107.5, 118.8] | 105.4 | 128.0 |
| Kids | 2 | 150.0 | [145.0, 155.0] | 140.0 | 160.0 |
| Dansje | 1 | 124.0 | (n<2) | 124.0 | 124.0 |

**BPM separates Situation more cleanly than energy does, and in the direction the labels suggest**: `Background` has the lowest median (120.0) among tags with n>=10, `Afbouw` the lowest overall (109.7, n=3), and the progression `Background` (120) < `Begin`/`Buildup` (~125-126) < `Peaktime` (128) < `Big Impact` (137.4) < `Afterparty`/`Laatste kwartier` (145/152.7) tracks a plausible set arc from warm-up through peak to closer. This is exactly the ordering `Begin` and `Background` failed to show in energy (Q6) — **BPM is the better proxy for those two tags specifically**, and a reasonable general-purpose fallback for tracks that carry BPM but no My Tag.

## Anonymisation note

No real track titles, artist names, or playlist/history names appear anywhere in this document or in the probe script's default output. Genre names, colour display names, and My Tag names (including category names `Mood`/`Situation`/`Genres`/`Components`) are reproduced verbatim per the task's requirements — they are rule vocabulary, not personal data. Counts only, as in E1.

## What to remove later

This is a probe, not shipped code. Nothing permanent depends on it (see `rekordbox-lighting-architecture`'s `experiments/` contract).

- Delete `src/rbxlight/experiments/e1b_real_denominator.py` when this verdict is no longer needed for reference. `e1_library_join.py` may still be needed by other probes; check before deleting it too (per E1's own removal note).
- No new dependencies were added — this probe reuses E1's `experiments` optional-dependency group (`pyrekordbox`, `sqlcipher3-wheels`) and E1's `work/master.db` copy.
- `work/master.db` is already gitignored and shared with E1; no change to its lifecycle.
- This document and E1's document are the durable record — keep both even after the code is deleted.
