---
epic: "BUGS"
title: "Ship margin fraction in preview payload to eliminate silent coordinate corruption"
estimate: S
status: ready
created: 2026-08-23
depends_on: [ ]
labels: [ backend, frontend, data-integrity ]
priority: P1
claimed_by:
claimed_by_date:
---

## 1. User Story

**As a** venue layout editor\
**I want** the margin fraction used to normalize truss coordinates to be mechanically linked between Python and JavaScript\
**So that** accidental drift between the two implementations cannot silently corrupt exported structure coordinates\

## 2. Business Context & Value

The preview payload normalizes truss structure coordinates from real-world centimetres into a [0, 1] range, reserving a 5% margin on every edge to prevent clipping at the renderer's boundaries. This normalization is implemented in two places:

- Python: `_normalize_point()` in `src/rbxlight/preview/layout.py` uses a constant `_MARGIN_FRACTION = 0.05`
- JavaScript: `cmToNorm()` and `normToCm()` in `src/rbxlight/preview/template.html` use a hardcoded `TRUSS_MARGIN_FRACTION = 0.05`

Currently, these are linked only by a cross-referencing comment block. If the Python value is changed without updating the JavaScript (or vice versa), the JavaScript's inverse transformation (`normToCm()`) will produce incorrect real-world coordinates. This corruption is silent — no error is raised, no test catches it — and manifests as wrong values in the truss editor panel and in exported `structure_cm` data.

The fix is to ship the margin fraction in the preview payload so JavaScript reads it from the payload instead of hardcoding it. This makes the link mechanical and testable.

## 3. Acceptance Criteria

* [ ] **Scenario 1: Margin fraction is shipped in the payload**
    * Given a preview payload is built
    * When the payload is serialized to JSON
    * Then the margin fraction value (0.05) appears exactly once in the payload, at a top-level key
* [ ] **Scenario 2: JavaScript reads from the payload**
    * Given the rendered preview document contains the payload
    * When JavaScript's `cmToNorm()` and `normToCm()` functions execute
    * Then they read the margin fraction from the payload instead of using a hardcoded literal
* [ ] **Scenario 3: Round-trip conversion is preserved**
    * Given a real-world cm point and the margin fraction
    * When the point is normalized via Python's `_normalize_point()` and then inverted via JavaScript's `normToCm()`
    * Then the result equals the original cm point (within floating-point precision)
* [ ] **Scenario 4: No hardcoded margin literal in template**
    * Given the template.html file
    * When searched for the literal `0.05` in the context of margin or normalization
    * Then no such literal exists (the comment block explaining the mirror is deleted or rewritten)
* [ ] **Scenario 5: Tripwire test is updated and remains strict**
    * Given the test asserting exact set equality on payload top-level keys
    * When the payload shape changes to include the margin fraction
    * Then the test's key-set literal is updated to include the new key, and the assertion remains a strict set-equality check (not weakened to a subset)
* [ ] **Scenario 6: All checks pass**
    * Given the implementation is complete
    * When `pytest`, `ruff check .`, and `mypy src/` are run
    * Then all pass with no new failures

## 4. Technical Constraints

* **Payload contract**: The margin fraction must be added as a top-level key in the dict returned by `build_preview_payload()` in `src/rbxlight/preview/payload.py`. The key name must follow the existing payload's naming convention (lowercase snake_case, e.g., `bpm`, `frame_cm`).
* **JSON serialization**: The value must be JSON-serializable (a float). It is embedded in the payload via `render_preview_document()` in `src/rbxlight/preview/document.py`, which calls `json.dumps(payload)`.
* **JavaScript access**: The JavaScript code must read the value from the global `RBXLIGHT_PAYLOAD` object (parsed from the embedded JSON) instead of using a hardcoded literal.
* **No fallback**: The JavaScript must not defensively fall back to a hardcoded value if the key is missing. A missing key indicates a version mismatch between the payload generator and the template, and a silent fallback would reintroduce the exact silent-corruption failure mode this story exists to eliminate. Failing loudly (e.g., a thrown error) is the correct behaviour.
* **Inverse transformation**: The JavaScript's `normToCm()` function must remain an exact mathematical inverse of Python's `_normalize_point()`, accounting for the y-axis inversion (ground = larger value in [0, 1]).

## 5. Design & UI/UX

N/A — this is a data-integrity fix with no user-facing UI changes. The rendered preview output is visually and numerically identical before and after (the value is unchanged; only its provenance changes).

## 6. Scope & Context

### Existing behaviour affected

- `build_preview_payload()` currently returns a dict with keys `{macro, venue, bpm, truss, fixtures, frame_cm}`. The new key will be added to this set.
- The payload is embedded in the HTML document via `render_preview_document()`, which serializes the entire dict to JSON. The new key will be included in that JSON.
- JavaScript's `cmToNorm()` and `normToCm()` functions currently use the hardcoded `TRUSS_MARGIN_FRACTION` variable. They will be updated to read from the payload instead.

### Domain rules and edge cases

