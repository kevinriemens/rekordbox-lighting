---
name: rekordbox-lightingdb-schema
description: Schema of rekordbox 6 LightingDB (macro.db3, user.db3), the LightingEditModel XML macro format, and how content/phrase_data relate to rekordbox's main library and a track's own ANLZ analysis (track identity, phrase-to-phase mapping, row-creation semantics, PSSI). Use when reading, generating, or transforming macros, venues, fixtures, phrase assignments, or anything joining to a track's identity/analysis data.
metadata:
  skill-type: domain-reference
  language: python
  project-type: data-tool
---

# rekordbox LightingDB Schema

Any code that opens these files MUST also load `rekordbox-data-safety` — this skill is domain knowledge only, it carries no safety rules.

You are the domain reference for rekordbox 6's LightingDB: the SQLite schema and the `LightingEditModel` XML macro format. A developer should be able to write a correct macro payload, or a correct row in any of these tables, from this document alone — without opening a database browser.

## Files

| file | size | role |
|---|---|---|
| `macro.db3` | ~9.8M | macro library — factory + user macros, fixture slots, patterns/assign (READ/WRITE target) |
| `user.db3` | ~13M | venues, fixture patches, per-track phrase assignments (READ/WRITE target) |
| `master.db3` | ~512M | factory fixture-profile library (READ-ONLY, never touch) |
| `macro_old.db3` / `master_old.db3` | — | rekordbox's own rolling backups — not yours, do not rely on them |

Located at `~/Library/Application Support/Pioneer/rekordbox6/LightingDB/`. All three are **plain unencrypted SQLite 3** — no SQLCipher, no app-level encryption. Standard `sqlite3` / ElementTree tooling works directly.

## macro.db3 tables

```sql
CREATE TABLE macro (
  id        INTEGER PRIMARY KEY,
  name      TEXT,
  beats     INTEGER,   -- macro length; defines the x-axis domain of every Point/Block in its payloads
  fixed     INTEGER,
  thumbnail TEXT,       -- filename string, not a blob
  preset    INTEGER,    -- 1 = factory, 0 = user
  enabled   INTEGER
);

CREATE TABLE macro_data (
  id               INTEGER PRIMARY KEY,
  macro_id         INTEGER,
  macro_fixture_id INTEGER,  -- FK -> macro_fixture.id, one of the 25 slots
  data             TEXT      -- LightingEditModel XML string, may be empty string ""
);

CREATE TABLE macro_fixture (
  id              INTEGER PRIMARY KEY,
  name            TEXT,
  fixture_type_id INTEGER   -- see "The 25 fixture slots" below
);

CREATE TABLE macro_pattern (
  id      INTEGER PRIMARY KEY,
  energy  INTEGER,  -- 1=HIGH, 2=MID, 3=LOW
  pattern INTEGER   -- 1..8, or 99 (INTERLUDE)
);

CREATE TABLE macro_assign (
  macro_pattern_id INTEGER,
  phase            INTEGER,  -- range depends on energy, see below
  macro_id         INTEGER,
  initial_macro_id INTEGER,
  PRIMARY KEY (macro_pattern_id, phase)
);

CREATE TABLE macro_event (
  macro_data_id INTEGER,
  kind          INTEGER,
  beat_num      INTEGER,
  sequence_num  INTEGER,
  value1        INTEGER,
  interval      INTEGER,
  value2        INTEGER
);
-- 0 rows in the live library. Unused by rekordbox 6. Do not write to it.
```

### `macro` preset / id-range convention

| range | preset | meaning |
|---|---|---|
| `id = -1` | 1 | factory |
| `id 1..916` | 1 | factory macro library |
| `id = 10000` | 1 | `SEPARATOR` — a marker row, not a usable macro |
| `id >= 10001` | 0 | user macros (currently 6: `10001..10006`) |

Never modify a `preset=1` row. New/edited macros always get the next free `id >= 10001` with `preset=0`.

- `thumbnail` is a filename string (e.g. factory macros reference their own preview images); **user macros always use `USER_SCENE.png`**.
- `beats` is the macro's length in beats and is the domain for every `x` coordinate in that macro's `macro_data` payloads — a Point with `x=32.0` in a `beats=32` macro sits at the very end.

## The 25 fixture slots

`macro_fixture` has exactly 25 rows — fixed, factory-defined virtual slots. Every macro has exactly one `macro_data` row per slot (25 total).

