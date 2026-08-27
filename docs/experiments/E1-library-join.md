# E1 — The Library Join

**Status: answered, 2026-08-25.** Bounded, read-only probe. No production code shipped — see "What to remove later" at the end.

Script: `src/rbxlight/experiments/e1_library_join.py` (`pip install -e ".[experiments]"`, then `python -m rbxlight.experiments.e1_library_join`).

Every number below comes from one live run against a real working copy: `work/user.db3` (2966 `content` rows), `work/macro.db3`, and a read-only copy of the live `~/Library/Pioneer/rekordbox/master.db` (7615 `DjmdContent` rows). No database was written. Track titles and artist names are never quoted here — see the anonymisation note at the end.

## Verdict

**Q1 (the join): YES, but stale for most existing rows.** `content.song_id` genuinely *is* `DjmdContent.ID` — the join is semantically real, not a coincidence — but it currently resolves for only **1183 of 2966** `content` rows (39.9%). The other 60.1% reference `song_id` values that no longer exist in the library under that id, split roughly evenly between two failure modes (below), and no alternative column recovers any of them. The join is correct as a *design*; it's stale as *data*, likely because of one or more past library-migration/import events that changed track IDs. New `content` rows created going forward should join cleanly, since they'd be written against the current ID scheme — but historical rows can't be repaired, only detected and skipped.

**Q2 (metadata viability): good where the join succeeds, but that's the minority of the library.** Of the 1183 tracks that DO join: genre is 96.3% populated across 63 distinct genres with a small long tail (usable). BPM and key are 100% populated (very usable). Colour and My Tag are real but thin — colour is essentially unused (1.2%) and repurposed for something unrelated to mood/genre; My Tag covers 23.2% with a rich, DJ-curated vocabulary. Rating is present but 58% are unrated. **Crucially, rekordbox's existing bank assignment shows no meaningful correlation with genre at all** — COOL dominates every one of the top 10 genres (57–88% each), even more concentrated than the library-wide 63.7% COOL baseline. A genre-driven auto-pick would be a *new* signal, not a refinement of an existing one — and it can only be that signal for the ~40% of `content` rows the join actually resolves, plus whatever fraction of the wider library (7615 tracks, of which only 1183 — 15.5% — have ever been sent through lighting analysis at all) gets analysed going forward.

**Design implication:** a genre/title auto-pick heuristic is viable, but it must degrade gracefully — most existing `content` rows (60.1%) and most of the library (84.5%) will not resolve to metadata today, and the feature needs an explicit "join failed, fall back to current behaviour" path rather than assuming every track has genre data.

## Evidence

### Q1 — the join

**10-row sample spanning the full `content.id` range (1..2966), not just the first 10:**

| content.id | song_id | exact `DjmdContent.ID` match |
|---|---|---|
| 1 | 1708 | no |
| 330 | 19458 | no |
| 660 | 86257187 | no |
| 989 | 174573337 | **yes** |
| 1319 | 3775699 | **yes** |
| 1648 | 226629694 | **yes** |
| 1978 | 8299 | no |
| 2307 | 90 | no |
| 2637 | 5060 | no |
| 2966 | 108 | no |

3/10 — consistent with the full-population rate below; the sample deliberately spans the id range rather than clustering near the start.

**Full-population coverage, both directions:**

- Forward: **1183 / 2966** (39.9%) of `content.song_id` values resolve to a live `DjmdContent.ID`.
- Of the 1783 unmatched:
  - **1183** are below `DjmdContent`'s current minimum ID (44138) — small, clearly legacy-scheme integers (e.g. 60, 90, 108, 1708) that predate however the library's IDs are numbered today.
  - **600** fall inside the current ID range but match no live row — i.e. they reference tracks that once existed and have since been removed from the library.
  - **0** are above the current maximum ID.
- Backward: **6432 / 7615** (84.5%) of library tracks have **no** `content` row at all — never sent through lighting analysis, not a join failure.
- Match rate is **not uniform** along `content.id` — it comes in bursts (as low as ~1% in one contiguous band of ~300 rows, as high as ~62% in another), consistent with distinct historical batches of `content` rows written under different ID regimes. `content` carries no timestamp column, so this can't be dated directly — it's supporting texture, not proof of a specific migration event.

