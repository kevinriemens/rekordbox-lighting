# E1d — Lighting Mode Row Creation

**Status: answered, 2026-08-26.** Bounded, read-only probe, fourth in the E1/E1b/E1c series.
Extends [E1 — The Library Join](E1-library-join.md), [E1b — The Real Denominator](E1b-real-denominator.md),
and [E1c — After Full Analysis](E1c-after-full-analysis.md). No production code shipped — see
"What to remove later" at the end.

Script: `src/rbxlight/experiments/e1d_lighting_mode_diff.py`
(`pip install -e ".[experiments]"`, then
`python -m rbxlight.experiments.e1d_lighting_mode_diff --before work/e1d_before_user.db3`).

## Verdict

**The hypothesis is NOT confirmed. `content` gained zero new rows, not 8.** Opening 8 tracks in
rekordbox's LIGHTING mode editor, then quitting the app, produced **exactly one changed row** across
the whole of `user.db3` — an **existing** `content` row whose bank was hand-changed, plus that same
track's 11 `phrase_data` rows. No row, in any table, was created. This is reported plainly and
immediately, per this probe's own instructions, rather than reframed to rescue the hypothesis.

**Lead answers, as requested:**

1. **Did `content` gain 8 rows? No — it gained zero.** Row count is 2966 before and after, identical
   to E1/E1b/E1c's baseline. The DJ's belief that these 8 tracks had "probably never been opened [in
   LIGHTING mode] before" does not hold for at least one of them: `content.id=2955` already existed,
   unchanged, before this session — it was not created by it.
2. **What `macro_pattern_id` did new rows default to? N/A — there were no new rows to default
   anything.** The only `content` mutation observed is a hand-driven **change** to an existing row
   (`macro_pattern_id` 1 → 20, i.e. COOL/HIGH → CLUB2/HIGH), not a creation event. This experiment
   cannot speak to rekordbox's creation-time default at all.
3. **Are the new `phrase_data` rows a reproducible copy of `macro_assign`? There are no new rows —
   but the *rewritten* rows on the bank-changed track are.** Every one of the 11 rewritten
   `phrase_data.macro_id` values for `content_id=2955` is drawn exactly from the new bank's
   (`macro_pattern_id=20`) `macro_assign.macro_id` set — a 100% membership match, shown row-by-row
   below (Deliverable 3). This is **direct, positive evidence for E2**: a bank change on an
   already-lit track does propagate into `phrase_data`, the layer that actually fires. But the
   *phrase_num → macro_assign.phase* correspondence is not simple identity (see Deliverable 3) — the
   track keeps its own native 11-phrase structure even though the new bank's `macro_assign` only
   defines 10 phases, so forging this mapping from `macro_assign` alone, for a track we have never
   seen phrase-analysed, is not fully solved by this probe.

**What this means for the forging plan, bluntly:** this probe answers "what happens when an existing
lit track's bank is changed" (strong E2 evidence, valuable on its own) but answers **nothing** about
row *creation* — the one question the task was designed to settle. E1/E1b/E1c already ruled out
ordinary track analysis as a creation trigger; this probe was rekordbox-lighting's best remaining lead
(LIGHTING-mode editor open) and it also came back negative for creation, though not for the same
reason — see "Why this is different from E1c's negative result" below.

## Evidence

### Refresh procedure (Step 0)

`pgrep -x rekordbox` returned exit 1 (not running) at three separate points: before the working-copy
refresh, immediately before the master.db refresh, and again before running the diff itself. All
three re-checks per this probe's own instructions, not assumed from any earlier verification.

- `work/e1d_before_user.db3` — a byte copy of the **pre-E1d** `work/user.db3`, taken by the
  orchestrator before the DJ's session, **read-only input to this probe, never overwritten.** MD5
  `f209b90f3533c3e3f041c6a29d4430c4`.
- `work/user.db3` and `work/macro.db3` — refreshed via `rbxlight pull` (the existing `sync.py` pull
  path, unmodified). New MD5 for `user.db3`: `13d5587aba9ba8e65fa71cbb422fe205` (differs from the
  BEFORE snapshot — confirms a real pull happened, not a no-op).