| id | name | fixture_type_id |
|---|---|---|
| 1 | Par Light 1 | 1 |
| 2 | Par Light 2 | 1 |
| 3 | Par Light 3 | 1 |
| 4 | Par Light 4 | 1 |
| 5 | Bar Light 1 | 2 |
| 6 | Bar Light 2 | 2 |
| 7 | Bar Light 3 | 2 |
| 8 | Bar Light 4 | 2 |
| 9 | Bar Light 5 | 2 |
| 10 | Bar Light 6 | 2 |
| 11 | Moving Head 1 | 3 |
| 12 | Moving Head 2 | 3 |
| 13 | Moving Head 3 | 3 |
| 14 | Moving Head 4 | 3 |
| 15 | Strobe | 4 |
| 16 | Mirrorball Spot | 5 |
| 17 | Effect 1 | 8 |
| 18 | Effect 2 | 8 |
| 19 | Laser | 9 |
| 101 | Par Light 1 (Simple) | 101 |
| 102 | Par Light 2 (Simple) | 101 |
| 105 | Bar Light 1 (Simple) | 102 |
| 106 | Bar Light 2 (Simple) | 102 |
| 111 | Moving Head 1 (Simple) | 103 |
| 112 | Moving Head 2 (Simple) | 103 |

Note `macro_fixture.id` is NOT contiguous 1..25 — the Simple slots use the 101/102/105/106/111/112 range. Always join on `id`, never assume position.

### Which XML sections each `fixture_type_id` supports (critical)

| fixture_type_id | fixture kind | Brightness | Colour | Strobe | Position | Rotate | Gobo |
|---|---|---|---|---|---|---|---|
| t1, t2, t4, t5, t8, t9 | Par, Bar, Strobe, Mirrorball, Effect, Laser | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| t3, t103 | Moving Head, Moving Head (Simple) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| t101, t102 | Par (Simple), Bar (Simple) | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |

**Writing a Position, Rotate, or Gobo section to a slot whose `fixture_type_id` doesn't support it is an invalid payload** — Simple Par/Bar slots (t101/t102) have no pan/tilt/rotation hardware behind them, and only Moving Head types (t3/t103) have a gobo wheel. Emit only the sections that type supports; still emit them as empty self-closing tags if the macro genuinely has no data for that section on a type that DOES support it (see next section).

## LightingEditModel XML

This is the `macro_data.data` payload — one per `macro_data` row, one per fixture slot.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<LightingEditModel ver="1.0">
  <Brightness>
    <PointBlock xleft="0.0" xright="32.0">
      <Point x="0.0"  y="0.0" type="1"/>
      <Point x="3.98" y="1.0" type="2"/>
      <Point x="32.0" y="1.0" type="3"/>
    </PointBlock>
  </Brightness>
  <Colour>
    <ColourBlock xleft="0.0" colourleft="-16401672" xright="32.0" colourright="-3277311"/>
  </Colour>
  <Strobe>
    <StrobeBlock xleft="" strobeleft="" xright="" stroberight=""/>
  </Strobe>
  <Position>
    <MovementBlock xleft="0.0" xright="32.0" pattern="Circle" width="0.5" height="0.5"
      offset_x="0.5" offset_y="0.5" round_angle="0" offset_angle="0" start_angle="0"
      period_time="20000" frequency_x="2" frequency_y="3" phase_x="90" phase_y="0"
      type="Loop" direction="Forward" relative="0"/>
  </Position>
  <Rotate>
    <RotateBlock xleft="0.0" rotateleft="0" xright="32.0" rotateright="360"/>
  </Rotate>
  <Gobo/>
