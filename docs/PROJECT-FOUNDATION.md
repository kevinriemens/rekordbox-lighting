# Project Foundation

**Written:** 2026-08-14 / 2026-08-15
**Status:** the origin record for this project — how it started, what was discovered, what was proven,
and which assumptions turned out to be wrong.

Read this before doing anything substantial. Most of the expensive mistakes in this project came from
assuming something about the rig or the data that turned out to be false, and every one of them is
written down here so it isn't repeated.

---

## The north star: a light show per track

**Written:** 2026-08-26

Rekordbox offers 8 mood banks × 3 energy levels = 24 combinations, and in practice assigns COOL to almost everything. Even used perfectly, 24 combinations across a whole night becomes repetitive fast. **The end goal is a bespoke light show per track, generated automatically from what the track is and how it is built.**

That goal is reached in three stages. Each stage is independently useful — none is a throwaway step toward the next.

**Stage 1 — Diversify onto the stock banks.** Spread tracks across all 24 existing combinations using rules authored from the DJ's own rekordbox My Tag taxonomy, plus genre and BPM. Zero new lighting content is created: 232 factory macros already exist and most have never played, because two thirds of the library sits on COOL. This is the highest variety-per-unit-of-effort move in the entire plan.

**Stage 2 — Grow the content.** Replace factory macro content with our own, authored as YAML recipes keyed by fixture role. After this the 24 combinations are ours, not Pioneer's.

**Stage 3 — Per-track shows.** Write `phrase_data` directly, driven by each track's own analysed structure. The bank stops being the whole show and becomes merely a starting point.

### Constraints that shape every stage

- **Only 8 banks exist, permanently.** The ninth-bank probe (2026-08-25) proved rekordbox's mood selector is a fixed 8-button surface. Storage tolerates unknown rows; the UI is the hard limit. Any design that needs a 9th bank is dead on arrival.
- **Content is YAML, never Python.** Established by the RETRO70 reversal. The engine is code; what the lights actually do is data.
- **`master.db` is read-only forever.** Lighting intent lives in this repository, never written back into rekordbox's library database.
- **The My Tag panel is a live DJing instrument.** The DJ filters tracks by My Tag mid-set. We read that taxonomy; we never write to it, and we never add categories to it. All lighting-specific mapping lives in this tool's YAML.
- **rekordbox's energy verdict is not trustworthy at the low end.** Measured: tracks the DJ tags `Background` are called HIGH energy by rekordbox 57.9% of the time and LOW 0% of the time. BPM separates the DJ's own `Situation` labels far more cleanly and monotonically. We override energy; we do not inherit it.

### What we learned getting here

- **E1** (`docs/experiments/E1-library-join.md`) — proved `user.db3 content.song_id` IS `master.db DjmdContent.ID`, decisively (the constant `content.master_db_id = 127286662` matches both `djmdProperty.DBID` and `djmdContent.MasterDBID` on every row — the two databases are two views onto the same library instance). rekordbox's DMX lighting subsystem has never been reverse-engineered publicly; no external reference to `LightingDB`, `macro.db3` or `user.db3` exists anywhere. This project is first. E1 also killed track colour as a design channel: 1.5% library usage, and all 8 colour slots are already renamed for an unrelated mixing workflow.
- **E1b** (`docs/experiments/E1b-real-denominator.md`) — measured the join over the denominator that matters and found it worse, not better (22.6% of playlist tracks), then established the cause was not data corruption but simply that most tracks had never been through lighting analysis. Refuted the "stale rows are junk" hypothesis: the unmatched rows carry more lighting programming per row than the matched ones.
- **E1c** (`docs/experiments/E1c-after-full-analysis.md`) — attempted re-measurement after the DJ ran a full-library analysis pass. **Corrected 2026-08-26: the anticipated pass never reached the `content` table at all** — it was byte-for-byte identical before and after, confirmed by direct row diff, not just aggregate counts. E1d/E1d2 later explained why: rekordbox's EXPORT-mode phrase analysis does not touch the LightingDB at all; only actually opening a track in the LIGHTING-mode macro editor creates `content`/`phrase_data` rows (see "How macros get selected for a track" / "Row creation semantics" in the `rekordbox-lightingdb-schema` skill). The concrete `Genres × Mood` combination matrix Stage 1's rules are authored from is real and usable, but it describes the same 1,183-track population E1/E1b already characterized — not an expanded one.

