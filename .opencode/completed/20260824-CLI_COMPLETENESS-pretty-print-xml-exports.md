# Pretty-print XML in macro YAML exports

**Completed:** 2026-08-24
**Epic:** CLI_COMPLETENESS
**Source:** `.opencode/refined/CLI_COMPLETENESS-pretty-print-xml-exports.md`

## Summary

Macro YAML exports now render each fixture-slot `LightingEditModel` payload as 2-space-indented XML
matching rekordbox's own formatting, so exports can be diffed against rekordbox output and read by
eye. Database bytes are untouched: indentation lives at the export boundary only, and imports
canonicalize payloads back to the serializer's compact form before storage.

## Plan Approved by the user

### Requirements Summary

- Exported YAML fixture payloads indented 2 spaces, XML declaration intact as first line
- Empty slots stay empty strings (not indented empty documents)
- Corrupt/unparseable payloads emitted raw — export never crashes
- Indented XML parses back to the same model (lossless)
- `macro_data.data` bytes unchanged; no reformatting of stored macros

### Technical Approach

- Backend: indent helper + import canonicalization confined to `macros/yaml_io.py`.
  `lightingxml.py`, `generate.py`, `repo.py`, `safety.py` untouched.
- Frontend: N/A

### Execution Order

| Phase | Agent | Task |
| ----- | ----- | ---- |
| 1 | backend-testing-agent | Update 1 test + new suite (fails first) |
| 2 | backend-agent | Implement indent-at-export + canonicalize-on-import |
| 3 | backend-optimizer-agent | Review/simplify |

## Implementation

### Backend

`src/rbxlight/macros/yaml_io.py` (168 lines, net +53):

- `_pretty_print_xml(xml)` — `ET.fromstring` → `ET.indent(space="  ")` → `tostring`, prepends the
  `<?xml version="1.0" encoding="UTF-8"?>` declaration (`tostring` drops it) and strips the space
  ElementTree inserts before `/>` so self-closing tags match rekordbox style (`<Point/>`). Empty and
  unparseable input returned unchanged — export never raises.
- `_canonicalize_payload(xml)` — `lightingxml.parse` + `serialize` → compact canonical bytes.
- `export_macro_yaml` — pipes non-empty payloads through `_pretty_print_xml`; still read-only.
- `import_macro_yaml` — canonicalizes every non-empty payload before `repo.create_macro`, so stored
  bytes are insensitive to how the YAML formatted the XML. Capability validation runs on the **raw**
  user input first, so error messages quote what the user actually wrote.

### Deviations from Plan

- **Canonicalize-on-import was a deliberate scope addition** beyond the story text (flagged and
  approved at the plan gate). Without it, hand-edited indented YAML would write differently-formatted
  bytes than tool-generated macros, breaking the diff-quiet invariant the story exists to protect.
- **Three scenario-preserving test assertion adjustments.** Two round-trip tests — including
  `test_should_reproduce_equivalent_stored_payloads`, which the story's policy protected — compared
  stored bytes against their raw input string. The shared fixture helper `a_valid_slot_payload()`
  turns out to be **hand-written pretty-printed XML**, not canonical serializer output, so the
  verbatim assertion was unsatisfiable under canonicalization without weakening the feature. Verified
  independently before accepting: `serialize(parse(payload)) != payload` for that fixture. The tests
  now compare against the canonical form; the scenario (export → import → canonical bytes) is intact.
  The third was a line-index fix (the multi-section payload has 3 `Point` elements, not 1).

## Agents Used

| Agent | Task | Result |
| ----- | ---- | ------ |
| backend-testing-agent | 15 new tests + 1 updated | Complete — 6 failed for the right reason |
| backend-agent | Implementation | Complete — 659 passing |
| backend-optimizer-agent | Review/simplify | Complete — trimmed a stale docstring, no structural issues |

## Files Modified

- `src/rbxlight/macros/yaml_io.py` — pretty-print on export, canonicalize on import, docstring
- `tests/macros/test_yaml_io.py` — 15 new tests, 1 updated, 3 assertion adjustments

## Tests

- 659 passing (was 644); `ruff check`, `ruff format --check`, `mypy src/` clean