</LightingEditModel>
```

### Element / attribute inventory

| element | attributes |
|---|---|
| `LightingEditModel` | `ver="1.0"` |
| `PointBlock` | `xleft`, `xright` |
| `Point` | `x`, `y`, `type` |
| `ColourBlock` | `xleft`, `colourleft`, `xright`, `colourright` |
| `StrobeBlock` | `xleft`, `strobeleft`, `xright`, `stroberight` |
| `RotateBlock` | `xleft`, `rotateleft`, `xright`, `rotateright` |
| `MovementBlock` | `xleft`, `xright`, `pattern`, `width`, `height`, `offset_x`, `offset_y`, `round_angle`, `offset_angle`, `start_angle`, `period_time`, `frequency_x`, `frequency_y`, `phase_x`, `phase_y`, `type`, `direction`, `relative` (18 attrs) |

### `Point@type` semantics (verified across 4706 parseable payloads)

| type | meaning | cardinality per `PointBlock` |
|---|---|---|
| `1` | block start | exactly one |
| `2` | interior point | zero or more (67330 total observed) |
| `3` | block end | exactly one |

- `x` = beat position, domain `0..macro.beats` for that macro.
- `y` = normalized brightness, `0.0..1.0`.
- A `PointBlock` with no interior points is still valid: just a `type=1` point followed by a `type=3` point.

### Section order is fixed

Documents always emit sections in this order, regardless of which are populated:

```
Brightness, Colour, Strobe, Position, Rotate, Gobo
```

A section with no data is **not omitted** — it's a self-closing empty tag (`<Strobe/>`, `<Gobo/>`, or a block element with empty string attributes like `<StrobeBlock xleft="" strobeleft="" xright="" stroberight=""/>`). Serializers must always emit all sections supported by that slot's `fixture_type_id`, populated or not — see the support table above for which sections a given slot even has.

### Colour encoding

Colours are **signed int32 ARGB, Java style** (two's-complement, alpha implicitly `0xFF`). Convert both ways:

```python
def argb_to_signed(a: int, r: int, g: int, b: int) -> int:
    val = (a << 24) | (r << 16) | (g << 8) | b
    return val - 0x100000000 if val >= 0x80000000 else val


def signed_to_argb(n: int) -> tuple[int, int, int, int]:
    u = n & 0xFFFFFFFF
    return (u >> 24) & 0xFF, (u >> 16) & 0xFF, (u >> 8) & 0xFF, u & 0xFF
```

Common values observed in the library:

| signed int32 | hex | colour |
|---|---|---|
| `-65536` | `#FFFF0000` | red |
| `-16776961` | `#FF0000FF` | blue |
| `-65281` | `#FFFF00FF` | magenta |
| `-16711936` | `#FF00FF00` | green |
| `-256` | `#FFFFFF00` | yellow |
| `-32768` | `#FFFF8000` | orange |
| `-1` | `#FFFFFFFF` | white |
| `-16777216` | `#FF000000` | black |

### `MovementBlock` enums and observed distributions

Only present under `<Position>`, only meaningful on types that support Position (see support table).

- `pattern` ∈ `Circle` (1528 obs.), `Line2` (370), `Line` (142), `Square` (108), `SquareChoppy` (8), `Lissajous` (2), `Leaf` (1), `Diamond` (1) — `Circle` is overwhelmingly the default choice.
- `type` ∈ `Loop`, `PingPong`
- `direction` ∈ `Forward`, `Backward`
- Near-constant across the library — safe defaults if generating new payloads: `frequency_x=2`, `frequency_y=3`, `phase_x=90`, `phase_y=0`, `round_angle=0`.
- `period_time` is in **milliseconds**; common values: `20000`, `10000`, `8000`, `6000`, `5000` (also seen: `14000`).

## user.db3 tables

```sql
CREATE TABLE venue (
  id      INTEGER PRIMARY KEY,
  name    TEXT,
  "order" INTEGER,
  enabled INTEGER
);

CREATE TABLE fixture (
  id                INTEGER PRIMARY KEY,
  name              TEXT,
  venue_id          INTEGER,
  fixture_master_id INTEGER,  -- FK -> master.db3 factory fixture profile
  mode_num          INTEGER,  -- DMX personality/mode of that profile
  macro_fixture_id  INTEGER,  -- FK -> macro_fixture.id (which of the 25 slots this fixture inherits its show from)
  universe_num      INTEGER,
  start_addr        INTEGER,  -- DMX start channel
  color_num         INTEGER,
  "order"           INTEGER,
  offset_x          INTEGER,
  offset_y          INTEGER,
  limit_min_x       INTEGER,
  limit_max_x       INTEGER,
  limit_min_y       INTEGER,
  limit_max_y       INTEGER,
  tilt_reversal     INTEGER
);

CREATE TABLE content (
  id               INTEGER PRIMARY KEY,
  song_id          INTEGER,
  master_db_id     INTEGER,
  macro_pattern_id INTEGER   -- FK -> macro_pattern.id
);

CREATE TABLE phrase_data (
  content_id       INTEGER,
  phrase_num       INTEGER,  -- observed 1..99
  macro_id         INTEGER,
  initial_macro_id INTEGER,
  PRIMARY KEY (content_id, phrase_num)
);

CREATE TABLE lighting_data (
  id         INTEGER PRIMARY KEY,
  content_id INTEGER,
  fixture_id INTEGER,
  data       TEXT   -- per-track, per-fixture custom override
);

CREATE TABLE direct_control (
  button_num           INTEGER,
  name                 TEXT,
  venue_id             INTEGER,
  dmx_ch               INTEGER,
  value_on             INTEGER,
  value_off            INTEGER,
  enable_auto_on       INTEGER,
  enable_with_blackout INTEGER,
  enable_knob          INTEGER,
  note_text            TEXT
);

CREATE TABLE lighting_property (
  key   TEXT PRIMARY KEY,
  value TEXT
);
```

