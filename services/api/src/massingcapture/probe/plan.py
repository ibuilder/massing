"""Floor plans: PDF and DXF, read without rasterising either.

Both formats classified and neither was probed, so a drawing arrived in a project with no size, no
units and nothing to calibrate against -- which for the format most floor plans are actually
delivered in is a hole straight through the plan-linked walkthrough.

Rasterising is not the interesting part and is not free. What is interesting is cheap:

- **DXF** is a plain group-code text format, and its ``HEADER`` section carries ``$EXTMIN`` and
  ``$EXTMAX`` -- the drawing's extents in its own units -- alongside ``$INSUNITS``, which names
  those units. That is a scaled, placeable floor plan out of a text scan, the same trade as reading
  an E57's index instead of its points.
- **PDF** carries ``/MediaBox`` per page: the sheet size in points, 72 to the inch. A sheet size and
  a stated drawing scale give metres per point directly, so an A1 at 1:100 needs no image to
  calibrate. Whether the page is vector or a scan matters too, and is visible in the same pass.

Standard library only, like every other probe. Where a PDF compresses its page tree into object
streams -- legal, and increasingly common -- this says so rather than guessing, because a page count
of zero reported confidently is worse than a page count reported as unknown.
"""

from __future__ import annotations

import re
import zlib
from pathlib import Path
from typing import Any

# -- DXF ------------------------------------------------------------------------------------------

#: ``$INSUNITS`` values, from the DXF reference. Metres per unit, and the name.
#:
#: 0 is "unitless", which is not the same as metres and must not be reported as such: a drawing that
#: declines to state its units is one a human has to look at, and quietly calling it metres is how a
#: 1:100 sheet becomes a hundred-metre room.
_INSUNITS: dict[int, tuple[str, float | None]] = {
    0: ("unitless", None),
    1: ("in", 0.0254),
    2: ("ft", 0.3048),
    3: ("mi", 1609.344),
    4: ("mm", 0.001),
    5: ("cm", 0.01),
    6: ("m", 1.0),
    7: ("km", 1000.0),
    8: ("uin", 0.0254e-6),
    9: ("mil", 0.0254e-3),
    10: ("yd", 0.9144),
    11: ("angstrom", 1e-10),
    12: ("nm", 1e-9),
    13: ("um", 1e-6),
    14: ("dm", 0.1),
    15: ("dam", 10.0),
    16: ("hm", 100.0),
    17: ("gm", 1e9),
    18: ("au", 1.495978707e11),
    19: ("ly", 9.4607304725808e15),
    20: ("pc", 3.0856775814913673e16),
}

#: Entities worth counting for a plan. Anything else lands in ``other``.
_PLAN_ENTITIES = frozenset(
    {"LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "TEXT", "MTEXT", "INSERT", "HATCH",
     "DIMENSION", "SPLINE", "ELLIPSE", "SOLID", "POINT"}
)  # fmt: skip


def _dxf_pairs(text: str):
    """Yield ``(group_code, value)`` from DXF's two-lines-per-item format.

    The whole format is a code on one line and its value on the next, forever. Malformed pairs are
    skipped rather than raised on: a drawing exported by a tool with an off-by-one is still worth
    the extents it does carry.
    """
    lines = text.splitlines()
    for index in range(0, len(lines) - 1, 2):
        code = lines[index].strip()
        if not code.lstrip("-").isdigit():
            continue
        yield int(code), lines[index + 1].strip()