**Alternative candidate columns tested** (does anything recover the 1783 unmatched rows?) — none do; `ID` remains the only match:

| candidate column | song_id overlap |
|---|---|
| `ID` (the join used) | 1183 |
| `rb_local_usn` | 0 |
| `usn` | 0 (column is empty in this library instance) |
| `ContentLink` | 0 |
| `TrackNo` | 0 |
| `DJPlayCount` | 0 |
| `FileSize` | 0 |
| `SampleRate` | 0 |
| `BitRate` | 0 |

rekordbox's own historical ID-remap table, `uuidIDMap` (columns: `TableName`, `TargetUUID`, `CurrentID`, `UUID` — literally built for this exact "old id -> new id" problem), is **empty** in this library. Whatever caused the legacy IDs, rekordbox itself no longer has a record of the mapping. The staleness in the 60.1% is not programmatically recoverable.

**Semantic sanity check.** 5 tracks were sampled from across the 1183 matched rows and their `Title` + `Artist` were inspected directly (not reproduced here — see anonymisation note). All 5 resolved to distinct, plausible, real-looking tracks with sensible title/artist pairings — not a coincidental small-integer collision. The probe script exposes this check behind an opt-in `--show-track-samples` flag so it never appears in default output.

**`content.master_db_id` constant (127286662) — does it identify the same library?** Yes, twice over:
- It matches `djmdProperty.DBID` in `master.db` exactly (`127286662`).
- It matches `djmdContent.MasterDBID` on every single `DjmdContent` row.

This confirms the two databases (`user.db3` in LightingDB, `master.db` as the main library) are two views onto the *same* rekordbox library instance — the constant isn't a coincidence or a factory default, it's this specific installation's database identity.

### Q2 — metadata viability (measured over the 1183 tracks that DO join)

**Genre**

- 96.3% populated (1139/1183 non-null, non-empty).
- 63 distinct genres.
- 20 genres have fewer than 5 tracks, covering 42 tracks total (3.6%) — a small, manageable long tail.
- Top 30 genres by track count:

  | genre | tracks | genre | tracks |
  |---|---|---|---|
  | Pop | 142 | Nu-Disco | 19 |
  | Techno | 85 | Carnaval Hoempapa | 18 |
  | Dance | 85 | Carnaval Ballermann | 16 |
  | Eclectic | 84 | Prog-House | 16 |
  | Deep-House | 77 | Carnaval Kirchroa | 15 |
  | Urban | 49 | Hardstyle | 15 |
  | Carnaval Mix | 47 | Disco | 14 |
  | EDM | 34 | Moombahton | 14 |
  | Apres-Ski | 34 | Drum & Bass | 13 |
  | Carnaval Kölle | 32 | X-Mas | 13 |
  | Nederlandstalig | 27 | Carnaval House | 11 |
  | Jump | 27 | Carnaval Polka | 10 |
  | Levenspop | 24 | Happy Hardcore | 10 |
  | Rock | 24 | Country | 10 |
  | Carnaval Mestreech | 22 | | |
  | Carnaval Noord-Limburg | 20 | | |

**Track colour**

