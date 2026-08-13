"""JSON payloads: 3D Tiles tilesets, Earth Studio camera exports, and plain pose files.

A ``.json`` on this pipeline is one of about five things, and the extension says none of them. This
module reads the document and decides -- a tileset by ``geometricError`` and ``root``, an Earth
Studio export by its ``cameraFrames``, a glTF by ``asset.version``, a pose file by its array shape.

Earth Studio is the odd one out and earns its place: it exports a camera path in either global ECEF
or local ENU, which is exactly the pair of frames this package's ``transform`` module works in. A
path imported from it drops straight into ``CameraPoseRecord`` with no guessing about convention.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: Keys that identify a document, in the order they are tested. Order matters: a 3D Tiles tileset
#: and a glTF both carry ``asset``, and only the tileset carries ``geometricError`` beside it.
_DISCRIMINATORS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tileset", ("root", "geometricError")),
    ("earth-studio", ("cameraFrames",)),
    ("gltf", ("asset", "scenes")),
    ("nodes-graph", ("nodes", "edges")),
    ("cesium-ion", ("assetMetadata",)),
)


class StructuredError(ValueError):
    """A JSON document was not one of the shapes this pipeline understands."""


def identify(document: Any) -> str:
    """Name the shape of a parsed JSON document."""
    if isinstance(document, list):
        return "pose-array" if document and isinstance(document[0], dict) else "array"
    if not isinstance(document, dict):
        return "unknown"
    for name, required in _DISCRIMINATORS:
        if all(key in document for key in required):
            return name
    if "cameras" in document or "poses" in document:
        return "pose-array"
    return "unknown"


def summarise_tileset(document: dict[str, Any]) -> dict[str, Any]:
    """3D Tiles: version, root error, refinement strategy, and the root bounding volume."""
    asset = document.get("asset") or {}
    root = document.get("root") or {}
    summary: dict[str, Any] = {
        "tiles_version": asset.get("version"),
        "tileset_generator": asset.get("generatetool") or asset.get("generator"),
        "geometric_error": document.get("geometricError"),
        "refine": root.get("refine"),
        "child_count": len(root.get("children") or []),
        "extensions_used": list(document.get("extensionsUsed") or []),
    }
    volume = root.get("boundingVolume") or {}
    if isinstance(volume.get("region"), list) and len(volume["region"]) >= 6:
        # A region is [west, south, east, north, minHeight, maxHeight] in radians and metres.
        import math

        west, south, east, north, low, high = (float(v) for v in volume["region"][:6])
        summary["bounds_geodetic"] = [
            math.degrees(west), math.degrees(south), low,
            math.degrees(east), math.degrees(north), high,
        ]  # fmt: skip
        summary["crs"] = "EPSG:4979"
    elif isinstance(volume.get("box"), list) and len(volume["box"]) >= 12:
        # A 3D Tiles box is a centre followed by three half-axis *vectors*, which may be rotated.
        # The axis-aligned envelope of one is |u_i| + |v_i| + |w_i| **per axis** -- not the sum of
        # the three lengths applied isotropically, which inflates an axis-aligned box by the size
        # of the other two dimensions and is exactly wrong for the common case.
        box = [float(v) for v in volume["box"]]
        centre = box[0:3]
        half = [abs(box[3 + axis]) + abs(box[6 + axis]) + abs(box[9 + axis]) for axis in range(3)]
        summary["bounds"] = [
            centre[0] - half[0], centre[1] - half[1], centre[2] - half[2],
            centre[0] + half[0], centre[1] + half[1], centre[2] + half[2],
        ]  # fmt: skip
        summary["bounds_note"] = (
            "Axis-aligned envelope of the box; exact when the box is itself axis-aligned."
        )
    elif isinstance(volume.get("sphere"), list) and len(volume["sphere"]) >= 4:
        x, y, z, radius = (float(v) for v in volume["sphere"][:4])
        summary["bounds"] = [x - radius, y - radius, z - radius, x + radius, y + radius, z + radius]
    return summary


def summarise_earth_studio(document: dict[str, Any]) -> dict[str, Any]:
    """An Earth Studio JSON track export: frame count, rate, and the frame it is expressed in."""
    frames = document.get("cameraFrames") or []
    summary: dict[str, Any] = {
        "camera_frame_count": len(frames),
        "frame_rate": document.get("frameRate"),
        "duration_frames": document.get("numFrames"),
        "earth_studio_version": document.get("version"),
    }
    # Earth Studio offers global ECEF or local ENU on export, and the two are metres apart in
    # magnitude -- an ECEF path read as ENU lands six million metres from the site.
    coordinate = str(document.get("coordinateSystem") or "").lower()
    if coordinate:
        summary["source_frame"] = "world-ecef" if "ecef" in coordinate else "project-enu"
        summary["coordinate_system"] = coordinate
    elif frames and isinstance(frames[0], dict):
        position = frames[0].get("position") or frames[0].get("coordinate") or {}
        if isinstance(position, dict) and "latitude" in position:
            summary["source_frame"] = "world-geodetic"
        elif isinstance(position, dict) and abs(float(position.get("x", 0) or 0)) > 1e6:
            summary["source_frame"] = "world-ecef"
    if frames:
        summary["first_frame"] = frames[0]
    tracks = document.get("trackPoints") or []
    if tracks:
        summary["track_point_count"] = len(tracks)
    return summary


def summarise(path: str | Path) -> dict[str, Any]:
    """Parse a JSON file and summarise it according to what it turns out to be."""
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as thrown:
        raise StructuredError(f"Not readable as JSON: {thrown}") from thrown

    shape = identify(document)
    summary: dict[str, Any] = {"json_shape": shape}
    if shape == "tileset" and isinstance(document, dict):
        summary.update(summarise_tileset(document))
    elif shape == "earth-studio" and isinstance(document, dict):
        summary.update(summarise_earth_studio(document))
    elif shape == "gltf" and isinstance(document, dict):
        from .mesh import summarise_gltf

        summary.update(summarise_gltf(path, binary=False))
    elif shape == "pose-array":
        entries = (
            document
            if isinstance(document, list)
            else (document.get("cameras") or document.get("poses") or [])
        )
        summary["pose_count"] = len(entries)
        if entries and isinstance(entries[0], dict):
            summary["pose_fields"] = sorted(entries[0].keys())
    elif shape == "nodes-graph" and isinstance(document, dict):
        summary["node_count"] = len(document.get("nodes") or [])
        summary["edge_count"] = len(document.get("edges") or [])
    return summary