def summarise_dxf(path: str | Path, *, limit: int = 64 * 1024 * 1024) -> dict[str, Any]:
    """Extents, units and an entity census from a DXF's text.

    ``limit`` caps the read: a 400 MB site drawing is not worth scanning to count its lines, and a
    truncated scan still gets the header, which is at the top and is the part that matters.
    """
    path = Path(path)
    size = path.stat().st_size
    raw = path.read_bytes()[:limit]
    text = raw.decode("utf-8", errors="replace")

    summary: dict[str, Any] = {"plan_format": "dxf", "size_bytes": size}
    if size > limit:
        summary["scan_truncated"] = (
            f"Read the first {limit // 1_048_576} MB of {size / 1_048_576:.0f} MB. "
            "Header values are complete; the entity census is not."
        )

    variable = None
    pending: dict[str, dict[int, float]] = {}
    census: dict[str, int] = {}
    section = None
    layers: set[str] = set()

    for code, value in _dxf_pairs(text):
        if code == 0:
            if value == "SECTION":
                section = "?"
            elif value == "ENDSEC":
                section = None
            elif section == "ENTITIES":
                name = value.upper()
                key = name if name in _PLAN_ENTITIES else "other"
                census[key] = census.get(key, 0) + 1
            variable = None
        elif code == 2 and section == "?":
            section = value.upper()
        elif code == 2 and section == "TABLES":
            pass
        elif code == 8 and section == "ENTITIES" and len(layers) < 500:
            layers.add(value)
        elif code == 9:
            variable = value.upper()
        elif variable in ("$EXTMIN", "$EXTMAX", "$LIMMIN", "$LIMMAX") and code in (10, 20, 30):
            try:
                pending.setdefault(variable, {})[code] = float(value)
            except ValueError:
                continue
        elif variable == "$INSUNITS" and code == 70:
            try:
                unit_code = int(value)
            except ValueError:
                continue
            name, metres = _INSUNITS.get(unit_code, ("unknown", None))
            summary["drawing_unit"] = name
            if metres is not None:
                summary["drawing_unit_metres"] = metres
            variable = None
        elif variable == "$ACADVER" and code == 1:
            summary["dxf_version"] = value
            variable = None

    low, high = pending.get("$EXTMIN"), pending.get("$EXTMAX")
    if low and high and {10, 20} <= low.keys() and {10, 20} <= high.keys():
        # A drawing that has never been zoom-extented carries the sentinel 1e20 extents AutoCAD
        # initialises with. Reporting those as an extent puts a floor plan the size of the solar
        # system on the project, so they are refused rather than passed on.
        values = [low[10], low[20], high[10], high[20]]
        if all(abs(value) < 1e12 for value in values) and high[10] > low[10]:
            # Six values when the drawing states a Z range, four when it does not. A flat plan
            # really is flat, and inventing zmin=zmax=0 would place it on the ground floor of
            # whatever project it joined rather than on no floor in particular.
            if 30 in low and 30 in high and abs(low[30]) < 1e12 and abs(high[30]) < 1e12:
                summary["bounds"] = [low[10], low[20], low[30], high[10], high[20], high[30]]
            else:
                summary["bounds"] = [low[10], low[20], high[10], high[20]]
            summary["width"] = high[10] - low[10]
            summary["height"] = high[20] - low[20]
            summary["bounds_sampled"] = False
            metres = summary.get("drawing_unit_metres")
            if metres:
                summary["width_metres"] = summary["width"] * metres
                summary["height_metres"] = summary["height"] * metres

    if census:
        summary["entity_census"] = dict(sorted(census.items(), key=lambda kv: -kv[1])[:20])
        summary["entity_count"] = sum(census.values())
    if layers:
        summary["layers"] = sorted(layers)[:200]
        summary["layer_count"] = len(layers)
    return summary


# -- PDF ------------------------------------------------------------------------------------------

