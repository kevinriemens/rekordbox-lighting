# Macro composition engine (compose + curves)

**Completed:** 2026-08-25
**Epic:** USER_CHANGE_REQUEST
**Source:** ad-hoc request

## Summary

Asked for three retro-70s "fout party" macros, the project got the thing that makes macros instead: a pure composition primitive (`compose.py`) and a shared curve vocabulary (`curves.py`). The three macros were built, verified and left in the working copy — but deliberately **not** committed as Python, because content is not code.

## Plan Approved by the user

### Requirements Summary

- Three production-ready festive/retro-70s macros, 32 beats each, no track assignment (user does that themselves)
- Must look *programmed*, not generated — factory density as the benchmark
- Nothing touches the live LightingDB; pushing stays an explicit separate step

### Technical Approach

- Backend: a pure `compose()` primitive (the composable building block `generate.py` never had), three preset recipes, a `preset list|create` CLI (no macro-import path existed), preview HTML per macro
- Frontend: none
- Correct the `physical-rig-profile` skill with the measured venue-2 slot table

### Execution Order

| Phase | Agent | Task |
| ----- | ----- | ---- |
| 1 | backend-testing-agent | Test suite for compose + presets + CLI |
| 2 | backend-agent | Implement to pass |
| 3 | backend-testing-agent | Re-scope: curve vocabulary tests, delete preset tests |
| 4 | backend-agent | Extract `curves.py`, delete `festive_presets.py` and the preset CLI |

## Implementation

### Backend

**`src/rbxlight/macros/compose.py`** (271 lines) — `compose_slot_payload(beats, fixture_type_id, *, brightness, colour, strobe, movement, rotate) -> str`. Pure. Builds one LightingEditModel payload for one slot from declarative parts, via the existing `models.py` dataclasses and `lightingxml.serialize` — never by string-building XML. Reads `FIXTURE_TYPE_CAPABILITIES` rather than duplicating it, so Position/Rotate/Gobo land in the correct one of three states (populated / present-but-empty / absent) per fixture type, and a section requested on a type that cannot do it raises rather than silently rendering nothing. Exceptions: `UnknownFixtureTypeError`, `UnsupportedSectionError`, `InvalidCompositionError`.

**`src/rbxlight/macros/curves.py`** (299 lines) — the vocabulary every macro needs, pure, importing only `compose`:

| Function | Produces |
|---|---|
| `constant_level` | flat brightness |
| `raised_cosine_swell` | smooth breathing swell, floor→peak, N cycles, phase-shiftable |
| `attack_decay_pulses` | sharp attack + decay, repeating on an interval |
| `square_wave` | hard on/off with duty and phase |
| `hold_then_snap_stops` | colour holds then snaps — how real factory macros are programmed |
| `smooth_loop_stops` | colour walks the palette and closes back on itself |
| `dedupe_ascending` | guarantees strictly ascending keyframes |
| `movement_spec` | `MovementSpec` with the 10 rarely-varied attrs defaulted |

Phase arguments wrap (including negative and oversized), so a nine-cell chase is `phase=i * span/9` with no caller-side modulo.

### Database

No schema change. Macros were written to `work/macro.db3` only.

### Deviations from Plan

**Three, all driven by the user, all improvements.**

1. **`festive_presets.py` was deleted, not committed.** The user challenged the test design — *"Shouldn't the tests cover general Macro-creation? ... That would mean every created macro would get it's own tests???"* — and then named the principle: *"Content should not be code. I think this is why we have the YAML right? Never forgot about the foundation. The endgoal here to make a sharable tool to help a lot of users with rbxlight."* Investigation showed the preset tests were in fact a generic conformance suite (zero hardcoded macro names), but two of them pinned today's inventory (`len(presets) == 3`, `all beats == 32`) — they'd punish adding a fourth macro. The real finding was upstream: 832 lines of `festive_presets.py` split cleanly into ~150 lines of engine misfiled as content and ~590 lines of pure content. The engine was promoted to `curves.py`; the content was removed and re-specified as a backlog story.

2. **No `preset` CLI.** It existed and worked, then went with the presets. The replacement is a role-keyed YAML recipe loader, refined separately.

