"""Rig layout description: the on-screen position, label, kind, and
rotation of every fixture in a venue. This is NOT rekordbox data —
user.db3's fixture.offset_x/offset_y are a centred placeholder, never a
real physical layout — so this tool maintains its own editable description
on disk (JSON), one file per venue.

Positions are normalized to [0, 1] on both axes so the renderer (built by
another agent against this payload) is resolution-independent. The
vertical axis follows an explicit ground/sky convention (`GROUND_Y`,
`SKY_Y`) rather than leaving "up" ambiguous.

Geometry: the reference rig is a 5-segment arch (see physical-rig-profile
skill, "Physical truss geometry"). `arch_outline_cm()` is the pure
geometric shape; `generate_layout()` mounts fixtures onto it by kind and
patch order, then normalizes everything (fixtures + the outline) into one
consistent [0, 1] frame.

This module is a pure re-export facade: implementation lives in the
sibling `layout_geometry`, `layout_segments`, `layout_placement`, and
`layout_io` modules.
"""

from __future__ import annotations

from rbxlight.preview.layout_geometry import (
    DIAGONAL_ANGLE_DEG,
    DIAGONAL_SEGMENT_LENGTH_CM,
    GROUND_Y,
    SKY_Y,
    TOP_SEGMENT_LENGTH_CM,
    VERTICAL_SEGMENT_LENGTH_CM,
    NormalizationFrame,
    arch_outline_cm,
    frame_cm_to_dict,
    normalize_rotation,
    normalized_arch_outline,
    normalized_structure,
)
from rbxlight.preview.layout_io import (
    InvalidSavedLayoutError,
    LayoutDiffEntry,
    LayoutMergeResult,
    diff_layouts,
    ensure_layout,
    layout_from_dict,
    layout_path_for_venue,
    layout_to_dict,
    load_layout,
    load_layout_file,
    save_layout,
)
from rbxlight.preview.layout_placement import (
    DEFAULT_PAN_DEGREES,
    DEFAULT_TILT_BLOCK_ROTATION_DEGREES,
    DEFAULT_TILT_DEGREES,
    LayoutEntry,
    RigLayout,
    apply_prior_calibration,
    classify_fixture_kind,
    generate_layout,
)
from rbxlight.preview.layout_segments import DegenerateStructureError

__all__ = [
    "DEFAULT_PAN_DEGREES",
    "DEFAULT_TILT_BLOCK_ROTATION_DEGREES",
    "DEFAULT_TILT_DEGREES",
    "DIAGONAL_ANGLE_DEG",
    "DIAGONAL_SEGMENT_LENGTH_CM",
    "GROUND_Y",
    "SKY_Y",
    "TOP_SEGMENT_LENGTH_CM",
    "VERTICAL_SEGMENT_LENGTH_CM",
    "DegenerateStructureError",
    "InvalidSavedLayoutError",
    "LayoutDiffEntry",
    "LayoutEntry",
    "LayoutMergeResult",
    "NormalizationFrame",
    "RigLayout",
    "apply_prior_calibration",
    "arch_outline_cm",
    "classify_fixture_kind",
    "diff_layouts",
    "ensure_layout",
    "frame_cm_to_dict",
    "generate_layout",
    "layout_from_dict",
    "layout_path_for_venue",
    "layout_to_dict",
    "load_layout",
    "load_layout_file",
    "normalize_rotation",
    "normalized_arch_outline",
    "normalized_structure",
    "save_layout",
]