### How macros get selected for a track

1. `content.macro_pattern_id` selects one of the 27 rows in `macro_pattern` for that track. `macro_pattern = energy(1..3) × style(1..8, 99)` — 3 × 9 = 27 rows total.

   **Bank names, in `pattern` order** (E1e; never stored as a column anywhere in the schema — the only place a name appears at all is the trailing token of a factory macro name, e.g. `HIGH CHORUS1 COOL`):

   | `pattern` | bank name |
   |---|---|
   | 1 | COOL |
   | 2 | NATURAL |
   | 3 | HOT |
   | 4 | SUBTLE |
   | 5 | WARM |
   | 6 | VIVID |
   | 7 | CLUB1 |
   | 8 | CLUB2 |
   | 99 | INTERLUDE — not user-selectable, see the ninth-bank section below |

   **Identity is `(energy, pattern)`, not `macro_pattern.id` alone** — `id` is just a surrogate key over that pair; don't hardcode an `id ↔ bank name` mapping without also checking `energy`/`pattern` on the row.
2. `macro_assign(macro_pattern_id, phase, macro_id, initial_macro_id)` maps `(pattern, phase)` → a concrete `macro_id`. **The number of phases is NOT uniform, and it is NOT derivable from `energy` alone.** Measured live total: **232 rows**, not 27 × 11.

   Measured per-row phase counts (`macro_pattern.id` → count):

   | pattern | energy 1 (HIGH) | energy 2 (MID) | energy 3 (LOW) |
   |---|---|---|---|
   | 1..6 (COOL, NATURAL, HOT, SUBTLE, WARM, VIVID) | **11** | 10 | 6 |
   | 7, 8 (CLUB1, CLUB2) | **10** | 10 | 6 |
   | 99 (INTERLUDE) | 6 | 6 | 6 |

   Check: `6×(11+10+6) + 2×(10+10+6) + 3×6 = 162 + 52 + 18 = 232`. ✔

   **Never compute a phase count — read it.** `SELECT COUNT(*) FROM macro_assign WHERE macro_pattern_id = ?`, or copy the source row set wholesale. Any code that derives the upper bound from a formula will be wrong for the two CLUB banks.

   *(Corrected 2026-08-23: this section previously documented a uniform `1..11`. **Corrected again 2026-08-25** — the 2026-08-23 fix replaced one formula with another, claiming energy alone determines the count, i.e. "11 phases for energy 1". That is wrong for patterns 7 and 8, which have 10 at HIGH. Re-verified 2026-08-25 by direct query. The lesson the two corrections share: this column has no rule, only data.)*
3. `phrase_data(content_id, phrase_num, macro_id, initial_macro_id)` is the **per-track override** layer, keyed by `(content_id, phrase_num)`. `phrase_num` observed range is `1..99`. This is what actually fires during playback for a given phrase of a given track — it starts as a copy of the pattern/phase assignment but can be hand-edited per track.

   ⚠️ **`phrase_data` is user work and must never be clobbered.** Because it is the layer that actually fires, it also *shadows* `macro_assign`: changing a bank's assignment does not necessarily change what an already-analyzed track plays. Any feature that rewrites `macro_assign` must treat existing `phrase_data` rows as authoritative and leave them alone, and must be honest that its effect on already-analyzed tracks is not guaranteed.

   **Update (E1d/E1d2, 2026-08-26) — partially resolved.** Changing a track's bank through rekordbox's own LIGHTING mode editor DOES rewrite that track's `phrase_data` wholesale from the new bank's `macro_assign` — verified twice, on two different tracks, 100% value-level match both times. See "A bank change in the rekordbox UI rewrites `phrase_data`" below for the mechanism and what's still an open question (an external write to `content.macro_pattern_id` alone, bypassing the UI, has NOT been shown to have the same effect — treat that as unproven, not as confirmed).

## Track identity: `content.song_id` vs `DjmdContent.ID` (master.db)

This section, and everything under it down to "Analysis Lock", consolidates the E-series probes
(`docs/experiments/E1*.md`) — the durable findings live here; the reports hold the raw measurements,
denominators, and methodology for anyone who wants to verify a number.

