# Project Foundation

**Written:** 2026-08-14 / 2026-08-15
**Status:** the origin record for this project — how it started, what was discovered, what was proven,
and which assumptions turned out to be wrong.

Read this before doing anything substantial. Most of the expensive mistakes in this project came from
assuming something about the rig or the data that turned out to be false, and every one of them is
written down here so it isn't repeated.

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

**The pattern across all of these: the fixtures were modelled correctly, but how they are physically
mounted was not.** Mounting orientation changes what an axis does.

---

## 6. What was proven against the live database

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

---

## 10. State at the end of the founding session

- **427 tests green**, ruff clean, mypy clean
- M1 complete and verified live (safety, sync, XML round-trip, macro repo, YAML, generators)
- Visualizer complete: arch truss, vertical bars, 3D beam projection, drag-to-position, offline
- Two test macros (`10007`, `10008`) still present in the live library
- M2 blocked pending re-pitch; M4 not started
- Backlog carries CLI gaps, the stale-layout trap, and a multi-venue epic that would make the tool
  reusable on any rig rather than just this arch
