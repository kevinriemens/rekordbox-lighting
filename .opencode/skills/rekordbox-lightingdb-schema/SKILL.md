---
name: rekordbox-lightingdb-schema
description: Schema of rekordbox 6 LightingDB (macro.db3, user.db3) and the LightingEditModel XML macro format. Use when reading, generating, or transforming macros, venues, fixtures, or phrase assignments.
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

   ⚠️ **`phrase_data` is user work and must never be clobbered.** Because it is the layer that actually fires, it also *shadows* `macro_assign`: changing a bank's assignment does not necessarily change what an already-analyzed track plays. Any feature that rewrites `macro_assign` must treat existing `phrase_data` rows as authoritative and leave them alone, and must be honest that its effect on already-analyzed tracks is not guaranteed. Whether rekordbox ever re-copies `macro_assign` into `phrase_data` (on re-analysis? on a UI action?) is **not yet established** — determine it empirically before promising a behaviour.

### `lighting_property` known keys

| key | example value | meaning |
|---|---|---|
| `ExecVenueId` | `2` | currently active venue |
| `LastSelectedVenue` | `2` | last venue selected in UI |
| `MacroVersionNum` | `1061` | schema/content version of macro library |
| `DbVersionNum` | `1854` | schema/content version of user db |
| `AsyncLastMacroId` | — | last macro id touched by async operation |

Current max `venue.id` in the live library = **3**. New venues get `id = 4`.

### Is a ninth bank (`pattern = 9`) possible? — VERDICT PENDING (2026-08-25)

`macro_pattern.pattern` is observed to take values `1..8` (the eight named banks) plus `99`
(INTERLUDE). **Whether rekordbox honours a row with `pattern = 9` is not yet known** — do not
assume either answer.

Two things are already established and do not need testing:
- **There is no name column anywhere.** Bank names exist only as the trailing token of factory macro
  names (`HIGH CHORUS1 COOL`, `CHORUS CLUB1`). A ninth bank therefore has **no name source at all**
  and would be unlabeled in the UI even if the row is honoured.
- **Dangling `macro_pattern_id` values already exist and are tolerated.** 61 `content` rows point at
  `macro_pattern_id = 0`, which has no matching `macro_pattern` row, and rekordbox does not visibly
  break. Weak but real prior evidence that it does not aggressively validate this FK.

The two open hypotheses, both falsifiable in a single rekordbox launch:
1. **Unreachable** — the mood/bank selector is probably a fixed 8-button row, so the bank could never
   be selected manually, and touching the selector may snap an assigned track back into `1..8`.
2. **Pruned on load** — rekordbox may drop or rewrite rows it does not recognise.

**The question is about selectability, not playback.** The useful outcome is whether the bank shows
up in the mood/bank selector as something the user can pick and assign. If it does, rekordbox itself
writes the `content` row, which is stronger evidence than writing one externally because it proves
the round trip. Force-assigning a track only answers the narrower fallback question — does it still
play when assigned programmatically — which matters only if the bank turns out to be unreachable in
the UI.

**Tooling to answer it exists and is committed:** `rbxlight experiment ninth-bank apply|revert`
(see `src/rbxlight/experiments/ninth_bank.py`). The default path adds the bank and writes nothing to
`user.db3` at all — `content` (2966 rows of user work) is untouched unless a track id is explicitly
passed. It works entirely on the working copy; promoting to live is a separate deliberate
`push --write`. When the experiment is run, record the verdict here, dated, and delete the
experiment module.

## Gotchas

- `macro_data` has **exactly 25 rows per macro** (one per `macro_fixture` slot) in the current-format library. Unused slots have `data = ""` (empty string) — **not** `NULL`, **not** a missing row. When writing a new macro, always insert 25 rows, one per slot, even if most are `""`.
- `macro_event` has 0 rows in the live library and is unused by rekordbox 6 — never write to it.
- Some macros have only **19 rows** in `macro_data` (older, pre-Simple-slots format, before the 6 `_101/_102/_103` slots existed). Read tolerantly (missing slot = treat as empty), but always **write** the full 25-row set.
- One macro has **150 rows** in `macro_data` (a known anomaly in the factory library) — do not assume exactly-25 on read, only on write. Do not crash on extra rows; ignore rows whose `macro_fixture_id` doesn't resolve to one of the 25 known slots.
