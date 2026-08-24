# BUGS — Ship margin fraction in preview payload

**Completed:** 2026-08-24 · **Estimate:** S · **Priority:** P1

## Problem

The 5% margin reserved by coordinate normalization existed twice: `_MARGIN_FRACTION = 0.05` in
Python and `var TRUSS_MARGIN_FRACTION = 0.05` in `template.html`, linked only by a comment.
Changing one without the other silently corrupts `normToCm()` output — wrong centimetres in the
truss editor panel and in exported `structure_cm`, with no crash and no failing test. This is the
same class of defect that shipped a (0,0)cm → (12,210)cm round-trip error in the 2026-08-16
truss-editing story.

## What changed

| File | Change |
|---|---|
| `src/rbxlight/preview/layout_geometry.py` | `_MARGIN_FRACTION` → public `MARGIN_FRACTION`; stale "shared magic constant" comment rewritten, dated |
| `src/rbxlight/preview/layout.py` | facade re-exports `MARGIN_FRACTION` |
| `src/rbxlight/preview/payload.py` | new top-level payload key `margin_fraction`; shape docstring updated |
| `src/rbxlight/preview/template.html` | reads `RBXLIGHT_PAYLOAD.margin_fraction`; **throws** if missing or non-numeric — no fallback |
| `tests/preview/test_payload.py` | tripwire key-set literal updated (strict `==` preserved); new test asserts payload value `is` the imported constant |
| `tests/preview/test_document.py` | `_SAMPLE_PAYLOAD` extended; new test asserts the value survives into the rendered HTML |

`document.py` unchanged — the key rides along in `json.dumps(payload)`.

## Decisions

1. **Key name:** `margin_fraction` — lowercase snake_case, matching `frame_cm` / `bpm`.
2. **No JS fallback.** A missing key means a payload/template version mismatch; a silent default
   would reintroduce exactly the failure mode this story removes. Guard throws with a message
   naming the key and the mismatch.
3. **`_SAMPLE_PAYLOAD` updated.** It models the full payload contract (carries `macro`, `venue`,
   `bpm`, `fixtures`), unlike the deliberately minimal inline `empty_payload` in the
   no-fixtures test, which was left alone.

## Verification

719 tests pass · `ruff check` clean · `mypy src/` clean (25 files).

## Limitation

`skip_frontend_tests=true` — there is no JS test runner. The Python side asserts the value ships;
the JS side (payload read, throw guard, inverse transform) is verified by code review only. The
transform maths was not touched, only the provenance of `m`.
