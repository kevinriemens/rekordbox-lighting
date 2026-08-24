"""Interactive terminal menu for rbxlight.

This package is never imported by `cli.py` at module scope — only inside
the entrypoint wiring (the no-args callback and the `tui` command), read
at call time. See `rekordbox-lighting-architecture` skill and
`tests/tui/test_structural_boundaries.py`.

This package must never import `rbxlight.cli`.
"""

from __future__ import annotations
