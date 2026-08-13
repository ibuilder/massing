"""Content-first format detection.

Ordered from strongest evidence to weakest:

1. **Magic bytes.** ``ASTM-E57``, ``LASF``, ``glTF``, ``%PDF``, ``\\x89PNG``. Unambiguous.
2. **Header parse.** A PLY header tells you whether it holds faces, points or Gaussians. A JSON
   document tells you whether it is a tileset or a camera path.
3. **Textual shape.** An OBJ starts with ``v``/``vn``/``f`` lines; a PTX starts with two integers.
4. **Extension.** Only for formats that genuinely have no signature.

``confidence`` reflects which rung was reached, and ``reason`` names it. A downstream decision that
depends on the answer -- and the measurability gate does -- can then decide whether it trusts it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..probe import ply as ply_probe
from ..probe import structured as structured_probe

#: How many bytes the sniffer reads. Enough for any header this pipeline cares about; a PLY header
#: with three hundred splat properties is about 8 KB, so 64 KB has generous headroom.
HEAD_BYTES = 65536


@dataclass(frozen=True)
class Classification:
    """What a file is, and what makes us think so."""

    asset_class: str
    asset_format: str
    #: 1.0 for a magic number or a parsed header; 0.6 for a textual shape; 0.3 for an extension.
    confidence: float
    reason: str
    details: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def from_content(self) -> bool:
        """Whether the answer came from the bytes rather than the file name."""
        return self.confidence >= 0.6

    def __str__(self) -> str:
        return f"{self.asset_class}/{self.asset_format} ({self.confidence:.0%}) -- {self.reason}"


UNKNOWN = Classification(
    "unknown", "unknown", 0.0, "no signature, shape or known extension matched"
)

#: Extension to ``(asset_class, asset_format)`` for formats with no usable signature, and as the
#: fallback for everything else. Never consulted before the content checks.
_BY_EXTENSION: dict[str, tuple[str, str]] = {
    ".e57": ("point-cloud", "e57"),
    ".las": ("point-cloud", "las"),
    ".laz": ("point-cloud", "laz"),
    ".copc": ("point-cloud", "copc"),
    ".ply": ("point-cloud", "ply"),
    ".pts": ("point-cloud", "pts"),
    ".ptx": ("point-cloud", "ptx"),
    ".xyz": ("point-cloud", "xyz"),
    ".obj": ("mesh", "obj"),
    ".glb": ("mesh", "glb"),
    ".gltf": ("mesh", "gltf"),
    ".fbx": ("mesh", "fbx"),
    ".stl": ("mesh", "stl"),
    ".ifc": ("bim", "ifc"),
    ".ifczip": ("bim", "ifczip"),
    ".frag": ("fragments", "frag"),
    ".splat": ("splat", "splat"),
    ".ksplat": ("splat", "ksplat"),
    ".spz": ("splat", "spz"),
    ".sog": ("splat", "sog"),
    ".lcc": ("splat", "lcc"),
    ".jpg": ("image", "jpeg"),
    ".jpeg": ("image", "jpeg"),
    ".png": ("image", "png"),
    ".tif": ("raster", "tiff"),
    ".tiff": ("raster", "tiff"),
    ".mp4": ("video", "mp4"),
    ".mov": ("video", "mov"),
    ".insv": ("video", "insv"),
    ".svg": ("plan", "svg"),
    ".pdf": ("plan", "pdf"),
    ".dxf": ("plan", "dxf"),
    ".dwg": ("plan", "dwg"),
    ".json": ("camera-metadata", "json"),
    ".csv": ("telemetry", "csv"),
}


def extension_hint(path: str | Path) -> tuple[str, str] | None:
    """The extension's opinion. The weakest evidence available, and the last one consulted."""
    return _BY_EXTENSION.get(Path(path).suffix.lower())


def is_probably_text(head: bytes) -> bool:
    """A NUL byte in the first kilobyte means binary. Crude, universal, and right."""
    return b"\x00" not in head[:1024]


def _decode(head: bytes, limit: int = 8192) -> str:
    return head[:limit].decode("utf-8", errors="replace")


