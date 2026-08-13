"""Meshes: OBJ, glTF, GLB, STL.

The interesting one is glTF, because its accessors already carry per-attribute ``min``/``max``. That
means a scene's bounding box is readable out of the JSON chunk without decoding a single vertex --
which for a 400 MB photogrammetry mesh is the difference between a millisecond and a minute.

OBJ has no such index and has to be streamed. It is worth streaming anyway: OBJ is what
OpenDroneMap emits, it is what most conversion pipelines take as input, and a project that knows a
mesh's extent before converting it can reject the one that is a thousand times too large because
somebody exported in millimetres.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

_GLB_MAGIC = b"glTF"
_CHUNK_JSON = 0x4E4F534A
_CHUNK_BIN = 0x004E4942


class MeshError(ValueError):
    """A mesh file did not read as the format it claimed."""


# -- glTF / GLB ---------------------------------------------------------------------------------


def read_glb_json(path: str | Path) -> dict[str, Any]:
    """Pull the JSON chunk out of a GLB. The binary chunk is never touched."""
    path = Path(path)
    with path.open("rb") as stream:
        header = stream.read(12)
        if len(header) < 12 or header[:4] != _GLB_MAGIC:
            raise MeshError('Not a GLB -- the file does not begin with "glTF".')
        _, version, total_length = struct.unpack("<4sII", header)
        if version != 2:
            raise MeshError(f"GLB version {version} is not supported; only glTF 2.0 binary is.")
        while stream.tell() < total_length:
            chunk_header = stream.read(8)
            if len(chunk_header) < 8:
                break
            chunk_length, chunk_type = struct.unpack("<II", chunk_header)
            payload = stream.read(chunk_length)
            if chunk_type == _CHUNK_JSON:
                return json.loads(payload.decode("utf-8"))
            if chunk_type != _CHUNK_BIN:
                continue
    raise MeshError("GLB contains no JSON chunk.")


def _gltf_bounds(document: dict[str, Any]) -> list[float] | None:
    """Union of every ``POSITION`` accessor's declared min and max.

    This is the scene's bounding box in *node-local* coordinates. Node transforms are not applied,
    because doing that properly means walking the scene graph and multiplying, and the number is
    wanted for a plausibility check rather than for placing anything. Callers who need the placed
    extent get it from the converter that produced the file.
    """
    accessors = document.get("accessors") or []
    lows: list[list[float]] = []
    highs: list[list[float]] = []
    for mesh in document.get("meshes") or []:
        for primitive in mesh.get("primitives") or []:
            index = (primitive.get("attributes") or {}).get("POSITION")
            if index is None or index >= len(accessors):
                continue
            accessor = accessors[index]
            low, high = accessor.get("min"), accessor.get("max")
            if isinstance(low, list) and isinstance(high, list) and len(low) >= 3:
                lows.append([float(v) for v in low[:3]])
                highs.append([float(v) for v in high[:3]])
    if not lows:
        return None
    return [
        min(v[0] for v in lows), min(v[1] for v in lows), min(v[2] for v in lows),
        max(v[0] for v in highs), max(v[1] for v in highs), max(v[2] for v in highs),
    ]  # fmt: skip


def summarise_gltf(path: str | Path, *, binary: bool) -> dict[str, Any]:
    path = Path(path)
    document = read_glb_json(path) if binary else json.loads(path.read_text(encoding="utf-8"))
    asset = document.get("asset") or {}

    vertex_count = 0
    triangle_count = 0
    accessors = document.get("accessors") or []
    for mesh in document.get("meshes") or []:
        for primitive in mesh.get("primitives") or []:
            position = (primitive.get("attributes") or {}).get("POSITION")
            if position is not None and position < len(accessors):
                vertex_count += int(accessors[position].get("count") or 0)
            indices = primitive.get("indices")
            # Mode 4 is TRIANGLES and the default when the field is absent.
            if indices is not None and indices < len(accessors) and primitive.get("mode", 4) == 4:
                triangle_count += int(accessors[indices].get("count") or 0) // 3

    summary: dict[str, Any] = {
        "gltf_version": asset.get("version"),
        "generator": asset.get("generator"),
        "mesh_count": len(document.get("meshes") or []),
        "node_count": len(document.get("nodes") or []),
        "material_count": len(document.get("materials") or []),
        "texture_count": len(document.get("textures") or []),
        "vertex_count": vertex_count,
        "triangle_count": triangle_count,
        "extensions_used": list(document.get("extensionsUsed") or []),
        "extensions_required": list(document.get("extensionsRequired") or []),
    }
    bounds = _gltf_bounds(document)
    if bounds:
        summary["bounds"] = bounds
        summary["bounds_sampled"] = False
        summary["bounds_frame"] = "node-local, scene graph transforms not applied"
    if not binary:
        external = [
            buffer.get("uri")
            for buffer in document.get("buffers") or []
            if buffer.get("uri") and not str(buffer["uri"]).startswith("data:")
        ]
        if external:
            # A .gltf that references a sibling .bin is not self-contained, and moving it without
            # its companions is the most common way a viewer ends up with an empty scene.
            summary["external_buffers"] = external
    return summary


# -- OBJ ----------------------------------------------------------------------------------------


def summarise_obj(path: str | Path, *, max_lines: int = 20_000_000) -> dict[str, Any]:
    """Stream an OBJ for counts, bounds and its material references."""
    path = Path(path)
    vertices = normals = texcoords = faces = 0
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    materials: list[str] = []
    groups: list[str] = []
    truncated = False

    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line_number, line in enumerate(stream):
            if line_number >= max_lines:
                truncated = True
                break
            if not line or line[0] == "#":
                continue
            keyword, _, rest = line.partition(" ")
            if keyword == "v":
                parts = rest.split()
                if len(parts) >= 3:
                    vertices += 1
                    try:
                        for axis in range(3):
                            value = float(parts[axis])
                            if value < lo[axis]:
                                lo[axis] = value
                            if value > hi[axis]:
                                hi[axis] = value
                    except ValueError:
                        continue
            elif keyword == "f":
                faces += 1
            elif keyword == "vn":
                normals += 1
            elif keyword == "vt":
                texcoords += 1
            elif keyword == "mtllib":
                materials.extend(rest.split())
            elif keyword in ("g", "o"):
                name = rest.strip()
                if name and len(groups) < 256:
                    groups.append(name)

    summary: dict[str, Any] = {
        "vertex_count": vertices,
        "face_count": faces,
        "normal_count": normals,
        "texcoord_count": texcoords,
        "has_normals": normals > 0,
        "has_texcoords": texcoords > 0,
        "material_libraries": materials,
        "groups": groups,
        "truncated": truncated,
    }
    if lo[0] != float("inf"):
        summary["bounds"] = [lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]]
        summary["bounds_sampled"] = truncated
    return summary


# -- STL ----------------------------------------------------------------------------------------


def summarise_stl(path: str | Path) -> dict[str, Any]:
    """Binary STL triangle count from its header. ASCII STL is reported without a count.

    Counting ASCII triangles means reading the whole file for a number nothing downstream uses, and
    STL is a fallback format here rather than one anybody should be shipping architecture in.
    """
    path = Path(path)
    size = path.stat().st_size
    with path.open("rb") as stream:
        head = stream.read(84)
    if head[:5].lower() == b"solid" and b"facet" in head:
        return {"stl_encoding": "ascii"}
    if len(head) < 84:
        raise MeshError("Binary STL is shorter than its own header.")
    triangles = struct.unpack_from("<I", head, 80)[0]
    expected = 84 + triangles * 50
    summary: dict[str, Any] = {"stl_encoding": "binary", "triangle_count": triangles}
    if expected != size:
        summary["warnings"] = [
            f"Header declares {triangles} triangles ({expected} bytes) but the file is {size}."
        ]
    return summary