---

## How we accumulate knowledge

**Written:** 2026-08-26, in answer to a direct question: are findings like the E-series actually kept
around, or does every session re-derive them? Until today the honest answer was *partly* — the
findings existed only as seven `docs/experiments/` reports that nothing loads by default. This section
states the standing split going forward.

- **Skills** (`.opencode/skills/*/SKILL.md`) are distilled *operating knowledge* — loaded every
  session, automatically. They state what is currently true and how to work with it. This is where a
  probe's durable findings belong once the probe closes.
- **`docs/experiments/*`** is *evidence and provenance* — the raw measurements, denominators, and
  methodology behind a finding. Not loaded automatically. Kept forever, and cited by name from the
  skill that consumes it, for anyone who wants to verify a number rather than take the skill's word for
  it.
- **This document** is *why the project exists* — the north star, the staged plan, the mistakes not to
  repeat. Not a schema or findings reference; those live in the two places above.

**Standing rule: a probe's findings are folded into the skills when it closes.** The report stays as
the evidence trail; the skill is what the next session actually starts from. A finding that only ever
lives in an experiment report has not really been retained — it has just been filed.

**E-series index** (verdicts folded into `rekordbox-lightingdb-schema` unless noted):

| probe | one-line verdict |
|---|---|
| [E1](../docs/experiments/E1-library-join.md) | `content.song_id` genuinely is `DjmdContent.ID` by design, but 60.1% of rows carry legacy IDs that no longer resolve, and rekordbox's own remap table is empty — unrecoverable by ID alone. |
| [E1b](../docs/experiments/E1b-real-denominator.md) | The denominator that matters (playlist tracks) joins even worse (22.6%) than E1's headline; the stale rows are not dead weight — they carry *more* lighting programming per row than the resolving ones. |
| [E1c](../docs/experiments/E1c-after-full-analysis.md) | The anticipated full-library analysis pass never reached the `content` table; the Stage 1 rule matrix is real but still scoped to the same 1,183-track population as E1/E1b. |
| [E1d](../docs/experiments/E1d-lighting-mode-row-creation.md) | Opening a track in LIGHTING mode created zero new rows this session — the one track already had a row; but changing an existing lit track's bank does rewrite `phrase_data` wholesale from the new bank. |
| [E1e](../docs/experiments/E1e-phrase-phase-mapping.md) | `phrase_num` ordinal position is not the phase key; `(kind, k1, k2, k3, b) → phase`, read from ANLZ `PSSI`, is a stable per-bank lookup, 99.35% accurate over 13,197 validated rows. |
| [E1d2](../docs/experiments/E1d2-row-creation-rerun.md) | The project's own ID-resolvability coverage test is not a lighting-absence test — proven directly on a track the DJ had just re-banked live; ground-truthed E1e's forging table 28/28 on a genuinely new row; explained the 61 legacy orphan rows; confirmed no transition layer exists and found a small (36-track) Analysis Lock population. |

---

## 1. How this started

The session opened in the wrong place: `~/Library/Application Support/Pioneer/rekordbox6`, the live
rekordbox data folder. There was no codebase there — 128 files of settings, XML and SQLite. My
actual goal: **analyze the LightingDB and find a way to author lighting macros without the rekordbox
GUI, which is too slow to use.**

Three pain points, all real:
1. Macros get repetitive a few hours into a set
2. Duplicating/editing macros through the GUI is bulky
3. Assigning macros per track is cumbersome — it must be done one track at a time

The stated dream: *"a small tool, or visual description of my setup, describe some different macros
and assign them in several places to make a more diverse light show, but still rely on rekordbox
automatic."*

The rekordbox folder is **data, not a workspace** — sessions should run from the project directory,
not from inside the Pioneer data folder.

---

## 2. What the LightingDB actually is

Located at `~/Library/Application Support/Pioneer/rekordbox6/LightingDB/`.

| File | Size | Role |
|---|---|---|
| `macro.db3` | 9.8M | macro library — read/write target |
| `user.db3` | 13M | venues, fixtures, per-track phrase assignments — read/write target |
| `master.db3` | 512M | factory fixture-profile library — **read-only, never write** |

**All plain unencrypted SQLite 3.** Not SQLCipher, unlike rekordbox's main `master.db`. This was the
first pleasant surprise and is what made the whole project viable.