`content.song_id` **is** `DjmdContent.ID`, by design, not coincidence — proven via
`content.master_db_id` (a constant, `127286662`, on every row) matching both `djmdProperty.DBID` and
`djmdContent.MasterDBID` in `master.db` (see the `rekordbox-data-safety` skill for `master.db`'s
read-only-copy rules). But as of 2026-08-26, **1,783 of 2,966 `content` rows (60.1%) carry `song_id`
values that do not resolve to any current `DjmdContent.ID`** — split roughly evenly between
sub-`DjmdContent`-minimum legacy IDs and in-range-but-since-removed IDs
([E1](../../docs/experiments/E1-library-join.md)). rekordbox's own id-remap table (`uuidIDMap`) is
empty in this library — the staleness is not programmatically recoverable by ID
([E1](../../docs/experiments/E1-library-join.md), confirmed unchanged in
[E1c](../../docs/experiments/E1c-after-full-analysis.md) and
[E1d2](../../docs/experiments/E1d2-row-creation-rerun.md)).

**This measures ID resolvability, not lighting absence — do not conflate the two.**
`song_id not in content.song_id` reads as "this track has never been lit," but
[E1d2](../../docs/experiments/E1d2-row-creation-rerun.md) proved that reading false, directly: a track
the DJ had just changed the bank of, live, in rekordbox's own UI, was certified "absent" by exactly
this check, twice — because its `content` row (`id=1576`) carried the stale `song_id=5800`, while the
track's *current* `DjmdContent.ID` is `62464681`. **Every coverage percentage this project has
published — E1's 39.9% forward-join, E1b's 22.6%/30.4% playlist/history join, E1c's re-measurement —
measures ID-equality resolvability, not whether a track has ever been lit.** The true
lighting-coverage fraction is higher than any published figure, by an amount this project cannot yet
measure.

### The fingerprint bridge — recovering identity without a resolvable ID

Because ID lookup cannot find a stale row, [E1d2](../../docs/experiments/E1d2-row-creation-rerun.md)
established a content-only alternative: a track's ANLZ `PSSI` phrase *kinds* predict its
`phrase_data` phase sequence under a given `macro_pattern_id` (via the subkind table further down this
section), and that predicted sequence — plus the track's own row count — narrows a same-bank
population of 53–70 candidate `content` rows down to exactly one, for 5 of 7 tested tracks. **It found
nothing for the other 2 of 7** — a real, reported gap, most plausibly PSSI/`phrase_data` drift (see
"ANLZ PSSI" below) or a subkind-table gap, not resolved by that probe. Use the fingerprint bridge to
validate or reconcile a UI-visible bank against a stale-ID row — it is not a guaranteed-always-succeeds
recovery tool.

## Row creation semantics

- `content.id` allocation is dense and sequential — max observed was exactly 2,966 of 2,966 rows
  ([E1c](../../docs/experiments/E1c-after-full-analysis.md)), later exactly 2,972 of 2,972 after 6 new
  rows in one session ([E1d2](../../docs/experiments/E1d2-row-creation-rerun.md)). No gap-reuse
  observed.
- Opening a track in rekordbox's **LIGHTING mode editor** (not merely selecting or previewing it) is
  what creates its `content`/`phrase_data` rows. Ordinary EXPORT-mode phrase analysis does **not**
  touch this table at all — see "Analysis pass ≠ LightingDB write" below.
  [E1d2](../../docs/experiments/E1d2-row-creation-rerun.md) confirmed one genuinely-new row this way:
  `content_id=2972`, bank `macro_pattern_id=7` — **COOL/MID is a freshly-lit track's default bank**,
  not `macro_pattern_id=0` — with a full 28-row `phrase_data` set.
- Incidental browser/preview activity (track selection, waveform hover — the exact trigger was not
  isolated) creates **orphan stubs**: `content` rows with `macro_pattern_id=0` and **zero**
  `phrase_data` rows.
  [E1d2](../../docs/experiments/E1d2-row-creation-rerun.md) watched 5 appear in one session — this is
  the explanation for the library's long-standing population of 61 `macro_pattern_id=0` orphans (see
  the ninth-bank section below, whose text previously called their origin unexplained — it no longer
  is).
- On creation, `macro_id == initial_macro_id` on every `phrase_data` row — a freshly-lit track has no
  phrase-level override yet, by definition
  ([E1d](../../docs/experiments/E1d-lighting-mode-row-creation.md),
  [E1e](../../docs/experiments/E1e-phrase-phase-mapping.md),
  [E1d2](../../docs/experiments/E1d2-row-creation-rerun.md)).
