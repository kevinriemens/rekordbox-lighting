"""Layout persistence: load/save a RigLayout to/from disk (JSON), diffing,
merging with a venue's current fixture list, and dict (de)serialization.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from rbxlight.preview.layout_geometry import (
    NormalizationFrame,
    arch_outline_cm,
    frame_cm_to_dict,
)
from rbxlight.preview.layout_placement import (
    DEFAULT_PAN_DEGREES,
    DEFAULT_TILT_DEGREES,
    LayoutEntry,
    LayoutMergeResult,
    RigLayout,
    generate_layout,
)
from rbxlight.preview.layout_segments import (
    DegenerateStructureError,
    _validate_structure_cm,
)
from rbxlight.venues.models import Fixture


@dataclass(frozen=True)
class LayoutDiffEntry:
    """One fixture's difference between two RigLayouts, as produced by
    diff_layouts(). Either side may be None: absent from `old` means the
    fixture is new (no "old" side); absent from `new` means it no longer
    exists (no "new" side).
    """

    fixture_id: int
    label: str
    old_x: float | None
    old_y: float | None
    old_rotation: float | None
    new_x: float | None
    new_y: float | None
    new_rotation: float | None


def diff_layouts(old: RigLayout, new: RigLayout) -> tuple[LayoutDiffEntry, ...]:
    """Pure diff between two layouts, by fixture_id. Unchanged fixtures
    (identical x, y, and rotation on both sides) are omitted entirely.
    Deterministically ordered by fixture_id, regardless of the order
    entries appear in either input.
    """
    old_by_id = {entry.fixture_id: entry for entry in old.entries}
    new_by_id = {entry.fixture_id: entry for entry in new.entries}

    diffs: list[LayoutDiffEntry] = []
    for fixture_id in sorted(set(old_by_id) | set(new_by_id)):
        old_entry = old_by_id.get(fixture_id)
        new_entry = new_by_id.get(fixture_id)

        if old_entry is not None and new_entry is not None:
            unchanged = (
                old_entry.x == new_entry.x
                and old_entry.y == new_entry.y
                and old_entry.rotation == new_entry.rotation
            )
            if unchanged:
                continue

        reference_entry = old_entry if old_entry is not None else new_entry
        assert reference_entry is not None  # fixture_id came from old_by_id | new_by_id
        label = reference_entry.label
        diffs.append(
            LayoutDiffEntry(
                fixture_id=fixture_id,
                label=label,
                old_x=old_entry.x if old_entry is not None else None,
                old_y=old_entry.y if old_entry is not None else None,
                old_rotation=old_entry.rotation if old_entry is not None else None,
                new_x=new_entry.x if new_entry is not None else None,
                new_y=new_entry.y if new_entry is not None else None,
                new_rotation=new_entry.rotation if new_entry is not None else None,
            )
        )

    return tuple(diffs)


def load_layout(path: Path) -> RigLayout | None:
    """Read a layout description from disk. Returns None if the file does
    not exist (this is the normal "never generated yet" case, not an
    error).
    """
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return layout_from_dict(data)


def save_layout(path: Path, layout: RigLayout) -> None:
    """Write a layout description to disk as JSON, atomically: write to a
    temp file in the same directory, then `os.replace` it into place, so
    an interrupted save can never leave a truncated/corrupt file at
    `path`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(layout_to_dict(layout), indent=2)

    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(data)
        os.replace(tmp_name, str(path))
    except BaseException:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


class InvalidSavedLayoutError(ValueError):
    """Raised by `load_layout_file` when a file that is expected to
    already be a saved layout export cannot be parsed as one: invalid
    JSON, missing required fields, or a required field with the wrong
    type. Degenerate stage/truss geometry is a distinct, already-typed
    failure mode (`DegenerateStructureError`) and is never wrapped by
    this one.
    """