**The macro payload is plain XML**, not a binary blob — `macro_data.data` holds a
`LightingEditModel` document. Fully readable and generatable. This was the breakthrough finding.

Full schema and XML format: see the `rekordbox-lightingdb-schema` skill.

---

## 3. The diversity problem, measured

My complaint that the show gets repetitive is **not perception — it's measurable**. Measuring my own
library:

- 2943 tracks, but **60% sit on just 2 of the 27 macro_patterns** (pattern 1 = 39.5%, pattern 7 = 20.7%)
- Each pattern is an 11-phase loop, so pattern 1 is an 11-macro rotation
- `HIGH CHORUS1 COOL` fires **5596×**, `MID CHORUS COOL` 3517×, `HIGH UP1 COOL` 2924×
- 173 of 190 macros are used at least once

**The library is adequate. The distribution is the problem.** That is what M4 addresses, and it is
probably the single highest-impact change available.

---

## 4. The rig

One physical rig, two venue profiles describing it differently.

**Hardware (universe 1):** 4 × LM70S moving head (14ch), 2 × L1015 moving beam bar (43ch),
4 × LPC008S par (7ch — **only 3 are patched**), fogger on ch171.

**The arch**, 5 segments left→right as seen from the audience:
150cm vertical up · 100cm at 45° up · 100cm horizontal · 100cm at 45° down · 150cm vertical down.
Roughly 241cm × 221cm.

**`FullArcCustomBars` (venue 2, active) is a deliberate hack, not a misconfiguration.**
Each L1015's 43 channels are re-declared as smaller off-label profiles to expose the bar's internals:
```
ch57-62    Super Storm1500B Tilt (6ch)   -> the bar's tilt/movement block
ch63-98    9 × 18x10W Pixel Bar (4ch)    -> the bar's 9 individual cells
ch100-105  Super Storm1500B Tilt (6ch)   -> bar 2 tilt block
ch106-141  9 × 18x10W Pixel Bar (4ch)    -> bar 2's 9 cells
```
42 of 43 channels per bar. rekordbox has no concept of a pixel bar with addressable cells, so
declaring fake sub-fixtures at the right offsets is the only way to reach them. Each cell is then
assigned to a *different* macro slot so it inherits a different factory macro's curve — producing
per-cell chases from macros never designed for it.

**Do not "fix" this. Any tool that rewrites venues must preserve it.**

Full detail: the `physical-rig-profile` skill.

---

## 5. Assumptions that were wrong

This is the most important section in this document.

### 5.1 "The bars form one horizontal surface" — WRONG
The original M2 pitch was to unlock a *continuous left-to-right sweep across all 18 cells*.
But the bars are mounted **vertically on the inside of the arch's legs**, so their cells are
**two vertical columns**, not one horizontal surface. What they do well is vertical rises and falls
per leg, mirrored or opposed between legs. **M2 must be re-pitched.**

### 5.2 "The bars' tilt sweeps up and down" — WRONG
Mounting a bar on its end rotates its tilt axis 90°. The tilt motor therefore sweeps the beam fan
**horizontally, left↔right across the room**. I caught this: *"I can't see the tilt of the bars —
they should sweep from left to right, right?"* That instinct was right. Fixed via a 90° default
mounting rotation.

### 5.3 "The pixel bars are mirrored by mistake" — WRONG
Initially read as a patching error. It is a deliberate decomposition (see §4). Corrected early.

### 5.4 "114 macro payloads are unparseable" — WRONG
Arithmetic error (4820 total − 4706 parsed). Those 114 rows are **empty strings**, which are a
legitimate "this fixture does nothing" value. **Every non-empty payload in the real data parses.**

### 5.5 "The rig has 3 pars" — INCOMPLETE
The skill said 3 because the *patch* has 3. I physically own **4**. Physical inventory and
patched inventory are different things and must be documented separately. A sub-agent correctly
halted work over this contradiction rather than encoding a false fact.

### 5.6 "Fixtures arrive grouped as tilt, its 9 cells, tilt, its 9 cells" — WRONG
The repository returns `tilt×2, moving_head×4, bar_cell×18, par×3`. Grouping by list position put
9 cells in a stack at the centre of the arch. **Cells belong to a bar by DMX address range**
(bar 1 owns ch57–99, bar 2 owns ch100–142), which follows directly from the decomposition.
Found by looking at a rendered preview — not by 412 passing tests, because the test fixture used a
tidy ordering that didn't resemble real data.

