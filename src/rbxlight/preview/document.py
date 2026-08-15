"""Self-contained preview document generation: embed a preview payload
into a single HTML string with no references to any remote resource — no
external scripts, stylesheets, fonts, or images. The user is frequently
offline; the document must render fully without a network connection.

Loads src/rbxlight/preview/template.html (delivered by another agent
building the renderer) and substitutes the JSON payload for the exact
placeholder token `/*__RBXLIGHT_PAYLOAD__*/`. If the template doesn't
exist yet, a minimal valid placeholder is created in its place so this
module keeps working until the real renderer lands.
"""

from __future__ import annotations

import json
from pathlib import Path

_TEMPLATE_PATH = Path(__file__).parent / "template.html"
_PLACEHOLDER_TOKEN = "/*__RBXLIGHT_PAYLOAD__*/"

_MINIMAL_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>rbxlight preview</title>
<script type="application/json" id="rbxlight-payload">/*__RBXLIGHT_PAYLOAD__*/</script>
<style>
  body { font-family: sans-serif; background: #111; color: #eee; }
</style>
</head>
<body>
<div id="app">Renderer not yet installed — payload embedded below.</div>
<script>
  const RBXLIGHT_PAYLOAD = JSON.parse(
    document.getElementById("rbxlight-payload").textContent
  );
</script>
</body>
</html>
"""


def _load_template() -> str:
    if not _TEMPLATE_PATH.exists():
        _TEMPLATE_PATH.write_text(_MINIMAL_TEMPLATE, encoding="utf-8")
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


def render_preview_document(payload: dict) -> str:
    """Return a single, self-contained HTML document string with
    `payload` embedded as JSON. Must not reference any remote resource
    (no http(s):// URL anywhere in the document).
    """
    template = _load_template()
    payload_json = json.dumps(payload).replace("</", "<\\/")
    return template.replace(_PLACEHOLDER_TOKEN, payload_json)