def classify_bytes(head: bytes, *, name: str = "") -> Classification:
    """Classify from a file's leading bytes alone.

    Split out from :func:`classify_file` so a classifier can run over an upload stream before
    anything is committed to disk, which is what the ingestion API does.
    """
    suffix = Path(name).suffix.lower() if name else ""

    # -- 1. magic numbers ------------------------------------------------------------------------
    if head[:8] == b"ASTM-E57":
        return Classification("point-cloud", "e57", 1.0, "ASTM-E57 signature")
    if head[:4] == b"LASF":
        # The compression bit lives in the point-format byte at offset 104.
        compressed = len(head) > 104 and bool(head[104] & 0x80)
        return Classification(
            "point-cloud",
            "laz" if compressed else "las",
            1.0,
            "LASF signature" + (" with the compression bit set" if compressed else ""),
        )
    if head[:4] == b"glTF":
        return Classification("mesh", "glb", 1.0, "glTF binary signature")
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return Classification("image", "png", 1.0, "PNG signature")
    if head[:3] == b"\xff\xd8\xff":
        return Classification("image", "jpeg", 1.0, "JPEG SOI marker")
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        geo = b"ModelTiepoint" in head or b"\x82\x2f" in head[:4096]
        return Classification(
            "raster",
            "geotiff" if geo else "tiff",
            1.0,
            "TIFF signature" + (" with GeoTIFF keys" if geo else ""),
        )
    if head[:4] == b"%PDF":
        return Classification("plan", "pdf", 1.0, "PDF signature")
    if head[:2] == b"AC" and head[2:6].isdigit():
        # DWG opens with its version string in the clear -- "AC1032" is AutoCAD 2018. That is a
        # real signature, so a .dwg renamed to .dxf is still recognised as the thing it is rather
        # than handed to a text parser that will find nothing and say so unhelpfully.
        version = head[:6].decode("ascii", errors="replace")
        return Classification("plan", "dwg", 1.0, f"DWG version marker {version}")
    if head[:2] == b"\x1f\x8b" and suffix == ".spz":
        return Classification("splat", "spz", 0.9, "gzip container with a .spz extension")
    if head[:4] == b"PK\x03\x04":
        if suffix == ".sog":
            return Classification("splat", "sog", 0.9, "zip container with a .sog extension")
        if suffix == ".ifczip":
            return Classification("bim", "ifczip", 0.9, "zip container with an .ifczip extension")
        return Classification("unknown", "unknown", 0.4, "zip container of unstated contents")
    if len(head) > 8 and head[4:8] == b"ftyp":
        brand = head[8:12].decode("ascii", errors="replace").strip()
        fmt = "mov" if brand.startswith("qt") else ("insv" if suffix == ".insv" else "mp4")
        return Classification("video", fmt, 1.0, f'ISO base media file, brand "{brand}"')

    # -- 2. parsed headers -----------------------------------------------------------------------
    if head[:3] == b"ply" and head[3:4] in (b"\n", b"\r"):
        try:
            header = ply_probe.parse_header(head)
        except ply_probe.PlyError as thrown:
            return Classification(
                "point-cloud", "ply", 0.5, f"PLY magic but unreadable header: {thrown}"
            )
        asset_class, reason = ply_probe.classify_ply(header)
        return Classification(
            asset_class,
            "ply",
            1.0,
            f"PLY header: {reason}",
            details={
                "encoding": header.encoding,
                "elements": {e.name: e.count for e in header.elements},
            },
        )

    if not is_probably_text(head):
        hint = _BY_EXTENSION.get(suffix)
        if hint:
            return Classification(*hint, 0.3, f'binary, classified by the "{suffix}" extension')
        return Classification("unknown", "unknown", 0.1, "binary with no recognised signature")

    text = _decode(head)
    stripped = text.lstrip()

    if "ISO-10303-21" in text[:200]:
        schema = ""
        marker = text.find("FILE_SCHEMA")
        if marker != -1:
            segment = text[marker : marker + 200]
            start, end = segment.find("'"), segment.find("'", segment.find("'") + 1)
            if start != -1 and end != -1:
                schema = segment[start + 1 : end]
        if schema.upper().startswith("IFC"):
            return Classification("bim", "ifc", 1.0, f"STEP physical file, schema {schema}")
        return Classification("bim", "ifc", 0.7, "STEP physical file with no IFC schema declared")

    if stripped[:1] in ("{", "["):
        try:
            document = json.loads(text) if len(head) < HEAD_BYTES else None
        except ValueError:
            document = None
        if document is not None:
            shape = structured_probe.identify(document)
            mapping = {
                "tileset": (
                    "tileset",
                    "tileset-json",
                    "3D Tiles tileset -- root and geometricError",
                ),
                "gltf": ("mesh", "gltf", "glTF JSON -- asset and scenes"),
                "earth-studio": ("camera-metadata", "json", "Earth Studio export -- cameraFrames"),
                "pose-array": ("camera-metadata", "json", "an array of camera poses"),
                "nodes-graph": ("camera-metadata", "json", "a node/edge graph"),
            }
            if shape in mapping:
                asset_class, asset_format, reason = mapping[shape]
                return Classification(asset_class, asset_format, 1.0, reason)
        return Classification("camera-metadata", "json", 0.5, "JSON of an unrecognised shape")

    if stripped[:4].lower() == "<svg" or (
        "<svg" in stripped[:512].lower() and stripped[:5] == "<?xml"
    ):
        return Classification("plan", "svg", 1.0, "SVG root element")

    if _looks_like_obj(text):
        return Classification("mesh", "obj", 0.8, "OBJ vertex and face directives")
    if _looks_like_dxf(text):
        return Classification("plan", "dxf", 0.8, "DXF section markers")
    if suffix == ".ptx" or _looks_like_ptx(text):
        return Classification("point-cloud", "ptx", 0.7, "PTX grid header followed by a pose block")
    if suffix in (".pts", ".xyz", ".txt", ".asc") or _looks_like_point_text(text):
        fmt = {".pts": "pts", ".xyz": "xyz"}.get(suffix, "xyz")
        return Classification("point-cloud", fmt, 0.6, "rows of three or more numbers")

    hint = _BY_EXTENSION.get(suffix)
    if hint:
        return Classification(*hint, 0.3, f'text, classified by the "{suffix}" extension')
    return UNKNOWN


