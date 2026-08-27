---
epic: "TRACKLIGHT"
title: "YAML assignment rules and pure resolver"
estimate: M
status: ready
created: 2026-08-26
depends_on: ["S1.1", "E1c"]
labels: [rules, database-free, data-driven, validation]
priority: P1
claimed_by:
claimed_by_date:
---

## 1. User Story

**As a** sound designer / DJ\
**I want** to author explicit rules mapping track metadata to bank and energy choices as data, not code\
**So that** the assignment logic is reviewable, difable, and changeable without touching the resolver code

## 2. Business Context & Value

The assignment chain requires mapping from a track's metadata (genre, My Tags, BPM) to a bank and energy choice. This is domain knowledge the DJ provides, not something the tool infers. By expressing that knowledge as a hand-authored YAML rule set, the intent becomes explicit and auditable — the rule file is the permanent record of "why this bank for this kind of track", and changes to the rules are visible as diffs rather than buried in code.

**E1c-E1f measured the taxonomy and true addressable set:**
- 51 My Tags organized into 4 categories (Mood, Situation, Genres, Components)
- 63 ID3 genre values
- BPM medians per Situation tag ranging from 109.7 (Afbouw) to 152.7 (Laatste kwartier), separated monotonically
- 44.6% of My Tag-carrying tracks carry more than one Mood tag, so rule conflicts are common and must be resolved by explicit ordering
- **My Tag coverage differs radically by identity path**: 19.2% in the ID-resolvable population vs. 49.5% in the fingerprint-recovered population. True lit population is more evenly spread across banks and notably better tagged than the biased ID-only sample suggested.

The resolver is a pure function — no database, no file IO, no side effects. This isolation makes it exhaustively testable and is the foundation for S1.3's dry-run capability. It operates only on tracks the reader marked as **identified** (by ID or fingerprint); unidentifiable and ambiguous tracks are passed to S1.3 for operator visibility, never silently dropped.

## 3. Acceptance Criteria

* [ ] **Scenario 1: Rule file loads successfully and validates**
    * Given a hand-authored YAML rule file with valid My Tag, Mood, Genre, Situation, and Components names from the taxonomy
    * When the resolver loads the rule file
    * Then every rule parses successfully and all tag names are validated against the taxonomy

* [ ] **Scenario 2: First matching rule wins**
    * Given a track that matches multiple rules in the ordered list
    * When the resolver evaluates all rules
    * Then the result is the first rule that matches (order is priority)

* [ ] **Scenario 3: Canonical worked example produces correct result**
    * Given the rule: `Genres: Urban` AND `Mood: Geile muziek` ⇒ bank `HOT`
    * When a track carries both those tags
    * Then the result is `HOT`

* [ ] **Scenario 4: Multi-valued field matching**
    * Given a rule matching on `Genres: [Urban, House]`
    * When a track carries the tag `Urban` (among other genres)
    * Then the rule matches

* [ ] **Scenario 5: Rule carries stable identifier for ledger and explain**
    * Given any rule in the file
    * When the rule matches for a track
    * Then the resolver returns the rule's stable identifier so S1.3 can record it in the ledger

* [ ] **Scenario 6: Energy deferred to BPM fallback**
    * Given a rule that specifies a bank but no energy (energy=deferred)
    * When the rule matches a track
    * Then the resolver passes the BPM to the energy resolver to choose HIGH, MID, or LOW based on thresholds defined in the YAML

* [ ] **Scenario 7: Fallback 1 — matching rule in ordered list**
    * Given a track with a My Tag that matches a rule
    * When running the resolver
    * Then the matching rule fires before any fallback is considered

* [ ] **Scenario 8: Fallback 2 — ID3 genre when no My Tag**
    * Given a track with no My Tags but a valid ID3 genre
    * When running the resolver
    * Then the result is the bank mapped from that genre in the genre fallback table (if present)

* [ ] **Scenario 9: Fallback 3 — BPM + default bank when neither My Tag nor genre**
    * Given a track with no My Tags and no matching genre entry
    * When running the resolver
    * Then the result is the default bank + BPM-derived energy

* [ ] **Scenario 10: Fallback 4 — leave track alone**
    * Given a track that matches no rule, no genre, and has no BPM-derived assignment
    * When running the resolver
    * Then the result is explicitly "no assignment" (not a silent default)

* [ ] **Scenario 11: Rule vocabulary validated against live library, staleness detected**
    * Given a rule file is loaded for execution
    * When the resolver is initialized for a `bank plan`
    * Then it validates every tag and genre name against the live library, reporting any that no longer exist, and identifies any rules that matched zero tracks in the current library (standing staleness detector). Rules keyed on newly added tags should start catching tracks, which is correct and needs no action.

* [ ] **Scenario 12: Pure function — no side effects**
    * Given track metadata and a rule set
    * When calling resolve() multiple times with the same inputs
    * Then the same result is returned every time, and no files are read or written

* [ ] **Scenario 13: Bank name ↔ integer mapping lives in one place**
    * Given the module loads
    * When inspecting where bank-name constants are defined
    * Then all bank names (COOL, NATURAL, HOT, SUBTLE, WARM, VIVID, CLUB1, CLUB2) and their integer equivalents are defined in a single, shared location

## 4. Technical Constraints

> ⚠️ Describe WHAT is needed, not HOW. No class names, method signatures, DTO shapes, or endpoint paths.
> The implementing agents + architecture skill decide those.