- `content_id=2972` is **ground truth**, not back-derived: E1e's `(kind, k1, k2, k3, b) → phase` table
  (below) predicted its full 28-phrase sequence, and rekordbox's own write matched it **28/28**
  exactly — the first validation of that table against a row rekordbox itself wrote during the probe,
  rather than a row that already existed.

### Analysis pass ≠ LightingDB write

A full-library EXPORT-mode phrase-analysis pass (running rekordbox's own "analyse track" over the
whole collection) leaves `content` **byte-for-byte unchanged** — same row count, same join rate, same
sampled row values, confirmed by direct diff, not aggregate comparison
([E1c](../../docs/experiments/E1c-after-full-analysis.md)). Only actually opening a track in the
LIGHTING mode editor creates rows (previous bullet). Do not assume "the DJ ran analysis on the library"
grew lighting coverage — it doesn't, by itself.

## ANLZ `PSSI` — part of the schema surface, reached via `master.db`

A track's phrase-kind analysis lives outside `user.db3`/`macro.db3` entirely, in its own ANLZ `.EXT`
analysis-cache file, reached via `DjmdContent.AnalysisDataPath` (in `master.db` — read-only, see the
`rekordbox-data-safety` skill) → parse the `PSSI` tag (`pyrekordbox`'s `AnlzFile.parse_file`, scanning
for tag type `PSSI`).

Per phrase entry: `index` (1-based ordinal position — matches `phrase_data.phrase_num` directly on
90.0% of checked tracks), `kind` (integer 1–10 observed), and four sub-flags `k1`/`k2`/`k3`/`b` that
disambiguate cases where `kind` alone would collapse genuinely distinct phases. Struct-level (not
per-entry) fields: `mood` (High=1/Mid=2/Low=3, documented in `pyrekordbox` itself) matches
`macro_pattern.energy` on 1,101/1,123 checked tracks (98.0%) — **rekordbox's own energy verdict is read
from its own phrase analysis, not guessed**; `bank` is a mostly-zero (98.9% of tracks) byte with no
meaning established by any probe; `u1..u5` are always zero across 500 sampled tracks (confirmed unused
padding, not signal this project missed); `len_entries` matches `phrase_data` row count on only 90.0%
of checked tracks — the other 10% shows a track's on-disk musical analysis and its stored lighting
programme can drift apart over time (most plausibly: re-analysed after its lighting programme was
written). All figures: [E1e](../../docs/experiments/E1e-phrase-phase-mapping.md).

**38.7% of currently-lit tracks have no readable ANLZ file at all**
([E1e](../../docs/experiments/E1e-phrase-phase-mapping.md)) — a hard blocker for any phrase-kind-based
derivation on those tracks, not a rare edge case to plan around.

## Phrase → phase: NOT ordinal, but a stable per-bank subkind lookup

**`phrase_num → phase` is refuted outright.** 0 of 120 `(macro_pattern_id, track-phrase-count)` groups
with ≥5 tracks produced a single consistent sequence; even in the narrowest, most favourable case — a
track's phrase count exactly equal to its bank's phase count (210 of 2,890 non-override tracks) — the
naive identity mapping (`phrase_num == phase`) matched **0/210** tracks
([E1e](../../docs/experiments/E1e-phrase-phase-mapping.md)). **Do not derive phase from a phrase's
ordinal position.**

**The real key is `(kind, k1, k2, k3, b) → phase`, a stable table per `macro_pattern_id`.** Validated
against 13,197 of 41,742 existing `phrase_data` rows (1,011 tracks, spanning 19 of 27 active
`macro_pattern_id`s): 165 of 200 distinct subkind keys (82.5%) are 100% consistent, and weighted by row
count, 13,111/13,197 rows (99.35%) agree with their key's majority phase
([E1e](../../docs/experiments/E1e-phrase-phase-mapping.md)). 5 rare bank combinations
(`macro_pattern_id` 15/16/17/23/24 — HOT/SUBTLE/WARM/CLUB1/CLUB2 at LOW energy) have zero
PSSI-readable representatives in the current population and are **not directly validated** — small
natural samples, not evidence of a different mechanism.

The forward direction — forging: `(kind, k1, k2, k3, b) → phase → macro_assign(macro_pattern_id,
phase) → macro_id` — is always unambiguous by construction, since `macro_assign`'s primary key is
`(macro_pattern_id, phase)`. The reverse direction (`macro_id → phase`, used only to validate existing
rows against history) is ambiguous for 3.94% of rows, confined to exactly 4 banks (CLUB1/CLUB2 at
HIGH/MID, `macro_pattern_id` 19–22) that legitimately duplicate a macro_id across adjacent phases —
this is a validation-methodology artifact, not a forging blocker
([E1e](../../docs/experiments/E1e-phrase-phase-mapping.md)).

