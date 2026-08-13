"""PLY, read properly.

PLY is the format that makes content-first classification non-negotiable. The same extension is used
for point clouds, for triangle meshes and for Gaussian splats, and the three want completely
different treatment: one is measurable, one is measurable and renderable, and one is a picture that
must never back a dimension. The research brief states the rule outright -- *never assume ``PLY``
means one thing* -- and this module is where that rule is actually enforced.

Header parsing is exact. Bounds are computed by walking the vertex block with ``struct``, which is C
speed for the unpack; for very large clouds it samples and says so rather than pretending.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

#: PLY scalar type to ``struct`` code and byte width.
_SCALARS: dict[str, tuple[str, int]] = {
    "char": ("b", 1),
    "int8": ("b", 1),
    "uchar": ("B", 1),
    "uint8": ("B", 1),
    "short": ("h", 2),
    "int16": ("h", 2),
    "ushort": ("H", 2),
    "uint16": ("H", 2),
    "int": ("i", 4),
    "int32": ("i", 4),
    "uint": ("I", 4),
    "uint32": ("I", 4),
    "float": ("f", 4),
    "float32": ("f", 4),
    "double": ("d", 8),
    "float64": ("d", 8),
}


class PlyError(ValueError):
    """A PLY header could not be read as one."""


@dataclass(frozen=True)
class PlyProperty:
    name: str
    scalar_type: str
    #: Set for list properties (``property list uchar int vertex_indices``), which have no fixed
    #: width and so make the element unstridable.
    count_type: str | None = None

    @property
    def is_list(self) -> bool:
        return self.count_type is not None


@dataclass(frozen=True)
class PlyElement:
    name: str
    count: int
    properties: tuple[PlyProperty, ...]

    @property
    def is_strided(self) -> bool:
        return all(not p.is_list for p in self.properties)

    @property
    def stride(self) -> int:
        if not self.is_strided:
            raise PlyError(f'Element "{self.name}" contains a list property and has no fixed size.')
        return sum(_SCALARS[p.scalar_type][1] for p in self.properties)

    def index_of(self, name: str) -> int | None:
        for index, prop in enumerate(self.properties):
            if prop.name == name:
                return index
        return None

    def has(self, *names: str) -> bool:
        present = {p.name for p in self.properties}
        return all(name in present for name in names)


@dataclass(frozen=True)
class PlyHeader:
    #: ``ascii``, ``binary_little_endian`` or ``binary_big_endian``.
    encoding: str
    version: str
    elements: tuple[PlyElement, ...]
    comments: tuple[str, ...]
    #: Byte offset of the first datum, i.e. just past ``end_header``.
    data_offset: int

    def element(self, name: str) -> PlyElement | None:
        return next((e for e in self.elements if e.name == name), None)

    @property
    def vertex(self) -> PlyElement | None:
        return self.element("vertex")

    @property
    def face_count(self) -> int:
        face = self.element("face")
        return face.count if face else 0


def parse_header(data: bytes) -> PlyHeader:
    """Read a PLY header out of the first bytes of a file.

    Tolerant of CRLF, because PLY written on Windows and read on Linux is the common case and the
    specification's "carriage return" wording has been read both ways by different writers.
    """
    marker = data.find(b"end_header")
    if not data.startswith(b"ply") or marker == -1:
        raise PlyError("Not a PLY header, or the header is longer than the bytes supplied.")
    line_end = data.find(b"\n", marker)
    data_offset = (line_end + 1) if line_end != -1 else marker + len(b"end_header")
    text = data[:data_offset].decode("ascii", errors="replace")

    encoding = ""
    version = ""
    comments: list[str] = []
    elements: list[PlyElement] = []
    name = ""
    count = 0
    properties: list[PlyProperty] = []

    def flush() -> None:
        if name:
            elements.append(PlyElement(name, count, tuple(properties)))

    for raw in text.splitlines():
        parts = raw.strip().split()
        if not parts:
            continue
        keyword = parts[0]
        if keyword == "format" and len(parts) >= 3:
            encoding, version = parts[1], parts[2]
        elif keyword == "comment":
            comments.append(" ".join(parts[1:]))
        elif keyword == "element" and len(parts) >= 3:
            flush()
            name = parts[1]
            count = int(parts[2])
            properties = []
        elif keyword == "property" and len(parts) >= 3:
            if parts[1] == "list" and len(parts) >= 5:
                properties.append(PlyProperty(parts[4], parts[3], count_type=parts[2]))
            else:
                properties.append(PlyProperty(parts[2], parts[1]))
        elif keyword == "end_header":
            break
    flush()

    if encoding not in ("ascii", "binary_little_endian", "binary_big_endian"):
        raise PlyError(f'Unrecognised PLY encoding "{encoding}".')
    return PlyHeader(encoding, version, tuple(elements), tuple(comments), data_offset)


# -- what kind of PLY is this -------------------------------------------------------------------

#: Spherical-harmonic DC term. Its presence is the unambiguous 3DGS marker: no point cloud and no
#: mesh writer emits it, and every 3D Gaussian Splatting exporter does.
_SPLAT_STRONG = ("f_dc_0",)

#: The per-Gaussian shape parameters. A file carrying all of these is a radiance field whatever it
#: calls its colour channels -- some trainers rename the harmonics but none drop scale and rotation.
_SPLAT_SHAPE = ("scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3")


def classify_ply(header: PlyHeader) -> tuple[str, str]:
    """Decide what a PLY actually contains. Returns ``(asset_class, reason)``.

    Order matters. A splat file also has vertices and could have faces bolted on by a converter, so
    the splat test runs first; a mesh test that ran first would classify a radiance field as
    measurable geometry, which is precisely the failure this package exists to prevent.
    """
    vertex = header.vertex
    if vertex is None:
        if header.face_count:
            return "mesh", "faces present with no vertex element -- unusual, treated as a mesh"
        return "unknown", "no vertex element"

    if vertex.has(*_SPLAT_STRONG):
        return "splat", 'vertex element carries "f_dc_0" -- spherical-harmonic radiance field'
    if vertex.has(*_SPLAT_SHAPE) and vertex.has("opacity"):
        return "splat", "vertex element carries per-Gaussian scale, rotation and opacity"
    if header.face_count > 0:
        return "mesh", f"{header.face_count} faces"
    return "point-cloud", f"{vertex.count} vertices, no faces"


def _endian(encoding: str) -> str:
    return "<" if encoding == "binary_little_endian" else ">"


def _scan_binary_bounds(
    stream: BinaryIO, element: PlyElement, encoding: str, *, max_samples: int
) -> tuple[tuple[float, ...] | None, bool]:
    axes = [element.index_of(name) for name in ("x", "y", "z")]
    if any(index is None for index in axes):
        return None, False
    fmt = _endian(encoding) + "".join(_SCALARS[p.scalar_type][0] for p in element.properties)
    record = struct.Struct(fmt)
    step = max(1, -(-element.count // max_samples))

    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    chunk_records = max(1, 4_000_000 // record.size)
    remaining = element.count
    index = 0
    while remaining > 0:
        batch = min(chunk_records, remaining)
        buffer = stream.read(batch * record.size)
        if len(buffer) < batch * record.size:
            break
        for values in record.iter_unpack(buffer):
            if index % step == 0:
                for axis in range(3):
                    value = values[axes[axis]]  # type: ignore[index]
                    if value < lo[axis]:
                        lo[axis] = value
                    if value > hi[axis]:
                        hi[axis] = value
            index += 1
        remaining -= batch
    if lo[0] == float("inf"):
        return None, False
    return (lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]), step > 1


def _scan_ascii_bounds(
    stream: BinaryIO, element: PlyElement, *, max_samples: int
) -> tuple[tuple[float, ...] | None, bool]:
    axes = [element.index_of(name) for name in ("x", "y", "z")]
    if any(index is None for index in axes):
        return None, False
    step = max(1, -(-element.count // max_samples))
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    for index in range(element.count):
        line = stream.readline()
        if not line:
            break
        if index % step:
            continue
        parts = line.split()
        try:
            for axis in range(3):
                value = float(parts[axes[axis]])  # type: ignore[index]
                if value < lo[axis]:
                    lo[axis] = value
                if value > hi[axis]:
                    hi[axis] = value
        except (IndexError, ValueError):
            continue
    if lo[0] == float("inf"):
        return None, False
    return (lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]), step > 1


def summarise(path: str | Path, *, max_samples: int = 1_000_000) -> dict[str, Any]:
    """Everything worth knowing about a PLY without converting it.

    ``max_samples`` caps the bounds scan. When it bites, ``bounds_sampled`` is set -- a sampled
    extent is a good extent for a plausibility check and a bad one for a claim of exactness, and
    the caller deserves to know which they have.
    """
    path = Path(path)
    with path.open("rb") as stream:
        head = stream.read(65536)
        header = parse_header(head)
        asset_class, reason = classify_ply(header)
        vertex = header.vertex

        summary: dict[str, Any] = {
            "encoding": header.encoding,
            "ply_version": header.version,
            "elements": {e.name: e.count for e in header.elements},
            "point_count": vertex.count if vertex else 0,
            "face_count": header.face_count,
            "classified_as": asset_class,
            "classification_reason": reason,
        }
        if header.comments:
            summary["comments"] = list(header.comments)
        if vertex is not None:
            summary["has_color"] = vertex.has("red", "green", "blue") or vertex.has("r", "g", "b")
            summary["has_normals"] = vertex.has("nx", "ny", "nz")
            summary["has_intensity"] = vertex.has("intensity") or vertex.has("scalar_Intensity")
            summary["properties"] = [p.name for p in vertex.properties]
            if asset_class == "splat":
                harmonics = sum(1 for p in vertex.properties if p.name.startswith("f_rest_"))
                summary["spherical_harmonic_coefficients"] = harmonics
                # (bands+1)^2 - 1 coefficients per colour channel, three channels.
                summary["spherical_harmonic_bands"] = (
                    int(round(((harmonics / 3 + 1) ** 0.5) - 1)) if harmonics else 0
                )

        if vertex is not None and vertex.count and vertex.is_strided:
            stream.seek(header.data_offset)
            if header.encoding == "ascii":
                bounds, sampled = _scan_ascii_bounds(stream, vertex, max_samples=max_samples)
            else:
                bounds, sampled = _scan_binary_bounds(
                    stream, vertex, header.encoding, max_samples=max_samples
                )
            if bounds:
                summary["bounds"] = list(bounds)
                summary["bounds_sampled"] = sampled
    return summary


def bounds_to_extent(bounds: Sequence[float]) -> dict[str, float]:
    """``[xmin, ymin, zmin, xmax, ymax, zmax]`` to the extent field names."""
    return {
        "xmin": bounds[0],
        "ymin": bounds[1],
        "zmin": bounds[2],
        "xmax": bounds[3],
        "ymax": bounds[4],
        "zmax": bounds[5],
    }