def load_layout_file(path: Path) -> RigLayout:
    """Load a layout file expected to already exist — e.g. a file
    exported by the offline visualizer for `layout install`.

    Unlike `load_layout` (which treats a missing file as the normal
    "never generated yet" case and returns None), any failure to parse
    `path` as a well-formed saved layout raises InvalidSavedLayoutError
    with an actionable message. `DegenerateStructureError` from
    `layout_from_dict`'s structure validation propagates unchanged, not
    wrapped.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InvalidSavedLayoutError(f"could not read {path}: {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidSavedLayoutError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise InvalidSavedLayoutError(
            f"{path} must contain a JSON object describing a saved layout, "
            f"got {type(data).__name__}."
        )

    try:
        return layout_from_dict(data)
    except DegenerateStructureError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise InvalidSavedLayoutError(
            f"{path} is not a valid saved layout: {exc}"
        ) from exc


def ensure_layout(
    path: Path, venue_id: int, fixtures: Sequence[Fixture]
) -> LayoutMergeResult:
    """Load path if it exists; otherwise generate a brand new layout.

    When a layout already exists: every existing entry for a fixture still
    present in `fixtures` is preserved UNCHANGED (the user's adjusted
    positions/rotations are never silently overwritten). A new entry is
    generated only for a fixture with no existing entry. Any existing
    entry whose fixture_id has no match in `fixtures` is removed from the
    returned layout but reported via `orphan_fixture_ids` — never silently
    dropped from the caller's knowledge, only from the renderable set.

    The (possibly merged) result is written back to `path`.
    """
    fixture_list = list(fixtures)
    fixture_ids = {fixture.id for fixture in fixture_list}

    existing = load_layout(path)
    existing_by_id = (
        {entry.fixture_id: entry for entry in existing.entries} if existing else {}
    )

    orphan_fixture_ids = tuple(
        sorted(
            fixture_id for fixture_id in existing_by_id if fixture_id not in fixture_ids
        )
    )

    # structure is user-owned data too — a saved custom shape is never
    # silently reset back to the default arch just because the venue's
    # fixture patch changed (mirrors layout regenerate's own behavior).
    target_structure = existing.structure_cm if existing is not None else None
    fresh = generate_layout(venue_id, fixture_list, target_structure)
    fresh_by_id = {entry.fixture_id: entry for entry in fresh.entries}

    merged_entries = tuple(
        existing_by_id[fixture.id]
        if fixture.id in existing_by_id
        else fresh_by_id[fixture.id]
        for fixture in fixture_list
    )
    merged_layout = RigLayout(
        venue_id=venue_id,
        entries=merged_entries,
        structure_cm=fresh.structure_cm,
        frame_cm=fresh.frame_cm,
    )
    save_layout(path, merged_layout)

    return LayoutMergeResult(
        layout=merged_layout, orphan_fixture_ids=orphan_fixture_ids
    )


def layout_path_for_venue(venue_id: int, base_dir: Path) -> Path:
    """Default on-disk path for a venue's layout description."""
    return base_dir / f"layout_venue_{venue_id}.json"


def layout_to_dict(layout: RigLayout) -> dict:
    """JSON-serializable representation of a RigLayout (used by
    save_layout, exposed for tests that assert on-disk shape directly).
    """
    return {
        "venue_id": layout.venue_id,
        "entries": [
            {
                "fixture_id": entry.fixture_id,
                "x": entry.x,
                "y": entry.y,
                "label": entry.label,
                "kind": entry.kind,
                "rotation": entry.rotation,
                "pan_degrees": entry.pan_degrees,
                "tilt_degrees": entry.tilt_degrees,
            }
            for entry in layout.entries
        ],
        "structure_cm": [list(point) for point in layout.structure_cm],
        "frame_cm": frame_cm_to_dict(layout.frame_cm),
    }


def layout_from_dict(data: dict) -> RigLayout:
    """Inverse of layout_to_dict. Missing "rotation" (layout files written
    before rotation support existed) defaults to 0.0 rather than failing.
    Missing "pan_degrees"/"tilt_degrees" (layout files written before
    pan/tilt sweep support existed) default to DEFAULT_PAN_DEGREES /
    DEFAULT_TILT_DEGREES for the same reason. Missing "structure_cm"
    (layout files written before stage geometry existed) defaults to the
    standard arch; missing "frame_cm" defaults to None (recovered from
    the structure's own bounding box by `normalized_structure`). Same
    optional-field defaulting precedent as rotation/pan/tilt above — no
    schema version, no migration step.

    Raises DegenerateStructureError if the loaded `structure_cm` cannot
    describe a valid polyline.
    """
    raw_structure = data.get("structure_cm")
    structure_cm = (
        tuple((float(x), float(y)) for x, y in raw_structure)
        if raw_structure is not None
        else arch_outline_cm()
    )
    _validate_structure_cm(structure_cm)

    raw_frame = data.get("frame_cm")
    frame_cm = (
        NormalizationFrame(
            min_x=raw_frame["min_x"],
            max_x=raw_frame["max_x"],
            min_y=raw_frame["min_y"],
            max_y=raw_frame["max_y"],
        )
        if raw_frame is not None
        else None
    )

    return RigLayout(
        venue_id=data["venue_id"],
        entries=tuple(
            LayoutEntry(
                fixture_id=entry["fixture_id"],
                x=entry["x"],
                y=entry["y"],
                label=entry["label"],
                kind=entry["kind"],
                rotation=entry.get("rotation", 0.0),
                pan_degrees=entry.get("pan_degrees", DEFAULT_PAN_DEGREES),
                tilt_degrees=entry.get("tilt_degrees", DEFAULT_TILT_DEGREES),
            )
            for entry in data["entries"]
        ),
        structure_cm=structure_cm,
        frame_cm=frame_cm,
    )