**Representative table — `macro_pattern_id=1` (COOL/HIGH, 11 phases, the highest-volume bank in the
library, 1,159 of 2,966 `content` rows):**

| kind | k1 | k2 | k3 | b | → phase | n_obs | consistency |
|---|---|---|---|---|---|---|---|
| 1 | 0 | 0 | 0 | 0 | 2 | 432 | 100.0% |
| 1 | 1 | 0 | 0 | 0 | 1 | 142 | 100.0% |
| 2 | 0 | 0 | 0 | 0 | 3 | 1,218 | 99.4% |
| 2 | 0 | 0 | 1 | 0 | 4 | 222 | 98.6% |
| 2 | 0 | 1 | 0 | 0 | 5 | 202 | 99.5% |
| 2 | 0 | 1 | 0 | 1 | 5 | 309 | 99.0% |
| 3 | 0 | 0 | 0 | 0 | 8 | 721 | 99.3% |
| 5 | 0 | 0 | 0 | 0 | 7 | 326 | 98.8% |
| 5 | 1 | 0 | 0 | 0 | 6 | 2,400 | 99.8% |
| 6 | 0 | 0 | 0 | 0 | 10 | 192 | 98.4% |
| 6 | 1 | 0 | 0 | 0 | 9 | 336 | 99.7% |

(A handful of single/low-digit-`n_obs` outlier keys exist for this bank too — see the source report for
the full, unrounded table.)