- `work/master.db` — refreshed via `ensure_master_db_copy(refresh=True)` (E1's helper, unmodified).
  File size unchanged (84869120 bytes).

No adaptation was needed for either refresh path.

### Deliverable 1 — did `content` gain rows?

| metric | before | after | baseline (E1c) |
|---|---|---|---|
| `content` row count | 2966 | 2966 | 2966 |
| max `content.id` | 2966 | 2966 | 2966 |
| new rows | — | **0** | (8 expected) |
| removed rows | — | 0 | — |
| changed rows | — | **1** | — |

**Zero new `content` rows.** The row-count, max-id, and full-table set-diff (every column, not just
aggregates) all agree: nothing was inserted. The one row that changed:

| field | before | after |
|---|---|---|
| `id` | 2955 | 2955 (unchanged) |
| `song_id` | 87067495 | 87067495 (unchanged) |
| `master_db_id` | 127286662 | 127286662 (unchanged) |
| `macro_pattern_id` | 1 (COOL / HIGH) | 20 (CLUB2 / HIGH) |

Answering the sub-questions the task posed, for this one row (there are no "new" rows to apply them to):

- **`master_db_id` is the same constant `127286662`** seen on all existing rows (E1's finding). This
  edit did not touch it.
- **`song_id` 87067495 resolves to a current `DjmdContent.ID`** in the freshly-refreshed `master.db`
  — confirmed directly, not inferred. Consistent with the task's expectation that recently-touched
  tracks resolve; also consistent with E1/E1c's reading that the 60% stale-ID population is historical
  debris, not an active, ongoing problem.
- **Is the new `content.id` a simple max+1 continuation, or gap-reuse?** Not observable — there is no
  new id to examine. `max(content.id)` is 2966 both before and after; nothing was appended.
- **What `macro_pattern_id` did it get on creation?** Not observable for the same reason — `id=2955`
  was not created by this session, it pre-existed.

**This directly contradicts the "these tracks were probably never opened in LIGHTING mode before"
premise, at least for this one track.** A `content` row already existed for it, with a real
(non-zero, non-orphan) bank assignment, prior to the DJ's session. Either this track had been opened
in LIGHTING mode at some earlier, unrecorded time, or `content` rows come from somewhere this project
has not yet identified. This probe cannot distinguish between those — it only confirms the row was
not created *now*.

### Deliverable 2 — the one track whose bank changed

**An *existing* row changed — not one of an expected 8 new ones.** `content_id=2955` /
`song_id=87067495` moved from `macro_pattern_id=1` (**COOL**, energy **HIGH**) to `macro_pattern_id=20`
(**CLUB2**, energy **HIGH**). Energy did not change (HIGH → HIGH); only the bank did. This is the
"changed the bank on exactly 1 of them" the DJ described — found cleanly, as a single-row diff, with no
ambiguity. But per the task's own fallback instruction: **"If instead an existing row changed rather
than one of the new ones, say so — it would mean that track already had a `content` row and the
hypothesis needs qualifying."** That is exactly what happened, and it is said plainly here.

### Deliverable 3 — did `phrase_data` gain rows?

**Zero new rows.** 41742 before, 41742 after — identical to baseline. **11 rows changed**, all for
`content_id=2955` — exactly the phrase count for a HIGH-energy, pattern-1-6 bank (11 phases per the
schema skill's measured table), matching the row's *original* bank (COOL, pattern 1). No other
`content_id` has a single changed, added, or removed `phrase_data` row.

**Complete dump — the representative track's full rewritten programme** (`content_id=2955`, the only
track this probe can show; there are no newly-created tracks to dump instead):

| phrase_num | macro_id (before) | initial_macro_id (before) | macro_id (after) | initial_macro_id (after) |
|---|---|---|---|---|
| 1 | 7 | 7 | 211 | 211 |
| 2 | 13 | 13 | 212 | 212 |
| 3 | 13 | 13 | 212 | 212 |
| 4 | 25 | 25 | 214 | 214 |
| 5 | 31 | 31 | 215 | 215 |
| 6 | 31 | 31 | 215 | 215 |
| 7 | 43 | 43 | 216 | 216 |
| 8 | 25 | 25 | 214 | 214 |
| 9 | 31 | 31 | 215 | 215 |
| 10 | 31 | 31 | 215 | 215 |
| 11 | 55 | 55 | 217 | 217 |

- **`phrase_num` is contiguous 1..11** for this track, both before and after — no gaps, no sparsity.
  Observed range for this track is exactly `1..11`, at the upper end of the schema skill's documented
  `1..99` range but not near it.
- **`macro_id == initial_macro_id` on every single row, before AND after.** This track carries none of
  the library's 36 phrase-level overrides (`macro_id <> initial_macro_id`) — it is, and remains, a
  "pristine" (non-hand-tuned-at-the-phrase-level) track. This matters for what this probe can and
  cannot say about overrides — see "still unknown" below.
- **Row count did not change when the bank changed (still 11), even though the new bank's
  `macro_assign` only defines 10 phases** (CLUB1/CLUB2 patterns have 10 HIGH-energy phases, not 11 —
  read directly from `macro_assign`, never derived, per the schema skill). This is the single most
  load-bearing observation in this probe: **`phrase_data`'s row count/structure is anchored to the
  track's own phrase analysis, not to the bank's phase count.** A bank swap does not resize
  `phrase_data` to match the new bank's phase count — it re-maps into whatever the new bank offers.

**Does the new `macro_id` match what `macro_assign` prescribes? Yes, at the value level — 100%.**
Every rewritten `macro_id` is a member of `macro_pattern_id=20`'s `macro_assign.macro_id` set. Side by
side, matching each `phrase_data` row to the *first* `macro_assign` phase carrying that same
`macro_id` (macro_assign itself repeats values across adjacent phases in the CLUB banks — see below):

| phrase_num | macro_id (after) | matched `macro_assign` phase (pattern 20) |
|---|---|---|
| 1 | 211 | 1 |
| 2 | 212 | 3 |
| 3 | 212 | 3 |
| 4 | 214 | 5 |
| 5 | 215 | 6 |
| 6 | 215 | 6 |
| 7 | 216 | 8 |
| 8 | 214 | 5 |
| 9 | 215 | 6 |
| 10 | 215 | 6 |
| 11 | 217 | 9 |

`macro_pattern_id=20`'s full `macro_assign` (10 phases, read directly):
`(1,211) (2,211) (3,212) (4,213) (5,214) (6,215) (7,215) (8,216) (9,217) (10,217)`.

For comparison, the *original* bank's (`macro_pattern_id=1`, 11 phases):
`(1,1) (2,7) (3,13) (4,19) (5,25) (6,31) (7,37) (8,43) (9,49) (10,55) (11,61)`, and this track's
BEFORE phrase rows matched phases `[2,3,3,5,6,6,8,5,6,6,10]` respectively.

**The two phase-index sequences are `[2,3,3,5,6,6,8,5,6,6,10]` (before, 11-phase bank) and
`[1,3,3,5,6,6,8,5,6,6,9]` (after, 10-phase bank).** The middle nine values (`phrase_num` 2 through
10) map to the **exact same phase index** in both banks (3,3,5,6,6,8,5,6,6). Only the two boundary
phrases (`phrase_num` 1 and 11) shift down by exactly one phase index — precisely the amount the new
bank's phase count shrank by (11 → 10). **This is a strong, specific, and reproducible-looking
pattern**, but it is drawn from a single track's single bank change, and it points to an internal
per-track "phrase profile" — most plausibly rekordbox's own phrase-*kind* analysis (Intro/Verse/
Chorus/Bridge/Outro-style structure, independent of `user.db3`/`macro.db3`) driving which
`macro_assign` phase each `phrase_num` pulls from. **This mapping function is not present anywhere in
the LightingDB schema this project has access to.** It is the one unexplained value in this whole
probe, and it is exactly the value forging most needs: without it, we can prove *what* macro_ids a
freshly-lit track would get (any value copied wholesale from `macro_assign`), but not reliably *which*
`phrase_num` gets *which* of the bank's phases, for a track this project hasn't already seen lit.

**Does `phrase_data` row count correlate with a track's musical phrase count?** Consistent with it —
11 rows matches the 11-phase HIGH/pattern-1-6 count exactly, for a track that was (before this
session) on a HIGH/pattern-1 (COOL) bank. This is the expected shape per the schema skill's phase-count
table, read directly rather than derived, and this probe adds no correction to that table.

### Deliverable 4 — did the bank change rewrite `phrase_data`? (E2 evidence)

**Yes — prominently, this is direct evidence for E2.** All 11 `phrase_data` rows for `content_id=2955`
were rewritten in the same commit as the `content.macro_pattern_id` change, with new `macro_id` values
drawn cleanly from the new bank's `macro_assign`. **A bank change on an already-lit track is NOT
silently ignored by the layer that actually fires** — at minimum, at edit time, in the LIGHTING mode
editor, changing a track's bank does propagate down into `phrase_data`. This directly informs the
three stories E2 currently gates: repointing `macro_assign` for a bank, at least when done through
rekordbox's own editor on a track that has no phrase-level overrides, is not merely cosmetic — it
changes what plays.

**The caveat that must travel with this finding:** this track had `macro_id == initial_macro_id`
everywhere — it had **no pre-existing phrase-level overrides** to potentially protect. The schema
skill's warning that `phrase_data` "is user work and must never be clobbered" and "shadows
`macro_assign`" is about tracks that DO have `macro_id <> initial_macro_id` rows (36 in the library).
**This probe cannot say whether rekordbox would have overwritten a hand-tuned override the same way**
— it never encountered one. That is now a named, explicit unknown (see Verdict question 3).

### Deliverable 5 — everything else

Full-table diff, every column, `user.db3`:

| table | before rows | after rows | only-before | only-after |
|---|---|---|---|---|
| `content` | 2966 | 2966 | 1 | 1 |
| `phrase_data` | 41742 | 41742 | 11 | 11 |
| `lighting_data` | 264 | 264 | 0 | 0 |
| `venue` | 2 | 2 | 0 | 0 |
| `fixture` | 36 | 36 | 0 | 0 |
| `direct_control` | 35 | 35 | 0 | 0 |
| `lighting_property` | 20 | 20 | 0 | 0 |

`lighting_data` (baseline 264) is byte-identical — no per-track/per-fixture override was touched.
`venue`, `fixture`, `direct_control` are untouched, as expected (nothing in this session involved venue
or fixture patching). **`lighting_property` is byte-identical, including both version-looking keys**:
`DbVersionNum=1854` and `MacroVersionNum=1061` — both exactly the values E1c already recorded. **No
counter, sequence, or version stamp was bumped by this session.** If forging needs to touch any
row-count or version field to stay consistent, this probe found none that moved for a normal edit —
though this is one data point, not a guarantee across all edit types.

`macro.db3` was independently confirmed untouched: there is no BEFORE byte-copy of `macro.db3` (only
`user.db3` got one per the task setup), so the check used is mtime equality — the live file's mtime
(`Aug 25 14:44:45`) is identical to the mtime already carried by the working copy from the prior pull,
proving the live file was not rewritten at any point across this session, not just "probably wasn't."

## Why this is different from E1c's negative result

E1c found that a full **export-mode** phrase-analysis pass touched `content` **not at all** — the
table was byte-for-byte unchanged, full stop. E1d finds that a **LIGHTING mode** editor session, on
tracks the DJ opened deliberately, also created **no new rows** — but it DID touch one **existing**
row's `phrase_data`, with real, structured, bank-derived content. These are not the same kind of
negative result: E1c showed the table entirely inert under one workflow; E1d shows the table is
capable of being rewritten, cleanly and derivably, but only for a track it turns out already had a row.
**The open question this leaves for a future E1e-style probe:** does LIGHTING mode create a `content`
row the *first* time a track with **zero** prior `content` row is opened there, or does row creation
require some other trigger this project hasn't identified yet (first bank *change* specifically,
rather than merely opening the editor; a specific save action; something else)? This probe cannot
answer that, because — per the finding above — it is now uncertain whether any of the 8 tracks opened
were actually new to `content` at all.