### 5.7 Moving heads move in 3D, not 2D
Pan swings beams toward and away from the audience, not just side to side. Handled by projecting the
beam vector into a front elevation (with depth foreshortening) plus a top-down plan view — deliberately
**not** a 3D renderer.

### 5.8 "rekordbox will prune a bank it doesn't recognise" — WRONG (2026-08-25)
The predicted failure mode for a ninth bank was that rekordbox would drop or rewrite rows it could not
map to a UI button, possibly taking a heavier hand than just the unknown rows. It does neither. The
probe row survived a full launch/quit cycle completely untouched (§6). The real limit was the other
predicted failure mode: **the bank is simply never displayed.** See §5.9 for why that distinction is
the useful part.

### 5.9 "A phase count can be derived from the bank's energy" — WRONG (2026-08-25)
The schema skill claimed 11 phases at HIGH energy, 10 at MID, 6 at LOW. Measured against the live DB,
the two CLUB banks (patterns 7 and 8) have **10 at HIGH, not 11**. Real shape: patterns 1–6 → 11/10/6
across energies 1/2/3; patterns 7–8 → 10/10/6; pattern 99 → 6/6/6, which sums to the known 232 rows
(`6×27 + 2×26 + 3×6`). This was the *second* wrong formula for that one column in three days — an
earlier correction had replaced a uniform `1..11` with the energy rule, which was also wrong. The rule
now recorded in the skill is: **never compute a phase count, read it from the source bank.** Had the
formula been trusted, the probe bank would have gained a phantom 11th phase row and contaminated the
very experiment it was built for.

**The pattern across all of these: the fixtures were modelled correctly, but how they are physically
mounted was not.** Mounting orientation changes what an axis does. §5.8 and §5.9 add a second pattern:
**a rule inferred from a tidy subset of the data will hold right up until it doesn't** — measure the
whole table, and prefer reading a value over deriving it.

---

## 6. What was proven against the live database

### 6.1 Macro writes are accepted (2026-08-14)

The riskiest unknown was whether rekordbox would even accept externally-written rows. Verified on
2026-08-14 by writing two macros — one a byte-identical clone of an existing user macro, one fully
machine-generated — and confirming both appear in rekordbox.

**Established:**
- rekordbox accepts externally-written macro rows
- no checksum, no version gate, no pruning of unknown rows
- `MacroVersionNum` (1061) / `DbVersionNum` (1854) do **not** need bumping
- machine-generated `LightingEditModel` XML is accepted as valid
- compact single-line XML is fine, despite rekordbox writing pretty-printed output

**Still unproven:** whether a generated macro *renders* as intended during real playback. The preview
shows our interpretation, not rekordbox's engine.

### 6.2 The ninth bank probe — storage tolerates, the UI decides (2026-08-25)

**Question:** does rekordbox honour a `macro_pattern` row whose `pattern` value (9) has no UI button
and no factory macro names? The standing worry was that a ninth bank would be either invisible or
destructive, and the item kept resurfacing because the answer was otherwise unknowable.

**Method.** A throwaway bank was written into the working copy and promoted with `push`: one
`macro_pattern` row `(id=28, energy=1, pattern=9)` plus 10 `macro_assign` rows cloned from bank 19
(CLUB1 at HIGH). The clone points at **existing factory macros**, holding macro content constant so
the pattern integer was the only variable. Deliberately **no track was repointed** — the `content`
table holds 2966 rows of irreplaceable user work, and the question was whether the bank could be
selected *by hand*, which a forced assignment would not have answered. rekordbox was launched,
inspected, and quit; both surrounding pushes passed the "rekordbox not running" guard, so the
observation window is bracketed by verified-quit states.

**Result: NO — the bank is not selectable.** It appeared nowhere: not in performance mode, not in
macro mapping mode. Nothing looked broken; the eight regular banks displayed exactly as normal. The
mood/bank selector is a fixed 8-button surface and an unknown `pattern` value has no way in.

**But it was not pruned — and that is the reusable finding.** The backup taken immediately before the
revert (i.e. a snapshot of live *after* rekordbox had read it) still contained row 28 with all 10
`macro_assign` rows, phases 1–10, `macro_id`s byte-identical to the source bank. `MacroVersionNum`
(1061) and `DbVersionNum` (1854) were unchanged. rekordbox did not reject, rewrite, renumber, or
repair anything. It simply never looked.