* **Rule file format**: Hand-authored YAML file, ordered list of rules. Each rule has a `match` clause (conditions ANDed together) and a `result` clause (bank + optional energy). Conditions may constrain any combination of: My Tag Genres, My Tag Mood, My Tag Situation, My Tag Components, ID3 genre, BPM range.

* **Match semantics**: Multiple conditions in one rule are ANDed. A condition naming a multi-valued field (e.g., `Genres`) matches if **any** of the track's values match. Example: a track tagged with `Genres: Urban, House` matches a rule with `Genres: Urban`.

* **Energy selection**: Rules may specify an explicit energy (HIGH, MID, LOW) or defer to BPM. When deferred, the resolver applies thresholds defined in the YAML to choose energy based on the track's measured BPM.

* **BPM thresholds**: Store the measured Situation-tag medians in the YAML (Afbouw 109.7, Background 120, Begin 125, Buildup 126, Peaktime 128, Big Impact 137, Afterparty 145, Laatste kwartier 152.7) as reference, and define the actual energy-selection thresholds as configuration content (not hard-coded).

* **Taxonomy validation and staleness detection**: Load the My Tag taxonomy (51 tags, 4 categories) and ID3 genre list (63 values) from the live library on every `bank plan`. Validate every tag and genre name in the rule file; report any that no longer exist in the library. Identify rules that matched zero tracks on this library state (they may have matched tracks before the library or rules changed, revealing staleness). Unknown tag/genre names hard-fail; zero-match rules are warnings, not errors.

* **Pure resolver**: The resolve function takes (track_metadata, rule_set) and returns (bank, energy, rule_id_that_matched) or (None, None, None) for "no assignment". No database, no file IO, no clock. Side effect–free, so it is exhaustively testable.

* **Fallback chain**: First match in rule list → ID3 genre table → BPM + default bank → explicit "no assignment". Each fallback is tried in order; the first that applies wins.

* **Stable rule identifiers**: Each rule carries a unique, stable ID so the ledger (S1.4) can record which rule fired for each track, and S1.3's `explain` output can name it.

* **Bank-name mapping**: A single, central definition of bank names (COOL=1, NATURAL=2, HOT=3, SUBTLE=4, WARM=5, VIVID=6, CLUB1=7, CLUB2=8) and energy values (HIGH, MID, LOW), shared with S1.3. The tool's own convention, applied consistently.

## 5. Design & UI/UX

The module has no UI. S1.3 uses the resolver to power the `bank plan`, `bank explain`, and downstream commands.

## 6. Scope & Context

### What exists today

- E1c verdict: the `Genres × Mood` co-occurrence matrix and BPM medians per Situation tag, captured in `docs/experiments/E1c-...md`.
- Taxonomy: 51 My Tags organized into 4 categories, 63 ID3 genres. These are measured and stable.
- S1.1 produces track metadata including all My Tags grouped by category, so the resolver input is well-defined.

### Domain rules (non-negotiable)

- **Resolver operates only on identified tracks.** The library reader (S1.1) marks each track as identified-by-ID, identified-by-fingerprint, ambiguous, or unidentifiable. The resolver takes only identified tracks; unidentifiable and ambiguous tracks are passed through to S1.3 for operator visibility, never silently dropped or guessed.
- **Order is priority.** The rule list is ordered; first match wins. This is deliberate — conflicts are common (44.6% of My Tag carriers have multiple Mood tags), and explicit author-controlled ordering is more predictable than scoring schemes.
- **My Tags are never written.** The resolver reads them, never modifies them.
- **ID3 genre is single-valued at the source** (one genre per track in `master.db`), but tags within the `Genres` My Tag category are multi-valued, and both must be preserved in the track metadata.
- **No per-track pins in v1.** Pinning a specific track to a specific bank (by `song_id`) is not done in this story. If rule authoring reveals a real need, that is a v2 concern.
- **No modifiers in v1.** Tags like `Fout` that layer onto era or vibe tags (shifting an already-chosen bank rather than selecting one) are out of scope. In v1, `Fout` is a condition an author may use inside an ordinary rule.
- **BPM always separates energy, never bank.** The rule *may* defer energy selection to BPM, but it must always specify a bank explicitly.
- **My Tag coverage is 49.5% in the addressable population.** Hand-authored `Genres` + `Mood` rules carry materially more of the library than earlier ID-only figures suggested (19.2%). ID3 genre and BPM fallbacks remain necessary, but are no longer doing most of the work.

### Known edge cases

- A track with no My Tags, no genre, and no measured BPM — this is rare but valid; the result is explicit "no assignment", not a silent default.
- Genre fallback table may be sparse — not every of the 63 ID3 genres need a bank entry. Unmatched genres fall through to BPM + default.
- A rule matching on a BPM range when the track has no BPM value — the match fails for that rule, fallback chain continues.

## 7. Test Impact Analysis

**Greenfield story** — no existing code is refactored or moved.

### Test files to be created

- New tests for the resolver module, covering:
  - Rule file parsing and validation
  - Taxonomy validation (unknown tag rejection)
  - Single-rule matching
  - Multi-rule ordering (first match wins)
  - Canonical worked example
  - Multi-valued field matching
  - All four fallback levels
  - Rule identifier accuracy
  - BPM-deferred energy selection
  - Pure function behavior (side-effect-free)
  - Bank-name mapping consistency
  - Edge cases (no tags, no genre, no BPM)

## 8. Mandatory Skills for Implementation

- `rekordbox-data-safety` — understand the read-only contract with `master.db` (this story's input)
- `rekordbox-lightingdb-schema` — My Tag and genre taxonomy, `master.db` content
- `rekordbox-lighting-architecture` — module placement, how S1.3 will consume this resolver