_MEDIABOX = re.compile(rb"/MediaBox\s*\[\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\]")
_PAGE_COUNT = re.compile(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", re.DOTALL)
_PAGE_OBJECT = re.compile(rb"/Type\s*/Page[^s]")
_ROTATE = re.compile(rb"/Rotate\s+(-?\d+)")
_PRODUCER = re.compile(rb"/Producer\s*\(([^)]{0,200})\)")
_CREATOR = re.compile(rb"/Creator\s*\(([^)]{0,200})\)")
_OBJECT_STREAM = re.compile(rb"/Type\s*/ObjStm")

#: PostScript points per inch. The unit every PDF box is in, and the reason a sheet size is exact.
POINTS_PER_INCH = 72.0

#: Known sheet sizes in points, to the nearest millimetre, for naming what came back.
_SHEET_SIZES: dict[str, tuple[float, float]] = {
    "A4": (595.28, 841.89),
    "A3": (841.89, 1190.55),
    "A2": (1190.55, 1683.78),
    "A1": (1683.78, 2383.94),
    "A0": (2383.94, 3370.39),
    "ANSI A": (612.0, 792.0),
    "ANSI B": (792.0, 1224.0),
    "ANSI C": (1224.0, 1584.0),
    "ANSI D": (1584.0, 2448.0),
    "ANSI E": (2448.0, 3168.0),
    "ARCH D": (1728.0, 2592.0),
    "ARCH E": (2592.0, 3456.0),
}


#: Drawn operators below which a page is not a drawing. A scanned sheet places one image with a
#: handful of operators; the least ambitious real CAD export is hundreds. Twenty separates them with
#: room on both sides, and the counts are reported so nobody has to trust the threshold.
_VECTOR_OPERATOR_FLOOR = 20

#: PDF path-construction and painting operators, as whole tokens. Matched with a boundary on each
#: side because ``l`` and ``c`` are single letters and appear inside every other word in a stream.
_PATH_OPERATOR = re.compile(rb"(?:^|[\s\]>])(?:re|[lcvym]|s|S|f|F|B|W)(?=[\s\[<]|$)")

#: Text-showing operators. Counted alongside paths, because "is this vector" is not the same
#: question as "does this have paths": a drawing that is all dimension strings and room labels has
#: barely a path in it and is entirely selectable, searchable, measurable content -- and a title
#: block is often the only vector thing on an otherwise scanned sheet.
_TEXT_OPERATOR = re.compile(rb"(?:^|[\s\]>)])(?:Tj|TJ|'|\")(?=[\s\[<(]|$)")


def _count_path_operators(body: bytes, *, sample: int = 2 * 1024 * 1024) -> int:
    """How many path operators the content streams contain."""
    return len(_PATH_OPERATOR.findall(body[:sample]))


def _count_text_operators(body: bytes, *, sample: int = 2 * 1024 * 1024) -> int:
    """How many text-showing operators the content streams contain."""
    return len(_TEXT_OPERATOR.findall(body[:sample]))


def sheet_name(width: float, height: float, *, tolerance: float = 6.0) -> str | None:
    """The standard sheet a page size matches, in either orientation. ``None`` for a custom size."""
    short, long = sorted((width, height))
    for name, (sheet_short, sheet_long) in _SHEET_SIZES.items():
        if abs(short - sheet_short) <= tolerance and abs(long - sheet_long) <= tolerance:
            return name
    return None


def _decompressed_streams(raw: bytes, *, budget: int = 4 * 1024 * 1024) -> bytes:
    """Inflate the Flate-compressed object streams, so a modern PDF's page tree is readable.

    PDF 1.5 lets a writer pack object definitions -- including page dictionaries -- into compressed
    ``/ObjStm`` streams, and every current authoring tool does. Without this the regexes above find
    nothing in a file that is perfectly well formed, which reads as "this PDF has no pages".
    """
    out = bytearray()
    for match in re.finditer(rb"stream\r?\n", raw):
        if len(out) >= budget:
            break
        start = match.end()
        end = raw.find(b"endstream", start)
        if end == -1:
            continue
        try:
            out += zlib.decompress(raw[start:end].rstrip(b"\r\n"))
        except zlib.error:  # noqa: PERF203
            continue
    return bytes(out)


def summarise_pdf(path: str | Path, *, head: int = 8 * 1024 * 1024) -> dict[str, Any]:
    """Page count, sheet sizes and whether the drawing is vector or a scan.

    Reads the raw file and, when the page tree turns out to be inside compressed object streams,
    the inflated contents too. Not a PDF parser: it looks for the handful of keys that answer "what
    size is this sheet", and reports honestly when a file hides them somewhere this cannot reach.
    """
    path = Path(path)
    size = path.stat().st_size
    raw = path.read_bytes()[:head]

    summary: dict[str, Any] = {"plan_format": "pdf", "size_bytes": size}
    version = re.match(rb"%PDF-(\d+\.\d+)", raw[:16])
    if version:
        summary["pdf_version"] = version.group(1).decode("ascii")

    # Inflate up front rather than on demand. Page dictionaries hide in object streams and content
    # streams are compressed as a matter of course, so almost nothing worth finding is in the raw
    # bytes of a file written this decade.
    inflated = _decompressed_streams(raw)
    searchable = raw + inflated
    if inflated:
        summary["compressed_streams"] = True
    if _OBJECT_STREAM.search(raw):
        summary["object_streams"] = True

    counted = _PAGE_COUNT.search(searchable)
    if counted:
        summary["page_count"] = int(counted.group(1))
    else:
        found = len(_PAGE_OBJECT.findall(searchable))
        if found:
            summary["page_count"] = found
        else:
            summary["page_count_note"] = (
                "The page tree is not reachable without a full PDF parser -- probably an "
                "encrypted or linearised file. Page sizes below, if any, are what was findable."
            )

    pages: list[dict[str, Any]] = []
    for match in _MEDIABOX.finditer(searchable):
        x0, y0, x1, y1 = (float(value) for value in match.groups())
        width, height = abs(x1 - x0), abs(y1 - y0)
        if width <= 0 or height <= 0:
            continue
        page: dict[str, Any] = {
            "width_points": round(width, 2),
            "height_points": round(height, 2),
            "width_mm": round(width / POINTS_PER_INCH * 25.4, 1),
            "height_mm": round(height / POINTS_PER_INCH * 25.4, 1),
        }
        named = sheet_name(width, height)
        if named:
            page["sheet"] = named
        page["orientation"] = "landscape" if width > height else "portrait"
        pages.append(page)
        if len(pages) >= 32:
            break

    if pages:
        summary["pages"] = pages
        first = pages[0]
        summary["width_points"] = first["width_points"]
        summary["height_points"] = first["height_points"]
        if "sheet" in first:
            summary["sheet"] = first["sheet"]

    rotation = _ROTATE.search(searchable)
    if rotation:
        summary["rotation"] = int(rotation.group(1)) % 360

    # Vector or scan, which decides whether the drawing can be measured off at all or only traced
    # over. A CAD export is thousands of path operators; a scan is an image XObject and about four
    # operators to place it. Counted on the inflated content, because a content stream is compressed
    # in every file anyone actually sends.
    has_image = b"/Subtype /Image" in searchable or b"/Subtype/Image" in searchable
    paths = _count_path_operators(searchable)
    texts = _count_text_operators(searchable)
    operators = paths + texts
    summary["has_raster_content"] = bool(has_image)
    summary["path_operators"] = paths
    summary["text_operators"] = texts
    if not has_image and operators:
        # Nothing raster in the file at all, and something drawn: there is no other thing it can be.
        summary["content"] = "vector"
    elif has_image and operators >= _VECTOR_OPERATOR_FLOOR:
        # Both. A drawing with a site photo or a logo in the title block is still a drawing, and
        # this is the only case where the threshold is doing real work rather than confirming a
        # foregone conclusion.
        summary["content"] = "vector"
        summary["content_note"] = (
            "Vector content with raster images in it -- a title block or an inset photograph. "
            "Measurable where it is drawn and not where it is placed."
        )
    elif has_image:
        summary["content"] = "raster"
        summary["content_note"] = (
            "This looks like a scanned drawing. Its dimensions are the sheet's, not the "
            "building's -- calibrate against a known length before measuring anything off it."
        )
    else:
        # Said rather than guessed. An encrypted PDF, or one whose streams use a filter this does
        # not inflate, reaches here with nothing counted, and "vector" would be a coin toss.
        summary["content"] = "unknown"
        summary["content_note"] = (
            "Nothing legible in the content streams -- possibly encrypted, or using a compression "
            "filter this reader does not inflate. Whether it is vector or a scan is not known."
        )

    for key, pattern in (("producer", _PRODUCER), ("creator", _CREATOR)):
        found_text = pattern.search(searchable)
        if found_text:
            summary[key] = found_text.group(1).decode("latin-1", errors="replace").strip()

    return summary


# -- DWG ------------------------------------------------------------------------------------------

#: The six-byte version string every DWG starts with, and the release that wrote it. Nothing else
#: in the format is readable without a licensed specification, and this much is worth saying: it is
#: the difference between "convert this" and "convert this with something that handles R2018".
_DWG_VERSIONS: dict[str, str] = {
    "AC1006": "R10",
    "AC1009": "R11/R12",
    "AC1012": "R13",
    "AC1014": "R14",
    "AC1015": "AutoCAD 2000",
    "AC1018": "AutoCAD 2004",
    "AC1021": "AutoCAD 2007",
    "AC1024": "AutoCAD 2010",
    "AC1027": "AutoCAD 2013",
    "AC1032": "AutoCAD 2018",
}


def summarise_dwg(path: str | Path) -> dict[str, Any]:
    """What can be established about a DWG without a licensed specification: which one it is.

    DWG is proprietary and undocumented, and guessing at its internals is how a reader produces a
    plausible drawing that is wrong. What it does carry in the clear is its version, and that is
    genuinely actionable -- it names what a converter has to support.
    """
    path = Path(path)
    with path.open("rb") as stream:
        head = stream.read(6)
    version = head.decode("ascii", errors="replace")
    summary: dict[str, Any] = {
        "plan_format": "dwg",
        "size_bytes": path.stat().st_size,
        "dwg_version": version,
        "note": (
            "DWG is proprietary and is not read here. Export or convert to DXF -- "
            "the ODA File Converter and LibreDWG both do it -- and everything else follows."
        ),
    }
    release = _DWG_VERSIONS.get(version)
    if release:
        summary["autocad_release"] = release
    else:
        summary["note"] = (
            f"Not a version marker this recognises ({version!r}). "
            "Either a DWG newer than this build knows, or not a DWG."
        )
    return summary


def summarise(path: str | Path) -> dict[str, Any]:
    """Dispatch on the signature, not on the extension. ``.dxf`` files are renamed all the time."""
    path = Path(path)
    with path.open("rb") as stream:
        head = stream.read(8)
    if head.startswith(b"%PDF-"):
        return summarise_pdf(path)
    if head[:2] == b"AC" and head[2:6].isdigit():
        return summarise_dwg(path)
    return summarise_dxf(path)