def _looks_like_obj(text: str) -> bool:
    directives = 0
    for line in text.splitlines()[:400]:
        keyword = line.split(" ", 1)[0]
        if keyword in ("v", "vn", "vt", "f", "usemtl", "mtllib", "g", "o"):
            directives += 1
    return directives >= 8


def _looks_like_dxf(text: str) -> bool:
    head = text[:2048].upper()
    return "SECTION" in head and ("HEADER" in head or "ENTITIES" in head or "AUTOCAD" in head)


def _looks_like_ptx(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines()[:12] if line.strip()]
    if len(lines) < 10:
        return False
    if not (lines[0].isdigit() and lines[1].isdigit()):
        return False
    # Lines 3-10 of a PTX block are the scanner position, its three axes, and a 4x4 matrix.
    for line in lines[2:6]:
        parts = line.replace(",", " ").split()
        if len(parts) < 3:
            return False
        try:
            [float(part) for part in parts]
        except ValueError:
            return False
    return True


def _looks_like_point_text(text: str) -> bool:
    numeric_rows = 0
    for line in text.splitlines()[1:200]:
        parts = line.replace(",", " ").split()
        if len(parts) < 3:
            continue
        try:
            [float(part) for part in parts[:3]]
        except ValueError:
            continue
        numeric_rows += 1
    return numeric_rows >= 20


def classify_file(path: str | Path) -> Classification:
    """Classify a file on disk. The entry point everything else uses."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"No such file: {path}")
    with path.open("rb") as stream:
        head = stream.read(HEAD_BYTES)

    result = classify_bytes(head, name=path.name)

    # A JSON document larger than the sniff window could not be parsed above. Re-read it properly
    # rather than reporting the weaker answer, because a 20 MB tileset is entirely ordinary.
    if (
        result.asset_format == "json"
        and result.confidence <= 0.5
        and path.suffix.lower() == ".json"
    ):
        try:
            summary = structured_probe.summarise(path)
        except structured_probe.StructuredError:
            return result
        shape = summary.get("json_shape")
        if shape == "tileset":
            return Classification("tileset", "tileset-json", 1.0, "3D Tiles tileset (full parse)")
        if shape == "gltf":
            return Classification("mesh", "gltf", 1.0, "glTF JSON (full parse)")
        if shape == "earth-studio":
            return Classification(
                "camera-metadata", "json", 1.0, "Earth Studio export (full parse)"
            )

    if result.asset_class == "unknown":
        hint = extension_hint(path)
        if hint:
            return Classification(*hint, 0.3, f'classified by the "{path.suffix}" extension alone')
    return result
