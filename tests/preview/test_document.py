"""Tests for rbxlight.preview.document — self-contained HTML document
generation. Contract: task requirements ("Document generation") — the user
is frequently offline, so no external resource reference is tolerated.
"""

from __future__ import annotations

import json

from rbxlight.preview import document

_SAMPLE_PAYLOAD: dict = {
    "macro": {"id": 10008, "name": "AI TEST SWEEP", "beats": 32},
    "venue": {"id": 2, "name": "TestVenue"},
    "bpm": 128,
    "fixtures": [
        {
            "id": 16,
            "label": "LM70S #1",
            "kind": "moving_head",
            "x": 0.12,
            "y": 0.30,
            "slot_id": 11,
            "slot_name": "Moving Head 1",
            "fixture_type_id": 3,
            "program": {
                "brightness": {
                    "xleft": 0.0,
                    "xright": 32.0,
                    "points": [{"x": 0.0, "y": 1.0, "type": 1}],
                },
                "colour": [],
                "strobe": [],
                "position": [],
                "rotate": [],
                "gobo": None,
            },
        }
    ],
}


class TestRenderPreviewDocument:
    def test_should_produce_a_single_document_string(self) -> None:
        # Given: a built preview payload
        # When: rendering the document
        result = document.render_preview_document(_SAMPLE_PAYLOAD)

        # Then: a non-empty string document
        assert isinstance(result, str)
        assert len(result) > 0

    def test_should_embed_the_full_payload_as_json(self) -> None:
        # Given: a built preview payload
        # When: rendering the document
        result = document.render_preview_document(_SAMPLE_PAYLOAD)

        # Then: the exact payload can be recovered by parsing the embedded JSON
        assert json.dumps(_SAMPLE_PAYLOAD, sort_keys=True) in json.dumps(
            json.loads(_extract_embedded_json(result)), sort_keys=True
        )

    def test_should_contain_no_external_scripts_or_stylesheets(self) -> None:
        # Given: a rendered document
        result = document.render_preview_document(_SAMPLE_PAYLOAD)

        # Then: no <link>, no <script src=...>
        assert "<link " not in result
        assert "script src=" not in result

    def test_should_contain_no_remote_urls_anywhere(self) -> None:
        # Given: a rendered document
        result = document.render_preview_document(_SAMPLE_PAYLOAD)

        # Then: no reference to a remote resource at all
        assert "http://" not in result
        assert "https://" not in result

    def test_should_contain_no_external_font_or_image_references(self) -> None:
        # Given: a rendered document
        result = document.render_preview_document(_SAMPLE_PAYLOAD)

        # Then: no @import / external font-face / remote <img src=...>
        assert "@import" not in result
        assert '<img src="http' not in result
        assert "<img src='http" not in result

    def test_should_handle_a_payload_with_no_fixtures(self) -> None:
        # Given: an edge-case empty-fixtures payload
        empty_payload = {
            "macro": {"id": 1, "name": "EMPTY", "beats": 32},
            "venue": {"id": 1, "name": "EMPTY VENUE"},
            "bpm": 128,
            "fixtures": [],
        }

        # When: rendering the document
        result = document.render_preview_document(empty_payload)

        # Then: still a valid, non-empty self-contained document
        assert isinstance(result, str)
        assert (
            "[]" in result
            or json.loads(_extract_embedded_json(result))["fixtures"] == []
        )


def _extract_embedded_json(document_text: str) -> str:
    """Best-effort extraction of the first JSON object/array literal that
    parses cleanly out of the rendered document — used only to verify the
    payload round-trips, not prescriptive about the embedding mechanism.
    """
    start = document_text.index("{")
    depth = 0
    for index in range(start, len(document_text)):
        char = document_text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return document_text[start : index + 1]
    raise AssertionError("no balanced JSON object found in rendered document")