3. **Formatting fix outside scope.** `tests/macros/test_patterns.py` and `tests/fixtures/pattern_fixtures.py` were already failing `ruff format --check` on committed `main` — the verification gate was red before this story started. Formatted; no semantic change. Flagged to the user, kept.

### The three macros

Built, structurally audited, previewed, and left in `work/macro.db3` as **10007 `RETRO70 GLITTERBALL`**, **10008 `RETRO70 RAINBOW STAIRS`**, **10009 `RETRO70 DISCO INFERNO`** — 32 beats, 14 driven slots each, 25 rows, zero NULLs, Position only on `11,12,13,14,111,112`, all nine bar-cell payloads distinct.

| macro | colour blocks | brightness points |
|---|---|---|
| 10007 GLITTERBALL | 46 | 400 |
| 10008 RAINBOW STAIRS | 96 | 173 |
| 10009 DISCO INFERNO | 343 | 1,152 |

Backed up as YAML in `macro_exports/` (gitignored) because they live only in `work/`, which a `pull` would wipe. Those exports are **slot-keyed** — frozen to venue 2, useless on another rig. That is the concrete argument for the role-keyed recipe format.

### Skill correction

`.opencode/skills/physical-rig-profile/SKILL.md` — the venue-2 slot mapping was partly inferred and wrong in two ways that change how a macro is designed. Replaced with the table measured from `work/user.db3`:

- The third LPC008S par shares **slot 16** with the bottom bar cells — pars are *not* three independent slots.
- The two bar **tilt blocks are independent slots (111/112)**, so the bars *can* diverge in movement even though their cells always mirror. The skill's flat "the bars always mirror each other" needed that qualification — it's the one place a macro can make the two legs scissor.

Also recorded: `<Gobo>` is the empty tag in 20/20 occurrences, there is no known gobo payload format, and the codebase models it presence-only.

## Agents Used

| Agent | Task | Result |
| ----- | ---- | ------ |
| deep-research-agent ×3 | Authoring surface, rig/slot mapping, working-copy + factory reference | Complete (parallel) |
| deep-research-agent | Gobo format viability | Complete — verdict "XS but empty" |
| backend-testing-agent | compose + presets + CLI suites (77 tests) | Complete |
| backend-agent | Implement compose, presets, CLI, skill fix | Complete |
| backend-testing-agent | Re-scope: curve suite, delete preset suites | Complete |
| backend-agent | Extract `curves.py`, delete presets + preset CLI | Complete (4 attempts — 3 terminated having written nothing) |

## Files Modified

- `src/rbxlight/macros/compose.py` — new, 271 lines
- `src/rbxlight/macros/curves.py` — new, 299 lines
- `src/rbxlight/macros/festive_presets.py` — created then deleted (832 lines)
- `src/rbxlight/cli.py` — `preset` sub-app added, then removed; all other commands verified intact
- `.gitignore` — added `macro_exports/`
- `.opencode/BACKLOG.md` — new `Ready to refine` section with "Role-based YAML macro recipes" (M), carrying the full creative spec of all three macros so it survives the code deletion
- `.opencode/skills/physical-rig-profile/SKILL.md` — measured slot table
- `tests/macros/test_compose.py`, `tests/macros/test_curves.py` — new
- `tests/fixtures/compose_fixtures.py`, `tests/fixtures/curves_fixtures.py` — new
- `tests/macros/test_patterns.py`, `tests/fixtures/pattern_fixtures.py` — formatting only, pre-existing debt

## Tests

145 added, 966 passing (baseline 821). 42 compose + 103 curves. **Zero reference a macro name** — adding a macro later requires no new test, which was the point of the user's challenge.

## Playbook Candidates

None reported (no UI work; optimizer pass skipped by agreement — `curves.py` is extracted from already-proven maths).

## Lesson

Long delegation prompts correlated with subagent termination three times in a row; trimming the prompt by roughly half fixed it on the fourth attempt. Each dead attempt had written nothing, confirmed via `git status` — no cleanup needed, but worth checking rather than assuming.