## Verdict — plain answers

1. **Is the hypothesis confirmed? No.** Opening a track in LIGHTING mode did not create any
   `content` or `phrase_data` rows in this session. The one row that changed already existed before
   the session started.
2. **Is forging viable?** Partially, and with one specific, named gap:
   - **The macro_id VALUES are fully derivable.** Every value written into `phrase_data.macro_id` /
     `initial_macro_id` on a bank change is drawn exactly from that bank's `macro_assign` — a clean,
     reproducible, 100%-verified copy at the value level. `content.master_db_id` is a known constant.
     `content.macro_pattern_id` is just whatever bank we choose.
   - **The phrase_num → macro_assign.phase mapping is NOT fully derivable from this probe.** This
     track's 11 phrase_nums mapped to bank-1's phases `[2,3,3,5,6,6,8,5,6,6,10]` and, after the bank
     change, to bank-20's phases `[1,3,3,5,6,6,8,5,6,6,9]` — a specific, stable-looking, per-track
     pattern, but its origin (almost certainly the track's own phrase-*kind* structure from
     rekordbox's musical analysis) is not present in `user.db3` or `macro.db3` and was not reverse
     engineered here. **Honest statement: we do not know, from this probe alone, how to compute which
     `phrase_num` should receive which bank phase for a track we have not already seen lit by
     rekordbox.** Forging a `content` row's bank assignment is tractable today; forging its
     `phrase_data` phrase-to-phase mapping for a *previously unlit* track is not yet solved.
   - **`content.id` allocation on creation is completely unobserved** — no new row was created to
     examine. Whether it is `max+1`, gap-reuse, or something else remains open.
3. **What is still unknown, and needs a further experiment:**
   - **The actual row-creation trigger.** This probe's central task — does opening a track in
     LIGHTING mode create its rows — was not settled, because the one identifiable participant track
     already had a row. A cleaner E1e would need to confirm, in advance, that a specific track has
     **zero** `content` row (checkable now, via this project's own tooling, before the DJ opens it),
     then open only that one track in LIGHTING mode, change nothing, quit, and re-diff.
   - **What happens to a track WITH a pre-existing phrase-level override when its bank changes.**
     This track had none (`macro_id == initial_macro_id` throughout) — whether rekordbox preserves a
     hand-tuned override or blows it away on a bank change is untested.
   - **The phrase_num → phase mapping's true source.** Likely rekordbox's own phrase-kind analysis,
     external to the LightingDB files this project reads — would need either a public spec or a
     dedicated probe correlating `phrase_data.phrase_num` against a track's ANLZ/PSSI phrase-kind data
     if accessible.
   - **Whether rekordbox accepts and plays forged rows at all.** Nothing in this project's read-only
     probes can answer this — per the task's own framing, **only the rig can answer it.** This remains
     the single biggest open question standing between "we can construct a plausible row" and
     "the rig lights up correctly when we push it."

## Anonymisation note

No real track titles, artist names, or comment text appear in this document. Integer IDs
(`content.id`, `song_id`, `macro_id`, `macro_pattern_id`), bank/energy names, and version-field values
are reproduced verbatim — they are schema/rule vocabulary and small integers, not personal data, per
the same standard E1/E1b/E1c applied.

## What to remove later

This is a probe, not shipped code. Nothing permanent depends on it (see
`rekordbox-lighting-architecture`'s `experiments/` contract — the dependency arrow only ever points
inward).

- Delete `src/rbxlight/experiments/e1d_lighting_mode_diff.py` when this verdict is no longer needed
  for reference. `e1_library_join.py` and `e1b_real_denominator.py` are still imported by this probe
  and by `e1c_after_full_analysis.py`; check both before deleting either.
- `work/e1d_before_user.db3` is not reproducible (it captured a specific pre-session state) — keep it
  only as long as this probe or a follow-up E1e might need to re-diff against it; otherwise it is safe
  to delete once this document is considered final, since the document already captures every relevant
  row.
- No new dependencies were added — this probe reuses E1's `experiments` optional-dependency group and
  E1's `work/master.db` copy helper.
- This document and E1/E1b/E1c's documents are the durable record — keep all four even after the code
  is deleted.