**Established:**
- the **storage layer tolerates unknown banks; the UI is the hard limit** — the constraint is presentational, not structural
- rekordbox does not prune `macro_pattern` / `macro_assign` rows it cannot map to a button
- this is consistent with the 61 pre-existing `content` rows pointing at `macro_pattern_id = 0`, a
  pattern that has never existed: rekordbox's habit is to **ignore what it doesn't recognise rather
  than repair it**
- a ninth bank is therefore dead as a user-facing feature, and the item is closed permanently

**Why this still matters:** every remaining bank/venue idea now writes against a database that is
known to be additive-tolerant. The risk in that work is whether rekordbox will *show* a thing, not
whether it will *survive* it — which is a much cheaper class of risk to test.

---

## 7. Safety model (non-negotiable)

This tool writes to a working DJ's live performance data. Data loss breaks a real show. I asked
explicitly that these rules be written down permanently rather than remembered — they live in the
`rekordbox-data-safety` skill and every DB-touching agent must load it.

1. Timestamped backup before any write — no backup, no write
2. Abort if rekordbox is running (it flushes on exit and clobbers external edits)
3. Reads are read-only URI connections, physically incapable of writing
4. Never write `master.db3`
5. Never modify `preset=1` rows (factory macros)
6. All writes in one transaction, roll back on error
7. Dry-run by default, explicit `--write` to commit
8. `restore` ships before any write command does
9. Work on a copy — only `pull` and `push` touch live
10. `push` is stale-write protected by sha256 (optimistic locking)

Plus: every macro write emits exactly **25 `macro_data` rows**; unused slots get an empty string,
never NULL, never a missing row. Tests never touch anything under the rekordbox folder, not even a read.

---

## 8. Why the visualizer exists

I don't have the rig wired up roughly **90% of the time**. Without a preview, evaluating a
generated macro means physically patching DMX — which makes iterating on generated light shows
impractical.

It was originally scheduled *after* M2. That was the wrong order: it is the **feedback loop for
everything else**, and three real bugs (§5.2, §5.6, §5.7) were caught by looking at it, none by the
test suite. It was built before M2 for exactly that reason.

**Honest limitation:** it renders our interpretation of the format, not rekordbox's playback engine.
Movement patterns are approximations; pan/tilt sweeps default to 540°/270° with no datasheet.
It proves internal consistency and is good enough to judge design. One calibration session against
real lights would settle the rest.

Because rekordbox stores **no physical geometry** (every fixture records a centred placeholder),
the layout is entirely the tool's own, lives in `work/layouts/layout_venue_<id>.json`, and is
user-editable by dragging in the visualizer.

---

## 9. Working agreements

- **Nothing is hardcoded about the hardware.** The venue's patched fixture list is the only source of
  truth for what can be controlled. Physical counts and angular sweeps live in editable layout data.
- **Sub-agents should halt on contradictions rather than guess.** This happened once (§5.5) and was
  the correct call — it prevented a false hardware fact being baked into the code.
- **The test suite is not sufficient on its own.** Two real bugs passed a green suite because the
  fixtures didn't resemble real data. When a test fixture and reality disagree, fix the fixture.
- **Preview before pushing to live.** Generation is cheap, wiring up a rig is not.
- **Read the value, don't derive it.** Two separate wrong formulas for `macro_assign`'s phase count
  (§5.9) both came from generalising a rule off part of the table. Query the source row instead.
- **A bounded experiment that returns NO is a success.** The ninth bank probe (§6.2) cost one small
  reversible write and permanently closed an item that had resurfaced repeatedly. Prefer answering a
  speculative question cheaply over carrying it indefinitely — and design the probe so the expensive
  data is never in the blast radius.

---

## 10. State at the end of the founding session

- **427 tests green**, ruff clean, mypy clean
- M1 complete and verified live (safety, sync, XML round-trip, macro repo, YAML, generators)
- Visualizer complete: arch truss, vertical bars, 3D beam projection, drag-to-position, offline
- Two test macros (`10007`, `10008`) still present in the live library
- M2 blocked pending re-pitch; M4 not started
- Backlog carries CLI gaps, the stale-layout trap, and a multi-venue epic that would make the tool
  reusable on any rig rather than just this arch
