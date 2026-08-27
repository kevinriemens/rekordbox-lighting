# E1c — After Full Analysis

**Status: answered, 2026-08-26.** Bounded, read-only probe, third in the E1/E1b series. Extends
[E1 — The Library Join](E1-library-join.md) and [E1b — The Real Denominator](E1b-real-denominator.md).
No production code shipped — see "What to remove later" at the end.

Script: `src/rbxlight/experiments/e1c_after_full_analysis.py`
(`pip install -e ".[experiments]"`, then `python -m rbxlight.experiments.e1c_after_full_analysis`).

All three working copies were refreshed immediately before this probe ran: `work/user.db3` and
`work/macro.db3` via `rbxlight pull` (the existing `sync.py` pull path — no adaptation needed), and
`work/master.db` via `ensure_master_db_copy(refresh=True)` (E1's copy helper — no adaptation needed
either). `rekordbox` was confirmed not running, both before the refresh and again immediately before
it, via `pgrep -x rekordbox` (exit 1 both times). No database was written. Track titles and artist
names are never quoted here — see the anonymisation note at the end.

## Verdict

**The headline finding is not a number — it's that the premise didn't happen.** The task briefing
for this probe, and `docs/PROJECT-FOUNDATION.md` line 39, both describe E1c as "re-measurement after
the DJ ran/analysed full lighting analysis on the whole collection." **That did not reach the
`content` table.** Every figure this probe can compare against E1/E1b's baseline is either byte-for-byte
identical or within the noise of two individually-edited tracks:

- `content` row count: **2966** (baseline 2966, unchanged).
- Forward join rate: **1183/2966 (39.9%)** (baseline 1183/2966 = 39.9%, unchanged) — same count, same
  percentage, same breakdown of the 1783 unmatched rows (1183 below the live minimum ID, 600 within
  range but missing, 0 above — all three identical to E1's baseline).
- A 10-row spot check of `content.id -> song_id` at the exact rows E1 sampled (`id` 1, 330, 660, 989,
  1319, 1648, 1978, 2307, 2637, 2966) returned the **exact same `song_id` values** E1 recorded. This
  is the `content` table's actual row content, not just its aggregate counts, confirmed unchanged.
- `phrase_data`: **41742** rows, **2905** distinct `content_id` (both unchanged from E1's baseline).
- `macro_pattern_id = 0` orphans: **61** (unchanged). Phrase-level overrides: **36** (unchanged).
  Phrase-level NULLs: **0** (unchanged).
- Duplicate `song_id` values across `content` rows: **0** — re-analysis did not write duplicate or
  replacement rows; it did not write to this table at all.
- Library-wide bank distribution: COOL **63.5%** (baseline 63.7%) and energy **HIGH 57.6% / MID 36.4%
  / LOW 6.0%** (baseline, quoted exactly) — the energy split matches the pre-analysis baseline to the
  decimal point.

**What DID change, and it's small.** `work/master.db` and `work/user.db3` both carry file modification
timestamps from the same morning this probe ran (today), so *something* touched them — but not the
lighting-analysis pipeline this probe was commissioned to re-measure. Two concrete, real changes were
found by cross-referencing this run's tables against E1's published per-genre bank breakdown:

1. `DjmdContent` shrank from **7615 to 7607** (library tracks) — 8 fewer tracks in the main library.
2. **Exactly 2 of the 1183 currently-joined tracks changed bank assignment** since E1/E1b: one `Pop`
   track moved `COOL -> CLUB1`, one `Eclectic` track moved `COOL -> HOT` (found by diffing this run's
   top-10-genre x bank crosstab, cell by cell, against E1's published table — every other cell in
   every other genre row is unchanged). My Tag counts over the same 1183 tracks also drifted upward by
   a handful of tracks per tag (e.g. `Meezingers` 57 -> 60, `Party` 52 -> 55) — consistent with the DJ
   doing ordinary My Tag housekeeping in rekordbox's main library view, which lives in `master.db` and
   is completely independent of the lighting `content`/`phrase_data` tables in `user.db3`.

This reads as normal day-to-day DJ activity (a couple of manual re-tags, a couple of library
maintenance removals) between E1b (2026-08-25) and this run (2026-08-26), not a bulk lighting-analysis
pass. **See "Contradiction with PROJECT-FOUNDATION.md" below** — this is flagged loudly per this
probe's own instructions, because Stage 1 of the project plan is written assuming this analysis run
happened and changed the join population.

**Because nothing changed, Deliverable 2's "did bulk analysis skew harder toward COOL" question has no
data to answer it with.** `content` carries no timestamp column (per E1), and the only available
"old vs new" proxy — `content.id` ordering — is moot here anyway: there are zero new rows by *any*
definition, so there is nothing to split the distribution by. This is stated as a hard limitation, not
worked around.

**The rule-authoring matrix (Deliverable 3) is real and complete, but it describes the same 1183
tracks E1/E1b already characterized — not a larger, freshly-analysed population.** The **denominator
for every table below is 1183** (the tracks that currently join `content.song_id` -> `DjmdContent.ID`
in this working copy) — stated once here, used consistently throughout. Because the join population
is unchanged, most figures below refine and extend E1/E1b's numbers rather than superseding them; where
a number moved (the 2-track bank shift, the small My Tag increases above), it is called out inline.

**Top 10 `Genres` x `Mood` pairs, the single most useful table for authoring S1.2's rules** (full top 40
in the evidence section):

| Genres tag | Mood tag | tracks |
|---|---|---|
| Apres Ski | Fout | 14 |
| Apres Ski | Party | 14 |
| Eclectic | Party | 13 |
| Urban | Geile muziek | 11 |
| Retro | Hard | 11 |
| Eclectic | Feel Good | 10 |
| Eclectic | Geile muziek | 10 |
| Apres Ski | Meezingers | 9 |
| Pop | Meezingers | 9 |
| Eclectic | Fout | 8 |

**Design implication for S1.2:** author rules from this table top-down — it is literally ranked by how
many tracks each rule would catch. But also read Deliverable 3.6 first: only **13.2%** of the 1183
joined tracks (122 + 34 = 156) have a Genres My Tag at all, so a Genres-keyed rule set alone reaches a
small minority of tracks. **77.0%** have neither a Mood nor a Genres My Tag but do have an ID3 genre —
that's where the ID3-genre x Mood table and the ID3 fallback do the real work.

## Evidence

### Refresh procedure (Step 0)

`pgrep -x rekordbox` returned exit 1 (not running) both before and immediately before the refresh —
re-verified per this probe's own instructions, not assumed from the earlier verification. Both existing
refresh paths worked without modification:

- `rbxlight pull` (CLI, wraps `sync.pull`) refreshed `work/macro.db3` and `work/user.db3` from
  `~/Library/Application Support/Pioneer/rekordbox6/LightingDB/`. New pull-state sha256 hashes differ
  from the pre-probe state for both files (confirming a real refresh happened, not a no-op), and
  `work/.pull-state.json` was rewritten with a fresh timestamp.
- `ensure_master_db_copy(refresh=True)` (E1's helper, reused unchanged) re-copied
  `~/Library/Pioneer/rekordbox/master.db` to `work/master.db`. File size is unchanged (84869120 bytes)
  but the source file's own mtime is today, confirming rekordbox had touched it since E1/E1b's last
  copy.

No adaptation was needed for either path.

### Deliverable 1 — coverage at the new scale

| metric | E1c (now) | E1/E1b baseline |
|---|---|---|
| `content` rows | 2966 | 2966 |
| `phrase_data` rows | 41742 | 41742 |
| `phrase_data` distinct `content_id` | 2905 | 2905 |
| `DjmdContent` rows (library tracks) | **7607** | 7615 |
| forward join (`content.song_id` -> live ID) | 1183/2966 (39.9%) | 1183/2966 (39.9%) |
| backward join (library tracks with a `content` row) | 1183/7607 (15.6%) | 1183/7615 (15.5%) |
| unmatched, below live min ID | 1183 | 1183 |
| unmatched, within range but missing | 600 | 600 |
| unmatched, above live max ID | 0 | 0 |
| duplicate `song_id` values across `content` rows | **0** | (not previously measured — new) |
| `macro_pattern_id = 0` orphans | 61 | 61 |
| `phrase_data` overrides (`macro_id <> initial_macro_id`) | 36 | 36 |
| `phrase_data` NULL `macro_id` | 0 | 0 |
| `uuidIDMap` rows (master.db) | 0 | 0 (empty) |

Every row-count and join-breakdown figure is identical to E1's baseline. The one figure that moved —
`DjmdContent` row count, 7615 -> 7607 — reflects 8 fewer tracks in the main library, not a change to
the lighting-analysis join.

**Did re-analysis create duplicate or replacement rows? No — because nothing was written to `content`
at all.** Zero `song_id` values repeat across `content` rows (no duplicates). A direct spot-check of
E1's original 10-row `content.id` sample (`1, 330, 660, 989, 1319, 1648, 1978, 2307, 2637, 2966`)
returned identical `song_id` values this run. Of the 7 of those 10 that were stale (unmatched) at E1's
baseline, **0 now resolve** — none were rewritten to a current ID. `uuidIDMap` (rekordbox's own
id-remap table) remains empty in `master.db`, exactly as E1 found it — there is still no mechanism, and
no evidence, of any remap having occurred.

**Verdict on the "replaced vs added-alongside" question the task posed: neither happened, because
re-analysis never wrote to this table.** The 1783 stale rows are exactly as unrecoverable, and exactly
as untouched, as E1b already found them.

### Deliverable 2 — quantify the COOL default

Bank distribution, all 2966 `content` rows (61 rows with `macro_pattern_id = 0` have no bank and are
reported separately, not folded into a "NONE" bank column below):

| bank | HIGH | MID | LOW | total | % of 2966 |
|---|---|---|---|---|---|
| COOL | 1160 | 611 | 112 | 1883 | 63.5% |
| NATURAL | 70 | 83 | 23 | 176 | 5.9% |
| VIVID | 67 | 86 | 16 | 169 | 5.7% |
| WARM | 89 | 70 | 3 | 162 | 5.5% |
| SUBTLE | 67 | 87 | 7 | 161 | 5.4% |
| CLUB1 | 110 | 35 | 3 | 148 | 5.0% |
| HOT | 53 | 72 | 9 | 134 | 4.5% |
| CLUB2 | 57 | 13 | 2 | 72 | 2.4% |
| INTERLUDE | 0 | 0 | 0 | 0 | 0.0% |
| *(no bank, `mpid=0`)* | — | — | — | 61 | 2.1% |

Energy split, excluding the 61 no-bank orphans (denominator 2905): **HIGH 1673 (57.6%), MID 1057
(36.4%), LOW 175 (6.0%)** — matches the quoted pre-analysis baseline (57.6% / 36.4% / 6.0%) exactly,
to the decimal.

**Compare against baseline:** COOL 63.5% now vs 63.7% baseline. Effectively flat — the ~0.2-point
difference is fully explained by the two individually-reassigned tracks found in Deliverable 3.10
below (both moved off COOL), not by any bulk shift. **INTERLUDE (`pattern = 99`) is never directly
assigned to a `content` row** — 0 tracks, both now and presumably at baseline (E1/E1b did not report
it separately, consistent with zero).

**Splitting the distribution by newly-analysed vs pre-existing rows: not possible, and not just for the
reason the task anticipated.** The task allowed for `content.id` ordering as "weak evidence, not proof."
That caveat turns out to be moot here: **there is no newly-analysed population at all** — Deliverable 1
established the `content` table is byte-for-byte unchanged since E1/E1b. Zero new rows exist under any
definition, so there is nothing to split the COOL distribution by, weak or otherwise. **This question
cannot be answered from this working copy; answering it requires the DJ to actually run lighting
analysis on previously-unanalysed tracks and this probe to be re-run afterward.**

Phrase-level overrides: 36 (baseline 36, unchanged). NULLs: 0 (baseline 0, unchanged).

### Deliverable 3 — the rule-authoring matrix

All tables in this section are measured over **the 1183 `content` rows that currently join
`song_id` -> a live `DjmdContent.ID`** — stated once, used throughout this section.

#### 3.1 — full `Genres` My Tag counts

| tag | tracks | % | tag | tracks | % |
|---|---|---|---|---|---|
| Eclectic | 33 | 2.8% | Moombah/Reggaeton | 10 | 0.8% |
| Pop | 30 | 2.5% | Hardere stijlen | 10 | 0.8% |
| Urban | 24 | 2.0% | Oldies | 9 | 0.8% |
| House | 22 | 1.9% | Latin | 6 | 0.5% |
| Apres Ski | 19 | 1.6% | Club & (Vocal) Trance | 6 | 0.5% |
| Carnaval | 17 | 1.4% | Ballermann | 4 | 0.3% |
| Retro | 17 | 1.4% | Soul/Disco | 4 | 0.3% |
| Dance | 16 | 1.4% | Schlager/Fox | 1 | 0.1% |
| Rock | 11 | 0.9% | Classic Rock | 1 | 0.1% |

All 18 `Genres` My Tags defined in the taxonomy appear at least once among the 1183 joined tracks —
none are entirely unused at this population.

`Genres` tags per track (n=1183):

| tag count | tracks | % |
|---|---|---|
| 0 | 1027 | 86.8% |
| 1 | 92 | 7.8% |
| 2 | 49 | 4.1% |
| 3+ | 15 | 1.3% |

**86.8% of joined tracks carry no `Genres` My Tag at all** — this category is thin on its own; it is a
refinement layer on top of ID3 genre, not a primary signal (see 3.6).

#### 3.2 — full `Mood` My Tag counts

| tag | tracks | % | tag | tracks | % |
|---|---|---|---|---|---|
| Meezingers | 60 | 5.1% | Ladies | 18 | 1.5% |
| Party | 55 | 4.6% | Oldskool | 17 | 1.4% |
| Fout | 49 | 4.1% | Stampen | 16 | 1.4% |
| Feel Good | 28 | 2.4% | Dance Classics | 14 | 1.2% |
| Guilty Pleasure | 27 | 2.3% | 00s | 13 | 1.1% |
| Hard | 23 | 1.9% | 80s | 11 | 0.9% |
| Geile muziek | 21 | 1.8% | House | 11 | 0.9% |
| Club vibe | 21 | 1.8% | 90s | 7 | 0.6% |
| Smartlappen | 19 | 1.6% | | | |

All 17 `Mood` My Tags appear at least once. Note `House` appears as both a `Genres` tag (22 tracks) and
a separately-defined `Mood` tag (11 tracks) — same word, two different categories, both valid; do not
collapse them when authoring rules.

`Mood` tags per track (n=1183):

| tag count | tracks | % |
|---|---|---|
| 0 | 989 | 83.6% |
| 1 | 85 | 7.2% |
| 2 | 48 | 4.1% |
| 3+ | 61 | 5.2% |

**83.6% of joined tracks carry no `Mood` My Tag at all** — thinner than `Genres`'s single-tag rate but
with a longer multi-tag tail (5.2% carry 3 or more Mood tags vs `Genres`'s 1.3%) — consistent with
E1b's finding (measured library-wide) that Mood-tagged tracks commonly carry more than one tag.

#### 3.3 — top 40 `Genres` x `Mood` co-occurrence pairs

The rule-priority list. Each row is a candidate rule (`Genres = X and Mood = Y => bank`), ranked by how
many of the 1183 joined tracks it would catch.

| Genres tag | Mood tag | tracks |
|---|---|---|
| Apres Ski | Party | 14 |
| Apres Ski | Fout | 14 |
| Eclectic | Party | 13 |
| Urban | Geile muziek | 11 |
| Retro | Hard | 11 |
| Eclectic | Feel Good | 10 |
| Eclectic | Geile muziek | 10 |
| Apres Ski | Meezingers | 9 |
| Pop | Meezingers | 9 |
| Eclectic | Fout | 8 |
| Retro | Stampen | 8 |
| Pop | Fout | 8 |
| Eclectic | Ladies | 7 |
| Urban | 00s | 7 |
| Rock | Meezingers | 7 |
| Carnaval | Party | 7 |
| Hardere stijlen | Hard | 7 |
| Retro | Oldskool | 7 |
| Retro | Club vibe | 7 |
| Oldies | Fout | 6 |
| Moombah/Reggaeton | Geile muziek | 6 |
| Dance | Club vibe | 6 |
| Pop | Feel Good | 6 |
| Urban | Ladies | 6 |
| Carnaval | Fout | 6 |
| House | House | 6 |
| Hardere stijlen | Stampen | 6 |
| Oldies | Meezingers | 6 |
| Oldies | Guilty Pleasure | 6 |
| Oldies | Party | 5 |
| House | Party | 5 |
| Moombah/Reggaeton | Ladies | 5 |
| Pop | Guilty Pleasure | 5 |
| Dance | Meezingers | 5 |
| Apres Ski | Stampen | 5 |
| House | Meezingers | 5 |
| House | Club vibe | 5 |
| Latin | Party | 4 |
| Soul/Disco | Dance Classics | 4 |
| Hardere stijlen | Club vibe | 4 |

Full 40 pairs, not truncated. Note `House` appears both as a rule LHS from `Genres` (`House / House`,
6 tracks — the Genres tag and the Mood tag happen to share the same name) and combined with other
Moods (`House / Party`, `House / Meezingers`, `House / Club vibe`) — treat these as four separate,
valid rules, not duplicates.

#### 3.4 — top 40 ID3-genre x `Mood` pairs

ID3 genre has far higher coverage (99.0% at E1b's playlist-track denominator; see 3.6 for this probe's
own coverage buckets) than `Genres` My Tag, so this table catches more tracks per rule even though the
genre vocabulary is coarser.

| ID3 genre | Mood tag | tracks |
|---|---|---|
| Levenspop | Smartlappen | 13 |
| Eclectic | Feel Good | 11 |
| Pop | Meezingers | 11 |
| Pop | Guilty Pleasure | 10 |
| Techno | Hard | 9 |
| Levenspop | Meezingers | 9 |
| Eclectic | Party | 8 |
| Jump | Hard | 8 |
| Urban | Geile muziek | 7 |
| Pop | Party | 7 |
| Pop | Fout | 7 |
| Levenspop | Fout | 6 |
| Eclectic | Fout | 6 |
| Eclectic | Geile muziek | 6 |
| Urban | 00s | 6 |
| Apres-Ski | Party | 6 |
| Levenspop | Party | 5 |
| Eclectic | Ladies | 5 |
| Rock | Meezingers | 5 |
| Dance | Meezingers | 5 |
| Pop | 80s | 5 |
| Pop | Feel Good | 5 |
| Urban | Oldskool | 5 |
| Jump | Stampen | 5 |
| Apres-Ski | Meezingers | 5 |
| Techno | Club vibe | 5 |
| Deep-House | Feel Good | 4 |
| Rock | Fout | 4 |
| EDM | House | 4 |
| EDM | Party | 4 |
| Eclectic | Guilty Pleasure | 4 |
| Techno | Stampen | 4 |
| Apres-Ski | Fout | 4 |
| Techno | Meezingers | 4 |
| Deep-House | House | 4 |
| Jump | Club vibe | 4 |
| Deep-House | Dance Classics | 3 |
| Pop | Geile muziek | 3 |
| Pop | 00s | 3 |
| Disco | Dance Classics | 3 |

Full 40 pairs, not truncated.

#### 3.5 — agreement between the two genre sources

Measured over tracks with both an ID3 genre and >=1 `Genres` My Tag:

| | count | % of 156 |
|---|---|---|
| both present | 156 | — |
| agree (normalized string match) | 69 | 44.2% |
| disagree | 87 | 55.8% |

"Agree" means the ID3 genre string, normalized (lowercased, hyphens/slashes collapsed to spaces),
matches one of the track's `Genres` My Tag names under the same normalization (e.g. `Apres-Ski` ==
`Apres Ski`). **They disagree more often than they agree.** Top disagreement pairs:

| ID3 genre | Genres My Tag | tracks |
|---|---|---|
| Jump | Retro | 10 |
| Deep-House | House | 8 |
| Carnaval Mix | Carnaval | 5 |
| Levenspop | Apres Ski | 4 |
| Carnaval Kölle | Carnaval | 3 |
| Disco | Soul/Disco | 3 |
| Deep-House | Eclectic | 3 |
| Techno | Apres Ski | 3 |
| Techno | Hardere stijlen | 3 |
| Techno | Club & (Vocal) Trance | 3 |
| Pop | Oldies | 3 |
| Club | House | 3 |
| Pop | Urban | 2 |
| Moombahton | Eclectic | 2 |
| Moombahton | Moombah/Reggaeton | 2 |

**Reading the disagreements:** most are not contradictions so much as different granularity —
`Carnaval Mix`/`Carnaval Kölle` (ID3, specific sub-genres of the DJ's Carnaval catalogue) vs the single
umbrella `Carnaval` My Tag; `Deep-House` (ID3) vs the broader `House` or `Eclectic` My Tags; `Jump`
(ID3, a Dutch/Belgian dance sub-genre) vs `Retro` (My Tag). **Design implication for S1.2's fallback
chain:** when both sources are present and disagree, prefer the `Genres` My Tag — it is the DJ's own
hand-applied label and, per this table, is consistently the *more specific* of the two, not a
contradiction to be resolved by picking whichever wins a vote. ID3 genre is the right default when
`Genres` My Tag is absent (see 3.6 — that's 77% of the population), not a source to override a My Tag
when both exist.

#### 3.6 — mutually-exclusive coverage buckets

Denominator: 1183 (all buckets sum to this).

| bucket | tracks | % |
|---|---|---|
| Mood + Genres (both My Tag categories) | 122 | 10.3% |
| Mood only | 72 | 6.1% |
| Genres only | 34 | 2.9% |
| neither, but has ID3 genre | 911 | 77.0% |
| nothing at all | 44 | 3.7% |

**This is the number that should anchor S1.2's fallback-chain design.** Only 19.3% of joined tracks
(122 + 72 + 34 = 228) carry any My Tag usable for a Mood/Genres rule. The other 80.7% either fall back
to ID3 genre alone (77.0% — the single biggest bucket by a wide margin) or have no usable genre signal
at all (3.7%, and per E1b, BPM/key are still near-universal here so a BPM-based fallback still applies
to those). **A rule engine built only from My Tag combinations, however well-tuned, reaches at most 1
in 5 of these tracks; the ID3-genre x Mood table (3.4) and a BPM-driven fallback do most of the actual
coverage work.**

#### 3.7 — top 25 `Situation` x `Mood` pairs

`Situation` carries the energy axis, `Mood` the bank axis — rules needing both combine these two
tables.

| Situation tag | Mood tag | tracks |
|---|---|---|
| Peaktime | Party | 44 |
| Peaktime | Meezingers | 40 |
| Peaktime | Fout | 36 |
| Buildup | Feel Good | 21 |
| Buildup | Meezingers | 20 |
| Buildup | Fout | 20 |
| Peaktime | Hard | 17 |
| Buildup | Party | 17 |
| Peaktime | Guilty Pleasure | 17 |
| Buildup | Guilty Pleasure | 17 |
| Peaktime | Club vibe | 17 |
| Peaktime | Oldskool | 17 |
| Peaktime | Feel Good | 13 |
| Buildup | Ladies | 13 |
| Peaktime | Geile muziek | 13 |
| Peaktime | Ladies | 13 |
| Peaktime | Stampen | 12 |
| Big Impact | Party | 11 |
| Big Impact | Fout | 10 |
| Big Impact | Meezingers | 10 |
| Laatste kwartier | Hard | 10 |
| Peaktime | 00s | 9 |
| Peaktime | House | 9 |
| Big Impact | Hard | 9 |
| Peaktime | Smartlappen | 7 |

Full 25 pairs, not truncated. `Peaktime` and `Buildup` dominate this table simply because they are the
most-applied `Situation` tags at this population (127/1183 and 74/1183 respectively — see 3.9/3.10) —
the pairing itself doesn't reveal a strong Mood preference specific to either tag; `Party`/`Meezingers`/
`Fout` are simply the library's most common Moods overall and show up under whichever Situation tag has
the most tracks.

#### 3.8 — `Components` distribution

| tag | tracks | % |
|---|---|---|
| Nederlands | 31 | 2.6% |
| Duits | 27 | 2.3% |
| Viral | 18 | 1.5% |
| Style Transition | 3 | 0.3% |
| Dansje | 1 | 0.1% |
| Sport | 0 | 0.0% |

**Assessment: `Components` carries no lighting-relevant signal.** `Nederlands`/`Duits` are language
tags (Dutch/German-language tracks), `Viral` flags internet-trend tracks, `Style Transition` and
`Dansje` are set-construction/logistics markers. None of these correlate with mood, energy, or genre in
a way a lighting rule could use — this category is purely a filing/language dimension for the DJ's own
browsing, and should be excluded from S1.2's rule inputs entirely.

#### 3.9 — BPM median and IQR per tag

**Per `Mood` tag** (n = tracks with that Mood tag and populated BPM):

| Mood tag | n | median | IQR |
|---|---|---|---|
| Meezingers | 60 | 128.0 | [120.0, 138.2] |
| Party | 55 | 128.0 | [121.1, 140.0] |
| Fout | 49 | 128.0 | [105.0, 139.0] |
| Feel Good | 28 | 125.0 | [118.5, 128.0] |
| Guilty Pleasure | 27 | 123.0 | [103.0, 126.0] |
| Hard | 23 | 151.0 | [150.0, 157.7] |
| Geile muziek | 21 | 107.0 | [105.0, 127.0] |
| Club vibe | 21 | 140.0 | [128.0, 150.4] |
| Smartlappen | 19 | 125.0 | [117.0, 131.0] |
| Ladies | 18 | 108.0 | [103.0, 127.5] |
| Oldskool | 17 | 139.8 | [105.0, 151.0] |
| Stampen | 16 | 151.0 | [150.0, 160.0] |
| Dance Classics | 14 | 125.0 | [112.6, 129.5] |
| 00s | 13 | 117.0 | [100.0, 125.0] |
| 80s | 11 | 122.0 | [101.4, 136.1] |
| House | 11 | 129.0 | [127.0, 133.5] |
| 90s | 7 | 123.0 | [105.5, 131.4] |

Unlike `Situation`, `Mood` BPM medians do **not** form a clean energy-ordered arc — `Hard` (151.0) and
`Stampen` (151.0, literally "stomping") sit clearly high, `Geile muziek` and `Ladies` sit clearly low
(107/108), but the bulk of tags (`Meezingers`, `Party`, `Fout`, `Feel Good`, `Smartlappen`, `Dance
Classics`) cluster tightly around 123-128 regardless of what the tag name suggests about vibe. This is
expected — `Mood` is a bank/vibe axis, not an energy axis, so BPM separating it cleanly would have been
a coincidence, not a design target. Read `Hard`/`Stampen` as a genuine high-BPM signal usable as a
secondary check; don't expect BPM to rank-order the rest of the `Mood` vocabulary.

**Per `Situation` tag** (refresh of E1b's Q7, same 1183-track scope):

| Situation tag | n | median | IQR |
|---|---|---|---|
| Peaktime | 127 | 128.0 | [121.5, 146.5] |
| Buildup | 74 | 125.5 | [108.4, 130.0] |
| Begin | 34 | 125.0 | [114.5, 128.0] |
| Big Impact | 30 | 141.9 | [125.2, 150.0] |
| Background | 19 | 120.0 | [109.5, 126.0] |
| Laatste kwartier | 16 | 152.7 | [138.0, 162.5] |
| Afterparty | 8 | 145.0 | [136.8, 163.5] |
| Afbouw | 3 | 109.7 | [107.5, 118.8] |
| Kids | 2 | 150.0 | [145.0, 155.0] |

**Confirmed at the new scale, essentially unchanged from E1b.** The arc `Background` (120.0) <
`Begin`/`Buildup` (~125-126) < `Peaktime` (128.0) < `Big Impact` (141.9) < `Afterparty`/`Laatste
kwartier` (145/152.7) reproduces E1b's finding exactly, with `Afbouw`'s low median (109.7) also
unchanged. Sample sizes moved slightly (`Peaktime` 122->127, `Buildup` 73->74, `Big Impact` 28->30 —
consistent with the small My Tag drift noted in the top-level verdict), but the ordering and the
medians themselves are stable. **E1b's recommendation stands: BPM is the more reliable Situation-energy
proxy, especially for `Begin`/`Background`, where E1b already showed rekordbox's own energy verdict
does not separate from baseline.**

#### 3.10 — refresh of E1b/E1's two cross-tabs

**`Situation` x rekordbox energy** (baseline energy distribution across all 1183 joined tracks:
HIGH 740 / 62.6%, MID 386 / 32.6%, LOW 57 / 4.8% — unchanged from E1b):

| Situation tag | n | HIGH | MID | LOW |
|---|---|---|---|---|
| Peaktime | 127 | 70.1% | 28.3% | 1.6% |
| Buildup | 74 | 62.2% | 36.5% | 1.4% |
| Begin | 34 | 55.9% | 44.1% | 0.0% |
| Big Impact | 30 | 73.3% | 26.7% | 0.0% |
| Background | 19 | 57.9% | 42.1% | 0.0% |
| Laatste kwartier | 16 | 81.2% | 12.5% | 6.2% |
| Afterparty | 8 | 100.0% | 0.0% | 0.0% |
| Afbouw | 3 | 0.0% | 0.0% | 100.0% |
| Kids | 2 | 0.0% | 100.0% | 0.0% |

**Confirmed, effectively unchanged.** `Background` is still 57.9% HIGH / 0% LOW against a 62.6%/4.8%
baseline — rekordbox is still calling background tracks high-energy at the same rate E1b found.
`Begin` (55.9% HIGH, 44.1% MID — the highest MID share of any tag) and `Afbouw` (100% LOW, n=3) are
also numerically identical to E1b. **This design decision (override energy, do not inherit it,
especially for `Begin`/`Background`) is unaffected by anything measured in this probe.**

**Top-genre x bank** (10 genres, same list and same per-cell values as E1's original table — every
individual cell was diffed against E1's published numbers):

| genre | COOL | CLUB1 | CLUB2 | NATURAL | SUBTLE | HOT | VIVID | WARM | total |
|---|---|---|---|---|---|---|---|---|---|
| Pop | **116** | **2** | 0 | 2 | 11 | 2 | 5 | 4 | 142 |
| Techno | 77 | 6 | 1 | 0 | 0 | 0 | 1 | 0 | 85 |
| Dance | 71 | 4 | 1 | 1 | 2 | 1 | 1 | 4 | 85 |
| Eclectic | **56** | 3 | 0 | 2 | 3 | **8** | 2 | 10 | 84 |
| Deep-House | 53 | 11 | 5 | 0 | 2 | 1 | 1 | 4 | 77 |
| Urban | 38 | 1 | 0 | 0 | 0 | 4 | 3 | 3 | 49 |
| Carnaval Mix | 35 | 3 | 2 | 5 | 0 | 0 | 2 | 0 | 47 |
| EDM | 28 | 4 | 0 | 0 | 0 | 1 | 1 | 0 | 34 |
| Apres-Ski | 21 | 1 | 0 | 4 | 3 | 0 | 4 | 1 | 34 |
| Carnaval Kölle | 28 | 0 | 0 | 1 | 0 | 0 | 2 | 1 | 32 |

Overall: **COOL 523 (78.2%)**, CLUB1 35 (5.2%), WARM 27 (4.0%), VIVID 22 (3.3%), SUBTLE 21 (3.1%), HOT
17 (2.5%), NATURAL 15 (2.2%), CLUB2 9 (1.3%). E1's original: COOL 525 (78.5%) — the ~0.3-point drop is
fully explained by the two bolded cells above (`Pop` COOL 117->116/CLUB1 1->2, `Eclectic` COOL 57->56/HOT
7->8) — the exact two tracks already identified in the top-level verdict. **Every other cell in every
other genre row is identical to E1's original table, confirmed by direct diff, not re-derivation.**
COOL still dominates every top-10 genre and still exceeds the library-wide COOL baseline (78.2% vs
63.5%) — **this design decision is also unaffected.**

## CONTRADICTION with `docs/PROJECT-FOUNDATION.md`

`docs/PROJECT-FOUNDATION.md` line 39 states:

> **E1c** ... re-measurement after the DJ analysed the full ~7500-track library, and the source of the
> concrete `Genres × Mood` combination matrix the Stage 1 rules are authored from.

This probe's own task briefing states the same premise ("Re-measure the library join after the DJ ran
full lighting analysis on the whole collection"). **Neither happened, as far as this working copy shows.**
Deliverable 1 establishes the `content` table is byte-for-byte identical to E1/E1b's pre-analysis
baseline — same row count, same join rate, same unmatched breakdown, same sampled row values. If a
full-library analysis pass ran, it did not write a single new `content` row and did not touch a single
existing one beyond the two individually-reassigned tracks documented above (which look like manual
edits, not a bulk operation).

**Impact:** the Genres x Mood matrix in Deliverable 3 is real and directly usable for S1.2, but it
describes the *same* 1183-track population E1/E1b already characterized — not a larger, freshly-analysed
one. Any planning language assuming coverage grew past 39.9% (overall) or past 22.6%/30.4% (E1b's
playlist/history denominators) as a result of this analysis run should be treated as **not yet true**.
E1b's own arithmetic forecast (§Q3 in that document: analysing the 2540 never-lit playlist tracks would
take overall coverage to 67.6% and playlist coverage to 100%) remains exactly as valid, and exactly as
unrealized, as it was when E1b was written.

**Suggested resolution:** update `docs/PROJECT-FOUNDATION.md` line 39 to record that the anticipated
full-analysis pass has not yet reached the `content` table as of 2026-08-26, and that S1.2's rule
matrix is built from the same 1183-track population as E1/E1b, not an expanded one. If/when the DJ does
run analysis on the outstanding playlist backlog, this probe's script can be re-run to produce an E1d
(or a rerun of this same script) with a genuinely larger join population.

## Anonymisation note

No real track titles, artist names, or comment text that could identify a person appear in this
document. Genre names, colour display names, and My Tag names (including category names
`Mood`/`Situation`/`Genres`/`Components`) are reproduced verbatim per the task's requirements — they
are rule vocabulary, not personal data. Counts only, as in E1/E1b.

## What to remove later

This is a probe, not shipped code. Nothing permanent depends on it (see
`rekordbox-lighting-architecture`'s `experiments/` contract — the dependency arrow only ever points
inward).

- Delete `src/rbxlight/experiments/e1c_after_full_analysis.py` when this verdict is no longer needed
  for reference. `e1_library_join.py` and `e1b_real_denominator.py` may still be needed by other
  probes; check before deleting them too (per E1/E1b's own removal notes).
- No new dependencies were added — this probe reuses E1's `experiments` optional-dependency group
  (`pyrekordbox`, `sqlcipher3-wheels`) and E1's `work/master.db` copy helper.
- `work/master.db` is already gitignored and shared with E1/E1b; no change to its lifecycle.
- This document and E1's/E1b's documents are the durable record — keep all three even after the code is
  deleted.