- Only **1.2%** (14/1183) of joined tracks have a colour set. Confirmed not a join artifact — across the *whole* library (all 7615 tracks), only **114 (1.5%)** have any colour set at all; colour is simply not part of this DJ's workflow.
- The 8 factory colour slots have been renamed to custom labels unrelated to genre/mood (verbatim, `DjmdColor.Commnt`), with whole-library usage counts:

  | colour slot | display name | whole-library count |
  |---|---|---|
  | 1 | `Overgangsmixen / Pre-mixen` | 25 |
  | 2 | `Ruckerz Music` | 6 |
  | 3 | `Shortcut / Edit` | 0 |
  | 4 | `Keven Le Fonque` | 58 |
  | 5 | `Green` | 0 |
  | 6 | `HIER` | 1 |
  | 7 | `1 drop` | 21 |
  | 8 | `2 drops` | 3 |

  Within the 1183 joined tracks specifically: `1 drop` (12), `2 drops` (2) — the other slots happen not to appear on any currently-joinable track. Colour is a real, usable override channel in principle (per the story's design — DJ hand-labels a track by colour), but as currently used it does not encode a genre/mood taxonomy.

**My Tag**

- 23.2% of joined tracks (275/1183) have at least one My Tag.
- 51 tags defined, organised under 4 top-level categories (`Mood`, `Situation`, `Genres`, `Components`). Full catalogue with joined-track counts, sorted by usage:

  | tag | parent | tracks | tag | parent | tracks |
  |---|---|---|---|---|---|
  | Peaktime | Situation | 122 | Latin | Genres | 6 |
  | Buildup | Situation | 73 | Ballermann | Genres | 4 |
  | Meezingers | Mood | 57 | Club & (Vocal) Trance | Genres | 4 |
  | Party | Mood | 52 | Soul/Disco | Genres | 4 |
  | Fout | Mood | 47 | Afbouw | Situation | 3 |
  | Nederlands | Components | 35 | Kids | Situation | 2 |
  | Begin | Situation | 34 | Style Transition | Components | 2 |
  | Eclectic | Genres | 33 | Classic Rock | Genres | 1 |
  | Duits | Components | 31 | Dansje | Situation | 1 |
  | Pop | Genres | 30 | Schlager/Fox | Genres | 1 |
  | Big Impact | Situation | 28 | Sport | Components | 0 |
  | Feel Good | Mood | 26 | | | |
  | Guilty Pleasure | Mood | 26 | | | |
  | Urban | Genres | 23 | | | |
  | House | Genres | 22 | | | |
  | Geile muziek | Mood | 21 | | | |
  | Hard | Mood | 21 | | | |
  | Apres Ski | Genres | 19 | | | |
  | Background | Situation | 19 | | | |
  | Club vibe | Mood | 19 | | | |
  | Ladies | Mood | 18 | | | |
  | Smartlappen | Mood | 18 | | | |
  | Carnaval | Genres | 17 | | | |
  | Retro | Genres | 17 | | | |
  | Viral | Components | 17 | | | |
  | Dance | Genres | 16 | | | |
  | Laatste kwartier | Situation | 16 | | | |
  | Oldskool | Mood | 16 | | | |
  | Stampen | Mood | 16 | | | |
  | Dance Classics | Mood | 14 | | | |
  | 00s | Mood | 13 | | | |
  | 80s | Mood | 12 | | | |
  | House | Mood | 11 | | | |
  | Moombah/Reggaeton | Genres | 10 | | | |
  | Hardere stijlen | Genres | 9 | | | |
  | Oldies | Genres | 9 | | | |
  | Rock | Genres | 9 | | | |
  | Afterparty | Situation | 8 | | | |
  | 90s | Mood | 7 | | | |

  (The 4 category rows themselves — `Mood`, `Situation`, `Genres`, `Components` — carry 0 direct tracks; they're parents, not tags applied to tracks.)

**Comment**

- 12.7% non-empty (150/1183).
- 10 sample values (these are the literal field contents — no track-identifying text appears in them, so no redaction was needed beyond what's shown):

  ```
  /* Feel Good / Guilty Pleasure / Peaktime / Buildup / House */
  /* Feel Good / Buildup / Peaktime / Eclectic / Latin / Party */
  /* Peaktime */
  /* Buildup / Party / Fout / Feel Good / Ladies */
  /* Geile muziek / Peaktime / Buildup / Eclectic / Latin / Moombah/Reggaeton / Urban / Party */
  /* Geile muziek / Peaktime / Eclectic */
  /* Party / Peaktime */
  /* Buildup / Peaktime / Dance Classics */
  /* Feel Good / Party / Inmix */
  /* Fout */
  ```

  These are **structured, not free-text noise** — every sample is a `/* Tag / Tag / ... */`-formatted list that exactly mirrors My Tag category names. It looks like an export/mirror of My Tag assignments into the comment field (by some external tool or a past workflow), not independent free-text annotation. As a metadata source it's redundant with My Tag, not additive.

**Rating**

Distribution across 1183 joined tracks:

| rating | tracks |
|---|---|
| 0 (unrated) | 690 (58.3%) |
| 1 | 38 |
| 2 | 69 |
| 3 | 95 |
| 4 | 135 |
| 5 | 156 |

**BPM / Key**

- BPM: 100% populated. min 64.7, median 128.5, max 200.0 (a small number of tracks at/near 200 BPM are plausibly double-time-detected, not necessarily wrong — not investigated further, out of scope for this probe).
- Key: 100% populated.

**Cross-tab: top 10 genres × currently-assigned bank**

Bank = `macro_pattern.pattern` only (energy is a separate HIGH/MID/LOW axis and doesn't change the bank name — see `rekordbox-lightingdb-schema` skill). Joined through `content.macro_pattern_id -> macro_pattern.pattern`.

| genre | COOL | CLUB1 | CLUB2 | NATURAL | SUBTLE | HOT | VIVID | WARM | total |
|---|---|---|---|---|---|---|---|---|---|
| Pop | 117 | 1 | 0 | 2 | 11 | 2 | 5 | 4 | 142 |
| Techno | 77 | 6 | 1 | 0 | 0 | 0 | 1 | 0 | 85 |
| Dance | 71 | 4 | 1 | 1 | 2 | 1 | 1 | 4 | 85 |
| Eclectic | 57 | 3 | 0 | 2 | 3 | 7 | 2 | 10 | 84 |
| Deep-House | 53 | 11 | 5 | 0 | 2 | 1 | 1 | 4 | 77 |
| Urban | 38 | 1 | 0 | 0 | 0 | 4 | 3 | 3 | 49 |
| Carnaval Mix | 35 | 3 | 2 | 5 | 0 | 0 | 2 | 0 | 47 |
| EDM | 28 | 4 | 0 | 0 | 0 | 1 | 1 | 0 | 34 |
| Apres-Ski | 21 | 1 | 0 | 4 | 3 | 0 | 4 | 1 | 34 |
| Carnaval Kölle | 28 | 0 | 0 | 1 | 0 | 0 | 2 | 1 | 32 |

Overall across these 675 top-10-genre tracks: **COOL 525 (78.5%)**, CLUB1 34 (5.1%), WARM 27 (4.0%), VIVID 22 (3.3%), SUBTLE 21 (3.1%), HOT 16 (2.4%), NATURAL 15 (2.2%), CLUB2 9 (1.3%).

**Plainly: rekordbox's existing bank assignment does not track genre.** COOL is the overwhelming majority bank in *every single one* of the top 10 genres, ranging from 61.8% (Apres-Ski, the lowest) to 90.6% (Techno, the highest) — never dropping much below two-thirds. The top-10-genre COOL rate overall (78.5%) is in fact *higher* than the library-wide COOL baseline (63.7%, from the story's context), meaning if anything popular genres skew slightly more toward the default, not less. There is no genre for which a non-COOL bank dominates. This reads as a default/fallback value, not a genre-informed choice — which means a genre-driven auto-pick would be introducing a new signal, not refining an existing one.

## Anonymisation note

No real track titles, artist names, or comment text that could identify a person appear in this document. Where the procedure required inspecting real titles/artists (the Q1 semantic sanity check), the result is reported as a pass/fail judgement only; the actual values were viewed via the probe script's `--show-track-samples` flag, which is opt-in and off by default precisely so this data doesn't end up in logs, screenshots, or this repo. Genre names, colour display names, and My Tag names are reproduced verbatim per the task's requirements — they are the rule vocabulary, not personal data.

## What to remove later

This is a probe, not shipped code. Nothing permanent depends on it (see `rekordbox-lighting-architecture`'s `experiments/` contract — the dependency arrow only ever points inward). When this verdict is no longer needed for reference:

- Delete `src/rbxlight/experiments/e1_library_join.py` and, if no other probe is using it, `src/rbxlight/experiments/__init__.py` and the now-empty `experiments/` directory.
- Remove the `experiments` optional-dependency group from `pyproject.toml` (`pyrekordbox`, `sqlcipher3-wheels`) — nothing else in the codebase uses it.
- `work/master.db` (the read-only copy this script made) is already gitignored (covered by the existing `work/` entry) and can be deleted from the local working copy at will; it is never referenced by anything else.
- This document (`docs/experiments/E1-library-join.md`) and the `master.db` section added to the `rekordbox-data-safety` skill are the durable record — keep those even after the code is deleted, the same way the ninth-bank probe's code was deleted but its rule survived in the schema skill.