- The margin fraction is a constant (0.05) and does not vary per macro, venue, or layout. It is a property of the normalization algorithm itself.
- The y-axis inversion (ground = larger value) is part of the normalization contract and must be preserved in the inverse transformation.
- The comment block in template.html (lines 527–539) explicitly states that the margin fraction is "not shipped in the payload" and is "a shared magic constant". This comment must be deleted or rewritten to reflect the new design, as leaving it would be actively misleading.

### Known pitfalls

- The tripwire test in `tests/preview/test_payload.py` (function `test_should_keep_the_payload_shape_unchanged_by_the_shared_frame_and_reference_box_change`) asserts exact set equality on the payload's top-level keys. Adding a key will fail this test until the set literal is updated. This is by design — the test is a deliberate guard against accidental payload growth. Updating the literal is an in-scope, intentional act for this story.
- There is no JavaScript test runner in this project (`skip_frontend_tests=true`), so the JavaScript side of the change cannot be verified by automated tests. The Python-side assertion that the value ships correctly is the only automatable guarantee. The JavaScript side must be verified by code review and manual testing.

## 7. Test Impact Analysis

### Existing tests affected by this change

| Test File | Test Method | What it asserts | Conflicts? | Action |
|-----------|------------|-----------------|------------|--------|
| `tests/preview/test_payload.py` | `test_should_keep_the_payload_shape_unchanged_by_the_shared_frame_and_reference_box_change` | Exact set equality on payload top-level keys against `{"macro", "venue", "bpm", "truss", "fixtures", "frame_cm"}` | YES | Update the key-set literal to include the new margin fraction key; keep the assertion as strict set equality (do not weaken to subset) |

### Test modification policy

- [ ] The tripwire test's key-set literal MUST be updated to include the new key.
- [ ] The assertion MUST remain a strict set-equality check (`==`, not `<=` or subset).
- [ ] No other existing tests in `tests/preview/` assert payload top-level keys, so no other tests require modification.

### New test coverage needed

A test asserting that:
- The payload carries the margin fraction value
- The value equals the Python constant `_MARGIN_FRACTION` from `src/rbxlight/preview/layout.py`
- The value is JSON-serializable and appears in the rendered document

(Do not name this test — the implementing agent will decide the name and placement.)

### Existing files impacted

| File | Impact |
|------|--------|
| `src/rbxlight/preview/payload.py` | `build_preview_payload()` must add the margin fraction to the returned dict |
| `src/rbxlight/preview/document.py` | No changes required; the new key is automatically included in the JSON serialization |
| `src/rbxlight/preview/template.html` | `cmToNorm()` and `normToCm()` must read the margin fraction from the payload; the hardcoded `TRUSS_MARGIN_FRACTION` variable and its comment block (lines 527–539) must be removed or rewritten |
| `tests/preview/test_payload.py` | The tripwire test's key-set literal must be updated |
| `tests/preview/test_document.py` | The module-level `_SAMPLE_PAYLOAD` fixture should be reviewed for consistency; the implementer must decide whether to add the new key there (see decision below) |

### Limitation: No JavaScript test coverage

There is no JavaScript test runner in this project. The JavaScript side of the change (reading from the payload, maintaining the inverse transformation) is verified by code review and manual testing only. The Python-side assertion that the value ships correctly is the only automatable guarantee.

## 8. Open Decisions

### Decision 1: Payload key naming

**What**: What should the new top-level key be named in the payload dict?

**Context**: Existing payload keys are lowercase snake_case (`frame_cm`, `bpm`). The key must be consistent with this style and clearly represent what the JavaScript variable represents (the margin fraction used in normalization).

**Recommendation**: Use `margin_fraction` (lowercase snake_case, matches existing convention, clearly names the concept).

**Implementer action**: Pick a name consistent with the payload's existing style and document the choice in the commit message.

### Decision 2: JavaScript fallback behaviour

**What**: Should the JavaScript defensively fall back to a hardcoded value if the margin fraction key is missing from the payload?

**Context**: A missing key would indicate a version mismatch between the payload generator and the template (e.g., an old template rendering a new payload, or vice versa). A silent fallback would reintroduce the exact silent-corruption failure mode this story exists to eliminate.

**Recommendation**: No fallback. Fail loudly (throw an error) if the key is missing. This makes version mismatches immediately visible and prevents silent data corruption.

**Implementer action**: Ensure the JavaScript code raises an error if the margin fraction key is not found in the payload, rather than using a default value.

### Decision 3: `_SAMPLE_PAYLOAD` in test_document.py

**What**: Should the module-level `_SAMPLE_PAYLOAD` fixture in `tests/preview/test_document.py` be updated to include the new margin fraction key?

**Context**: This fixture is used by the test `test_should_embed_the_full_payload_as_json`, which does not call `build_preview_payload()` directly. It is a manually constructed sample payload. The fixture does not currently include `frame_cm` (which is optional and can be None), so it may be intentionally minimal.

**Recommendation**: Read the fixture and its surrounding context to understand whether it is meant to model the full real payload contract or a minimal subset. If it models the full contract, add the new key for consistency. If it is intentionally minimal, leave it as-is.

**Implementer action**: Make this decision after reading the fixture and its test, and document the choice in the commit message.
