# E1d2 — Row-Creation Rerun (and a Methodological Correction)

**Status: answered, 2026-08-26.** Bounded, read-only probe, sixth in the E1/E1b/E1c/E1d/E1e series.
Extends [E1 — The Library Join](E1-library-join.md), [E1b — The Real Denominator](E1b-real-denominator.md),
[E1c — After Full Analysis](E1c-after-full-analysis.md), [E1d — Lighting Mode Row Creation](E1d-lighting-mode-row-creation.md),
and [E1e — The Phrase→Phase Mapping](E1e-phrase-phase-mapping.md). No production code shipped — see
"What to remove later" at the end.

Script: `src/rbxlight/experiments/e1d2_lighting_mode_rerun.py`
(`pip install -e ".[experiments]"`, then
`python -m rbxlight.experiments.e1d2_lighting_mode_rerun --before work/e1d2_before_user.db3`).

## Verdict — the methodological correction, first, plainly

**(a) is confirmed. Candidate selection was invalid.** `e1d2_candidate_tracks.py`'s "provably absent
from lighting" check — `song_id not present in ANY content.song_id row` — is not a test of absence. It
is a test of **ID resolvability**, and this project has now watched it fail in the most direct way
possible: a track the DJ could see carrying a real bank in rekordbox's own UI was certified "absent" by
that check, twice, because the row that actually held its bank was keyed to a `song_id` the check never
looked for.