**The other 18 validated banks' full subkind tables (`macro_pattern_id` 2–14, 18–22) are not
reproduced here** — read them directly from
[E1e — The Phrase→Phase Mapping](../../docs/experiments/E1e-phrase-phase-mapping.md#the-complete-subkind--phase-table),
which is the intended lookup table for Stage 1/Stage 3 forging code to be built directly against, not
merely illustrative.

## A bank change in the rekordbox UI rewrites `phrase_data`

Changing an already-lit track's bank through rekordbox's own LIGHTING mode editor rewrites **every one**
of that track's `phrase_data.macro_id`/`initial_macro_id` values, drawn wholesale from the new bank's
`macro_assign` — verified twice, on two different tracks, 100% value-level match both times
([E1d](../../docs/experiments/E1d-lighting-mode-row-creation.md),
[E1d2](../../docs/experiments/E1d2-row-creation-rerun.md)). This is what the earlier "not yet
established" note above referred to — it is now established **for a rekordbox-driven UI edit**.

**Open question, not a conclusion — flagged explicitly, not upgraded to fact:** whether an *external*
write to `content.macro_pattern_id` alone (bypassing the UI) has the same effect on `phrase_data`. It
almost certainly will not — `phrase_data` is a separate table and no trigger mechanism has been
observed — so **anything that writes `content.macro_pattern_id` directly must plan to rebuild
`phrase_data` itself**, rather than assume rekordbox will do it on the next launch. This is exactly the
question a future E2-style probe against the physical rig is meant to settle; nothing in this project's
read-only probes can answer it.

**Also open:** what happens to a track WITH a pre-existing phrase-level override when its bank
changes — every track examined so far had `macro_id == initial_macro_id` throughout, so this is
untested ([E1d](../../docs/experiments/E1d-lighting-mode-row-creation.md)).

## No transition layer exists

Phrase-to-phase is a hard cut — `phrase_data` selects one whole macro per phrase, nothing blends
across the boundary, and there is no dedicated transition mechanism anywhere in the schema. What can
look like a transition is tail content authored inside a macro itself:
[E1d2](../../docs/experiments/E1d2-row-creation-rerun.md) traced one DJ-perceived "transition" to a
macro's own brightness dips/flashes in its final third, immediately before the hard cut to the next
phrase's macro — not a distinct mechanism. `macro_event` remains 0 rows, confirming this skill's
existing note above that it's unused. Worth stating explicitly: the absence of a transition layer is
otherwise easy to mistake for a gap in this project's understanding rather than a fact about rekordbox
itself. A future stage wanting an actual crossfade between phrase macros would be building new
functionality, not extracting one that already exists.

## Analysis Lock (`master.db`)

`djmdContent.Analysed` takes exactly two observed values: `105` (unlocked) and `233` (locked — a
single bit set, `233 − 105 = 128`), set by hand in rekordbox's own UI. **36 of 7,615 tracks (0.47%)
are locked** ([E1d2](../../docs/experiments/E1d2-row-creation-rerun.md)). Locked tracks are excluded
from bulk re-analysis — any plan that says "re-analyse to regenerate missing ANLZ/PSSI data" must
detect and report the tracks it cannot touch, rather than assume success. The overlap with the
no-readable-ANLZ population (38.7% of lit tracks, above) is small: only 1 of the 36 locked tracks also
lacks readable PSSI — the two are largely separate populations, and Analysis Lock does not explain
most of the 38.7% gap.

### `lighting_property` known keys

| key | example value | meaning |
|---|---|---|
| `ExecVenueId` | `2` | currently active venue |
| `LastSelectedVenue` | `2` | last venue selected in UI |
| `MacroVersionNum` | `1061` | schema/content version of macro library |
| `DbVersionNum` | `1854` | schema/content version of user db |
| `AsyncLastMacroId` | — | last macro id touched by async operation |

Current max `venue.id` in the live library = **3**. New venues get `id = 4`.

### Is a ninth bank (`pattern = 9`) possible? — ANSWERED: NO (2026-08-25)

`macro_pattern.pattern` takes values `1..8` (the eight named banks) plus `99` (INTERLUDE).
**A ninth bank is not usable. Do not attempt one, and do not reopen this.**

**Tested directly against the live database on 2026-08-25.** A probe bank `(id=28, energy=1,
pattern=9)` plus 10 `macro_assign` rows cloned from bank 19 (CLUB1 HIGH, existing factory macros, so
macro content was held constant and the pattern integer was the only variable) was pushed to live. No
track was repointed — `content` was never written. rekordbox was launched, inspected, and quit.

**Result — two distinct findings, both load-bearing:**

1. **The bank is invisible. This is the blocking one.** It appeared nowhere: not in performance mode,
   not in macro mapping mode. Only the eight regular banks showed. The mood/bank selector is a fixed
   8-button surface, so an unknown `pattern` value has no way in and cannot be selected or assigned by
   hand. This is independent of the missing name: there is **no name column anywhere** (bank names
   exist only as the trailing token of factory macro names — `HIGH CHORUS1 COOL`, `CHORUS CLUB1`), so
   a ninth bank has no label source either.

2. **It was NOT pruned — the row survived untouched.** The backup taken immediately before the revert
   (a snapshot of live *after* rekordbox had read it) still held row 28 with all 10 `macro_assign`
   rows, phases 1–10, `macro_id`s byte-identical to the source. `MacroVersionNum` (1061) and
   `DbVersionNum` (1854) were unchanged. rekordbox did not reject, rewrite, renumber, or repair
   anything.

**The reusable rule: storage tolerates unknown rows; the UI is the hard limit.** rekordbox ignores
what it does not recognise rather than repairing it. This matches the 61 `content` rows pointing at
`macro_pattern_id = 0` (a pattern that has never existed), which have always survived. So when
planning bank or venue work, the risk to test is whether rekordbox will *display* a thing — not
whether the data will *survive*, which it does.

*(Their origin was unexplained when this section was written. E1d2 later found the mechanism —
incidental browser/preview activity creates exactly this shape of orphan row: `macro_pattern_id=0`,
zero `phrase_data`. See "Row creation semantics" above.)*

Nothing looked broken at any point, and the DB was restored to baseline afterwards (27 patterns, 232
`macro_assign` rows, the 61 pre-existing orphans unchanged). The probe tooling was disposable and has
been deleted; `macros/patterns.py` and `phrases/repo.py`, which it was built on, are permanent.

**If you want customised lighting on a bank, take over one of the existing eight** by repointing its
`macro_assign` rows — `initial_macro_id` preserves the factory value, so the revert is free.

## Gotchas

- `macro_data` has **exactly 25 rows per macro** (one per `macro_fixture` slot) in the current-format library. Unused slots have `data = ""` (empty string) — **not** `NULL`, **not** a missing row. When writing a new macro, always insert 25 rows, one per slot, even if most are `""`.
- `macro_event` has 0 rows in the live library and is unused by rekordbox 6 — never write to it.
- Some macros have only **19 rows** in `macro_data` (older, pre-Simple-slots format, before the 6 `_101/_102/_103` slots existed). Read tolerantly (missing slot = treat as empty), but always **write** the full 25-row set.
- One macro has **150 rows** in `macro_data` (a known anomaly in the factory library) — do not assume exactly-25 on read, only on write. Do not crash on extra rows; ignore rows whose `macro_fixture_id` doesn't resolve to one of the 25 known slots.
