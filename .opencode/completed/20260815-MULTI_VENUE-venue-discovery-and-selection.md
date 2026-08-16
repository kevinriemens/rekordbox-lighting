# Venue discovery and selection

**Completed:** 2026-08-15
**Epic:** MULTI_VENUE
**Source:** `.opencode/refined/MULTI_VENUE-venue-discovery-and-selection.md` (story 1 of 3)

## Summary

Added `rbxlight venue list` and centralized venue resolution so `preview` and `layout regenerate` both
validate the venue exists, say which venue they used and why, and enumerate the valid venues when they
can't resolve one. Fixed a latent defect found during research: `layout regenerate` silently succeeded
with zero fixtures when given a non-existent or stale venue id.

## Plan Approved by the user

Approved implicitly — user requested a straight run to the commit gate.

### Requirements Summary

- `venue list` command: id, name, fixture count, marker for the active venue
- Venue resolution validates existence; errors enumerate valid venues and keep the failing id in the text
- Stale vs unset active-venue pointer produce distinct, actionable errors
- `preview` and `layout regenerate` confirm which venue was used and whether it came from the flag or the fallback
- Missing working copy produces an actionable "run pull" error, not a stack trace

### Technical Approach

- Backend: additive read-only venue enumeration with fixture counts in the venue repository; new `venue`
  typer sub-app; one shared venue resolver used by both venue-aware commands; one shared working-copy guard
- Frontend: none — CLI-only story
- Database: no schema changes, read-only, working copy only

### Execution Order

| Phase | Agent | Task |
|---|---|---|
| 2.1 | backend-testing-agent | Test suite (fails first) |
| 2.2 | backend-agent | Implement to green |
| 2.3 | backend-optimizer-agent | Refactor + standards review |

Frontend phases skipped (CLI-only). Test-conflict scan ran and found no conflicts, so the Phase 1.3
gate was a no-op.

## Research Findings That Shaped the Story

Three findings from the parallel research pass changed the plan from the refined story's assumptions:

1. **`layout regenerate` never validated the venue.** `preview` got existence-checking for free as a side
   effect of the preview payload builder calling `get_venue`; `layout regenerate` had no such call, so a
   bad or stale `--venue` produced `0 fixture(s) unchanged.` and exit 0. Scenarios 2 and 6 were therefore
   a real bug, not message polish. Centralizing resolution fixed both commands at once.
2. **No working-copy guard existed** on either read command — running before `pull` surfaced a raw
   `sqlite3.OperationalError`. Only `push` had an ad-hoc "run pull first" message, for a different case.
3. **Zero existing tests exact-matched venue output text** — every assertion was a substring, exit-code or
   exception-type check — so all message enrichment was additive-safe and no scenario had to be weakened.

## Implementation

### Backend

- `venues/models.py` — `VenueWithFixtureCount` frozen dataclass (kept in the venues models module, not the
  top-level one, per the existing intentional split)
- `venues/repo.py` — `list_venues_with_fixture_counts(conn)`: single LEFT JOIN + GROUP BY (no N+1),
  ordered by venue id, returns zero-fixture venues with count 0, empty list when no venues exist,
  read-only-connection safe
- `cli.py`
  - `venue` sub-app registered on the root app, with `venue list`
  - `_require_working_copy(path)` — shared actionable guard for the not-yet-pulled case
  - `_readonly_working_copy(...)` — context manager wrapping resolve → guard → connect read-only → close
  - `_format_venue_line` / `_venue_listing_text` — one formatter shared by the listing and by the error
    enumerations, so the two cannot drift apart
  - `_resolve_venue_and_fixtures` rewritten to validate existence and return `(Venue, fixtures, source)`,
    distinguishing explicit-not-found / no-active-venue / stale-active-pointer
  - `_announce_venue_selection` — `Venue: <id> (<name>) — selected via <explicit|active venue>.`

### Frontend

None.

### Deviations from Plan

- The story framed scenarios 2 and 6 as error-message improvements. They were implemented as a behavioral
  fix as well, because `layout regenerate` was silently succeeding. Strictly more than the story asked for,
  but the story's acceptance criteria could not be satisfied without it.
- `venue list` deliberately does NOT fail on a stale active-venue pointer — it is the command the user runs
  to recover from exactly that state, so it lists every real venue and marks none active.

## Agents Used

| Agent | Task | Result |
|---|---|---|
| deep-research-agent ×3 (parallel) | CLI venue resolution / venue repo layer / test coverage conflict scan | Complete |
| backend-testing-agent | 28 tests + multi-venue fixture | Complete |
| backend-agent | Implementation to green | Complete |
| backend-optimizer-agent | Duplication extraction + standards review | Complete |

## Files Modified

- `src/rbxlight/cli.py` — venue sub-app, shared resolver, working-copy guard, selection confirmations
- `src/rbxlight/venues/repo.py` — `list_venues_with_fixture_counts`
- `src/rbxlight/venues/models.py` — `VenueWithFixtureCount`
- `tests/test_cli.py` — `TestVenueListCommand`, `TestMissingWorkingCopyForVenueAwareCommands`, new preview
  and layout-regenerate venue tests, 3 existing tests extended
- `tests/venues/test_repo.py` — `TestListVenuesWithFixtureCounts`
- `tests/fixtures/venue_fixtures.py` — `a_multi_venue_database()`; `set_lighting_property` now
  `INSERT OR REPLACE` so a stale `ExecVenueId` can be simulated

## Tests

- 502 tests, 502 passing (474 pre-existing unchanged + 28 new)
- New coverage for the stale-active-pointer case, which had none before
- `ruff check` / `ruff format --check` / `mypy src/` clean

## Playbook Candidates

None reported — this is a CLI project with no playbook route.