**Direct proof, no fingerprint needed:** candidate 9 is the one track the DJ deliberately changed
(COOL→SUBTLE) this session. The diff below shows exactly one changed `content` row this session:
`content_id=1576`, `song_id=5800`. Candidate 9's **current** `DjmdContent.ID` is `62464681`. `5800 ≠
62464681` — the row that just visibly changed bank in rekordbox, under the DJ's own hand, is keyed to an
ID that is not this track's current ID by any measure. `5800` is also **below `DjmdContent`'s current
minimum ID (44138)** — the same "stale, pre-dates-the-current-numbering" signature E1 already
identified in 1,183 of the library's 2,966 `content` rows.

**Independent confirmation, no IDs at all:** row `1576`'s pre-session state (bank 13, COOL/LOW) was fed
into E1e's `(kind, k1, k2, k3, b) → phase` table using candidate 9's own current ANLZ `PSSI` data. The
predicted 22-phase sequence matches the row's actual (pre-session) phase sequence **exactly, all 22
positions** — and only 3 of the library's 111 other COOL/LOW rows even share the row count, let alone
the sequence. Two independent methods — raw ID mismatch, and a content-only fingerprint that never
touches an ID — agree on the same row. That is about as confirmed as a single-session probe gets.

**The fingerprint bridge — the recovery mechanism — worked cleanly for 5 of the 7 "already banked"
candidates**, each resolving to exactly one stale, non-resolving `content` row out of a same-bank
population of 8–5 candidates after filtering by row count (see table below). **It found nothing for 2
of the 7** (candidates 4 and 7) — reported honestly as a real gap, not glossed over (see "Where the
bridge failed" below).

**Consequence for every coverage figure this project has published:** E1's 39.9%/60.1%
resolves/doesn't-resolve split, E1b's "real denominator" work, and E1c's post-analysis figures are all
built on `song_id == DjmdContent.ID` equality. That equality is **necessary but not sufficient** for a
row to be "the track's lighting row" — a track can (and, per this session, does) carry a live bank
assignment that ID-equality reports as absent. **We currently have no reliable way to test whether a
library track has a lighting row, full stop.** Every prior percentage in this project measures *ID
resolvability*, not *lighting coverage*. The true lighting-coverage fraction is higher than any figure
this project has published — how much higher is not yet measurable, because the fingerprint bridge that
*can* find stale rows only works for tracks with a readable ANLZ `PSSI` file (61.3% of already-known-lit
tracks per E1e) and a bank already correctly guessed, and it is not exhaustive even then (2 of 7 in this
very session).

**Did content gain rows, and which candidates?** Yes — 6 new rows, but **not** for the candidates
originally expected to produce them:

- Candidate 2 (fully untouched pre-session, no bank shown): **zero new or changed rows.** Still
  genuinely absent after this session — the one clean negative control in the set.
- Candidate 9 (untouched-looking, but displaying COOL): its row **existed already**, under a stale ID —
  confirmed above.
- Candidate 10 (fully untouched pre-session, no bank shown): got a **genuinely new** row —
  `content_id=2972`, bank COOL/MID, with a full 28-row `phrase_data` set that reproduces its own PSSI
  prediction **28/28, exactly** (see Deliverable 3 — this is the first ground-truth test of E1e's
  forging mechanism, not a back-derived one).
- The other 5 new rows (`content_id` 2967–2971) are **orphans** (`macro_pattern_id=0`, zero
  `phrase_data`) for **5 tracks that are not among the 10 candidates at all** — same unresolved
  `artist_id`, distinct titles, all resolving to live `DjmdContent.ID`s. These look like incidental
  browser/preview activity, not LIGHTING-mode editor engagement — see Deliverable 1.

So: **candidate 2 got nothing (consistent with E1d's original "opening alone creates nothing" finding);
candidate 9's bank change landed on a pre-existing stale row (proving (a) directly); candidate 10 got a
brand-new, fully-populated row that matches its own PSSI perfectly.** Three different outcomes from
three candidates that all looked identically "untouched" before the session — itself more evidence that
UI appearance is not a reliable absence signal.

## Evidence

### Refresh procedure

`pgrep -x rekordbox` returned exit 1 at every checkpoint (before the working-copy refresh, before the
master.db refresh, and again immediately before running the probe) — re-verified each time, never
assumed from an earlier check.

- `work/e1d2_before_user.db3` — the BEFORE snapshot, taken by the orchestrator before this session,
  **read-only input, never overwritten.**
- `work/user.db3` / `work/macro.db3` — refreshed via `rbxlight pull` (unmodified `sync.py` path).
  `user.db3` MD5 changed (confirming a real pull, not a no-op); `macro.db3` MD5 unchanged (its live mtime
  is byte-identical to the working copy's — confirmed via `check_macro_db_untouched`, matching E1d's own
  mechanism).
- `work/master.db` — refreshed via `ensure_master_db_copy(refresh=True)`. Read-only, forever, per the
  safety skill.

### Deliverable 1 — did `content` gain rows?

| metric | before | after |
|---|---|---|
| `content` rows | 2966 | 2972 |
| `phrase_data` rows | 41742 | 41770 |
| new `content` rows | — | 6 |
| changed `content` rows | — | 1 |

All 6 new rows, dumped in full:

| id | song_id | macro_pattern_id | bank/energy | resolves to a live `DjmdContent.ID`? |
|---|---|---|---|---|
| 2967 | 259029032 | 0 | NONE/NONE (orphan) | yes |
| 2968 | 158069819 | 0 | NONE/NONE (orphan) | yes |
| 2969 | 155605537 | 0 | NONE/NONE (orphan) | yes |
| 2970 | 6610129 | 0 | NONE/NONE (orphan) | yes |
| 2971 | 3755011 | 0 | NONE/NONE (orphan) | yes |
| 2972 | 1894 | 7 | COOL/MID | **no** — below the current `DjmdContent` minimum ID |

**None of the 6 new `song_id`s match any of the 10 candidates' current `DjmdContent.ID`s.** The 5
orphan rows (2967–2971) share one unresolved `ArtistID` and are titled generically (sample-pack-style
names) — not part of this session's candidate list at all. They carry **zero `phrase_data` rows**,
matching E1's pre-existing population of 61 `macro_pattern_id=0` orphans. The most plausible
explanation: passive browser/preview interaction (track selection, waveform hover) creates a bare
orphan `content` stub with no bank and no phrase programme — a much lighter trigger than actually
loading the LIGHTING-mode macro editor. This is a hypothesis, not a proven trigger; this probe did not
control for what interaction produced them.

`content_id=2972` is different in kind: it has a real bank (`macro_pattern_id=7`, COOL/MID) and a full
28-row `phrase_data` set (Deliverable 3) — identified as candidate 10 by its unique phrase count (28,
the only one of the 10 candidates' own PSSI-read phrase counts equal to 28 — see
`work/e1d2-candidates.txt`). Its `song_id` (1894) is itself already a stale, non-resolving value — so
even a **freshly minted** row was not written with the track's current `DjmdContent.ID`. Whatever
identifier rekordbox is keying `content.song_id` on, it is not simply "the current ID of the track being
opened," for either a pre-existing row (candidate 9) or a brand-new one (candidate 10).

The one changed row:

| field | before | after |
|---|---|---|
| `id` | 1576 | 1576 (unchanged) |
| `song_id` | 5800 | 5800 (unchanged) |
| `macro_pattern_id` | 13 (COOL/LOW) | 16 (SUBTLE/LOW) |

### Deliverable 2 — candidate 9: does the changed row carry a stale `song_id`?

**Yes, decisively.**

| | value |
|---|---|
| changed row's `song_id` | 5800 |
| candidate 9's current `DjmdContent.ID` | 62464681 |
| equal? | **no** |
| `5800` vs current `DjmdContent` min ID (44138) | below it — same signature as E1's 1,183 sub-minimum stale IDs |

Independent, ID-free confirmation via the fingerprint bridge, run against the **BEFORE** snapshot (the
row's original bank, COOL/LOW = `macro_pattern_id=13`, since the DJ's own change moved it out of that
bank during this session — searching AFTER-state COOL/LOW rows would miss it by construction):

- Predicted phase sequence (candidate 9's own `PSSI`, `(kind,k1,k2,k3,b)` table for `mpid=13`):
  `[1, 2, 2, 5, 2, 2, 2, 5, 2, 2, 2, 4, 2, 3, 4, 4, 4, 4, 4, 3, 5, 6]`
- Actual sequence (row 1576, before the session): **identical, all 22 positions.**
- Discriminating power: 111 other `content` rows share bank 13 (COOL/LOW); only **3** also share the
  22-phrase row count; **exactly 1** (this row) matches the full sequence.

Two independent methods — a raw ID comparison and a phrase-fingerprint that uses no ID at all — agree
on the same row. **(a) is proven outright for this track**, exactly as the task anticipated.

### Deliverable 3 — `phrase_data`, and candidate 10 as ground truth for forging

**28 new rows, all for `content_id=2972` (candidate 10). 22 changed rows, all for `content_id=1576`
(candidate 9, the bank change — see E1d for the row-by-row `macro_assign` copy-through, reproduced
here).**

Candidate 10's new row is the **first ground-truth test** of E1e's forging mechanism — every prior
validation was back-derived from rows that already existed; this row was written by rekordbox itself,
during this session, for a track that had genuinely zero prior `content` row:

| | |
|---|---|
| `macro_pattern_id` assigned | 7 (COOL/MID) |
| PSSI `len_entries` | 28 |
| `phrase_data` row count | 28 |
| predicted phase sequence (E1e's table, `mpid=7`) | `[1,2,3,9,4,5,5,8,2,8,8,9,9,5,5,9,2,2,2,5,8,9,2,8,8,9,8,10]` |
| actual phase sequence (rekordbox's own write) | **identical, all 28 positions** |
| per-row hit rate | **28/28 (100%)** |

This is a clean, positive result for E1e's forging plan: given only a track's own `PSSI` data and a
chosen bank, the predicted `phrase_num → macro_assign.phase → macro_id` chain reproduces exactly what
rekordbox itself wrote, on a track this project had never seen lit before. It also incidentally answers
one of E1d's open questions: **a fresh `content` row's default bank is `macro_pattern_id=7` (COOL/MID)**
— not `macro_pattern_id=0`, when the LIGHTING-mode editor is actually engaged (as opposed to the bare
orphan stubs seen for the other 5 new rows).

Candidate 9's bank-change rewrite of `phrase_data` matches E1d's original finding exactly (`macro_id`
values drawn wholesale from bank 16's `macro_assign` — see E1d for the full row dump; this session adds
nothing new to that mechanism beyond confirming it again on a different track).

### Deliverable — the fingerprint bridge across all 7 "already banked" candidates

For each candidate, the DJ-reported bank name + the track's own PSSI `mood` field (giving energy) select
a candidate `macro_pattern_id`; all 3 possible energies were tried and reported, not just the
mood-implied one, since PSSI's `mood` only matches `macro_pattern.energy` ~98% of the time per E1e.

| candidate | bank shown | best `mpid` (bank/energy) | PSSI phrase count | rows sharing bank | rows sharing bank+count | exact fingerprint matches |
|---|---|---|---|---|---|---|
| 1 | HOT | 3 (HOT/HIGH) | 13 | 53 | 4 | **1** — `content_id=1783`, `song_id=20472` |
| 3 | NATURAL | 2 (NATURAL/HIGH) | 18 | 70 | 3 | **1** — `content_id=1942`, `song_id=19297` |
| 4 | SUBTLE | tried 4/10/16 | 23 | 67/87/8 | 1/1/0 | **0 — no match at any energy** |
| 5 | VIVID | 6 (VIVID/HIGH) | 15 | 67 | 5 | **1** — `content_id=2097`, `song_id=8784` |
| 6 | VIVID | 6 (VIVID/HIGH) | 21 | 67 | 4 | **1** — `content_id=1927`, `song_id=288` |
| 7 | VIVID | tried 6/12/18 | 19 | 67/86/16 | 0/5/1 | **0 — no match at any energy** |
| 8 | NATURAL | 14 (NATURAL/LOW) | 16 | 23 | 4 | **1** — `content_id=1777`, `song_id=413` |

Every one of the 5 successful matches' `song_id` is **below the current `DjmdContent` minimum (44138)**
— the same stale signature as candidates 9 and E1's broader population, confirmed for each:
20472, 19297, 8784, 288, 413 are all non-resolving. **This is the recovery mechanism the task asked
this probe to demonstrate**, working end-to-end on 5 independent tracks: no ID lookup, no assumption
about which stale ID a track "should" have — a content-only fingerprint (bank + PSSI phrase-kind
sequence + row count) picks the one matching row out of a same-bank population of 53–70, every time it
succeeds.

**How discriminating is the fingerprint, honestly?** Very, when it resolves at all: in every one of the
5 successes, exactly **1** row matched, never more than 1 — the row-count filter alone narrows a
same-bank population of 53–70 down to 3–5 candidates, and the full phase-sequence comparison always
picked exactly one of those. It never produced an ambiguous multi-row result in this session. But it is
not exhaustive:

### Where the bridge failed (candidates 4 and 7)

For both, all 3 energy guesses were tried; none produced an exact match, and relaxing the row-count
filter to look for the best *partial* overlap still found nothing convincing (candidate 4's best
partial match: 39% of positions, wrong row count; candidate 7's best: 65%, also a different row count).
Two explanations are consistent with the data and this probe cannot distinguish between them:

1. **Temporal drift.** E1e already found that 10.0% of currently-lit tracks show `PSSI.len_entries ≠
   phrase_data` row count — meaning a track's on-disk musical analysis and its stored lighting programme
   can drift apart after the fact (most plausibly: re-analysis after the lighting programme was
   written). If candidates 4/7's stale rows exist but were written against an *older* PSSI read, today's
   PSSI would no longer predict them.
2. **The subkind table's own known gaps.** E1e's subkind table has no direct validation for some bank
   combinations and is only 99.35% accurate overall — a genuine (if rare) subkind mismatch would also
   produce exactly this failure mode.

**Reported plainly, not glossed over: for 2 of 7 candidates, this probe cannot confirm or rule out
hypothesis (a) via the fingerprint alone.** Given (a) is already proven for candidate 9 by direct ID
comparison, and confirmed independently for 5 of the remaining 7, the most likely explanation for 4 and
7 remains the same stale-ID mechanism — this probe simply lacks a matching, undrifted `PSSI` read to
prove it for these two specific tracks.

### Deliverable 4 — everything else

Full-table diff, every column, `user.db3`:

| table | before | after | only_before | only_after |
|---|---|---|---|---|
| `content` | 2966 | 2972 | 1 | 7 |
| `phrase_data` | 41742 | 41770 | 22 | 50 |
| `lighting_data` | 264 | 264 | 0 | 0 |
| `venue` | 2 | 2 | 0 | 0 |
| `fixture` | 36 | 36 | 0 | 0 |
| `direct_control` | 35 | 35 | 0 | 0 |
| `lighting_property` | 20 | 20 | 0 | 0 |

`lighting_property` is byte-identical, including both version-looking keys (`DbVersionNum=1854`,
`MacroVersionNum=1061`) — same as E1d found. No counter or version stamp moved this session either.
`macro.db3` confirmed untouched via mtime equality (same mechanism as E1d).

## The two things the DJ volunteered

### Transitions (candidate 3)

**No dedicated transition layer exists, and none was used on this track.** Checked three candidate
mechanisms directly:

1. **An INTERLUDE macro (`macro_pattern.pattern=99`) in `phrase_data`?** No. Candidate 3's resolved row
   (`content_id=1942`) uses none of the 6 factory `INTERLUDE` macro_ids (`911`–`916`). Library-wide,
   exactly **one** `phrase_data` row anywhere uses an INTERLUDE macro_id (`content_id=981`, `phrase_num=16`,
   `macro_id=916`, overriding an `initial_macro_id=126`) — a genuine, pre-existing, unrelated **manual
   phrase-level override** by hand, not something tied to this session or to candidate 3.
2. **`macro_event` rows?** Still **0**, confirmed fresh this session — unused, as documented in the
   schema skill.
3. **Something inside the macro XML itself?** This is the actual explanation. Candidate 3's phrase 1
   macro (`HIGH INTRO2 NATURAL`, `macro_id=8`) programs several fixture slots with brightness dips and
   flashes that land in the final third of its 32-beat length (e.g. slot 5/6: a blackout-flash-blackout
   pattern peaking around beat 26–29 of 32) before the hard cut to phrase 2's macro
   (`HIGH CHORUS1 NATURAL`). **The schema has no crossfade or transition primitive between phrase
   macros — switching from one phrase's macro to the next is always a hard cut** (per the schema skill:
   `phrase_data` selects one whole macro per phrase, nothing blends across the boundary). What the DJ
   perceived as "transition stuff" is very likely this macro's own authored tail content creating a
   natural build/release right before the cut, not a distinct mechanism.

**This matters for Stage 3:** there is no separate transition layer to reproduce. If a future stage
wants an actual crossfade between phrase macros, it does not exist in rekordbox's own data model today
and would have to be built as new functionality, not extracted from existing rows.

### Analysis Lock (candidate 8)

`djmdContent.Analysed` takes exactly two observed values across the library: `105` (unlocked) and `233`
(locked) — a single set bit (`233 − 105 = 128`). Candidate 8 (`DjmdContent.ID=357035`) is one of them:
`Analysed=233`.

| | value |
|---|---|
| library tracks measured (current `work/master.db`) | **7,615** — not the 7,607 figure quoted in the task; using the freshly-measured count here, not the recalled one |
| locked (`Analysed=233`) | **36** / 7,615 (0.47%) |
| locked AND unreadable ANLZ `PSSI` | **1** / 36 (2.8%) |

**The overlap is small.** Locking a track for Analysis Lock does not, in this library, correlate with
having no readable `PSSI` — 35 of the 36 locked tracks have perfectly good analysis data; only the
lock itself blocks *re*-analysis. E1e's forging-blocking figure (38.7% of lit tracks with no readable
ANLZ) is a **much larger and structurally separate problem than Analysis Lock** — most of that 38.7%
is not explained by locking. Locking matters concretely in one narrow way: if a future stage tries to
fix "no readable PSSI" by bulk re-analysing the library, these 36 tracks (or however many of them
overlap with the un-analysed set at that time) will silently refuse, and the fix must detect and report
that rather than assume success.

## Anonymisation note

No real track titles, artist names, or comment text appear in this document, its script, or its console
output. Integer IDs (`content.id`, `song_id`, `macro_id`, `macro_pattern_id`, `DjmdContent.ID`),
bank/energy names, phase/kind codes, and row counts are reproduced verbatim — schema/rule vocabulary and
aggregate numbers, not personal data, per the same standard E1–E1e applied. The 5 unrelated new-orphan
tracks (Deliverable 1) are described only by shape (shared artist_id, generic titles), never quoted.

## What to remove later

This is a probe, not shipped code. Nothing permanent depends on it (see
`rekordbox-lighting-architecture`'s `experiments/` contract — the dependency arrow only ever points
inward).

- Delete `src/rbxlight/experiments/e1d2_lighting_mode_rerun.py` when this verdict is no longer needed for
  reference. It imports from `e1_library_join.py`, `e1b_real_denominator.py`, `e1d_lighting_mode_diff.py`,
  `e1d2_candidate_tracks.py`, and `e1e_phrase_phase_mapping.py` — all still used elsewhere; check each
  before deleting any of them.
- `work/e1d2_before_user.db3` is not reproducible (captured a specific pre-session state) — keep it only
  as long as this probe might need to re-diff; safe to delete once this document is considered final.
- No new dependencies were added.
- This document and E1/E1b/E1c/E1d/E1e's documents are the durable record — keep all six even after the
  code is deleted. **The methodological correction in this document's Verdict — that ID-equality
  absence is not a lighting-coverage test — must be read alongside every coverage figure E1/E1b/E1c ever
  published; it is a correction to those documents' interpretation, not a replacement for them.**
