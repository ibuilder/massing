"""IFC, read as the STEP text it is.

Not a parser -- IfcOpenShell exists and is behind the ``ifc`` adapter for anyone who needs geometry.
This reads the header and takes a census, because two facts from an IFC unlock most of the
plan-linked walkthrough workflow and neither needs a geometry kernel:

- **The schema and the length unit.** An IFC in millimetres registered as though it were in metres
  is a building a thousand times too big, and the unit is sitting in ``IFCSIUNIT`` in plain text.
- **The storeys.** ``IFCBUILDINGSTOREY`` carries a name, a GlobalId and an elevation. That is a
  ``FloorRecord`` each, which is the spine every scan position, pano node and plan hangs off. A
  project that reads them gets its floors for free instead of asking a user to type them.

Also here: That Open Fragments (``.frag``). Those are FlatBuffers with no self-describing header, so
the honest thing is to report what can be established -- that it is binary, its size, and the IFC it
claims to have come from if a sidecar says so -- rather than to invent a parse.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_STEP_MAGIC = "ISO-10303-21"

#: Prefix multipliers from ``IfcSIPrefix``, as metres per unit when applied to ``METRE``.
_SI_PREFIX: dict[str, float] = {
    "EXA": 1e18, "PETA": 1e15, "TERA": 1e12, "GIGA": 1e9, "MEGA": 1e6, "KILO": 1e3,
    "HECTO": 1e2, "DECA": 1e1, "DECI": 1e-1, "CENTI": 1e-2, "MILLI": 1e-3,
    "MICRO": 1e-6, "NANO": 1e-9, "PICO": 1e-12, "FEMTO": 1e-15, "ATTO": 1e-18,
}  # fmt: skip

#: Above this, the census is skipped. A 400 MB federated model is worth indexing properly with
#: IfcOpenShell rather than by scanning text, and a probe should not take a minute.
DEFAULT_DEEP_LIMIT = 128 * 1024 * 1024

_STOREY = re.compile(r"^#(\d+)\s*=\s*IFCBUILDINGSTOREY\s*\(", re.IGNORECASE)
_ENTITY = re.compile(r"^#\d+\s*=\s*([A-Za-z0-9_]+)\s*\(")
_SI_UNIT = re.compile(
    r"IFCSIUNIT\s*\(\s*\*\s*,\s*\.([A-Z]+)\.\s*,\s*([$.A-Z]*)\s*,\s*\.([A-Z]+)\.", re.IGNORECASE
)
_CONVERSION_UNIT = re.compile(
    r"IFCCONVERSIONBASEDUNIT\s*\(\s*#\d+\s*,\s*\.([A-Z]+)\.\s*,\s*'([^']*)'", re.IGNORECASE
)
_UNICODE_ESCAPE = re.compile(r"\\X2\\((?:[0-9A-Fa-f]{4})+)\\X0\\")


class IfcError(ValueError):
    """A file claimed to be IFC-SPF and did not read as one."""


def decode_step_string(raw: str) -> str:
    """Decode a STEP string literal: doubled quotes, and ``\\X2\\...\\X0\\`` unicode runs.

    Names in a real model are full of them -- any accented character in a room name arrives this
    way -- and a floor called ``\\X2\\00C9\\X0\\tage 1`` in a UI is a bug report.
    """
    text = raw.replace("''", "'")
    text = _UNICODE_ESCAPE.sub(
        lambda match: "".join(
            chr(int(match.group(1)[i : i + 4], 16)) for i in range(0, len(match.group(1)), 4)
        ),
        text,
    )
    return text.replace("\\S\\", "").replace("\\\\", "\\")


def split_step_attributes(body: str) -> list[str]:
    """Split a STEP attribute list on top-level commas.

    Naive splitting breaks on the first name containing a comma and on every nested aggregate, both
    of which are routine. Quoted strings and parentheses are tracked so they do not.
    """
    parts: list[str] = []
    depth = 0
    in_string = False
    current: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if in_string:
            if char == "'":
                if index + 1 < len(body) and body[index + 1] == "'":
                    current.append("''")
                    index += 2
                    continue
                in_string = False
            current.append(char)
        elif char == "'":
            in_string = True
            current.append(char)
        elif char in "([":
            depth += 1
            current.append(char)
        elif char in ")]":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current).strip())
    return parts


def _string_attribute(value: str) -> str | None:
    value = value.strip()
    if value.startswith("'") and value.endswith("'") and len(value) >= 2:
        return decode_step_string(value[1:-1])
    return None


def _float_attribute(value: str) -> float | None:
    value = value.strip()
    if value in ("$", "*", ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class IfcStorey:
    """One ``IFCBUILDINGSTOREY``: a floor, straight out of the model."""

    step_id: int
    global_id: str | None
    name: str | None
    long_name: str | None
    #: In the model's own length unit, not metres. Convert with ``length_unit_metres``.
    elevation: float | None


@dataclass(frozen=True)
class IfcGeoreference:
    """``IfcMapConversion`` and its ``IfcProjectedCRS``: where the model actually is.

    Modern IFC keeps vertices near the origin -- which is right, because a model authored at
    six-digit survey coordinates renders as a jittering mess -- and states the survey position
    separately, as a conversion from the model's engineering frame to a named projected CRS. Both
    halves are needed and neither is guessable from the geometry: a model whose coordinates are
    small is not a model at the origin, it is a model that told you where it is somewhere else.

    Without this, a BIM and a georeferenced scan of the same building cannot be put in one frame
    even though the IFC says exactly how.
    """

    #: The projected CRS name as the file states it, e.g. ``EPSG:32760``. Not resolved or validated
    #: -- an authoring tool writes what it likes here, and a guess is worse than the file's own word.
    crs: str | None
    crs_description: str | None
    geodetic_datum: str | None
    #: Eastings, northings and height **in the map unit**, exactly as the file states them. Not
    #: normalised, because the audit trail is the file's own numbers; :meth:`origin_metres` does the
    #: conversion where a caller wants one.
    eastings: float
    northings: float
    orthogonal_height: float
    #: Rotation of the model's +X axis within the map grid, anticlockwise from grid east.
    rotation_degrees: float
    scale: float
    #: ``IfcProjectedCRS.MapUnit``, resolved. Millimetres far more often than anyone expects, which
    #: is how an easting of 729,013,348 turns out to be a perfectly ordinary UTM coordinate 729 km
    #: across the zone. Reporting the number without the unit is the whole failure this guards.
    map_unit: str | None = None
    map_unit_metres: float | None = None

    def origin_metres(self) -> tuple[float, float, float]:
        """The map origin in metres, whatever the file chose to state it in."""
        factor = self.map_unit_metres if self.map_unit_metres else 1.0
        return (self.eastings * factor, self.northings * factor, self.orthogonal_height * factor)

    def matrix(self, model_unit_metres: float = 1.0) -> tuple[float, ...]:
        """The conversion as a column-major 4x4, **metres in and metres out**.

        Source frame is the model's engineering coordinates; target is :attr:`crs`. Naming both is
        the point -- a matrix without its two frames is a number nobody can check, and one whose two
        ends are in different units is worse, because it composes cleanly and is wrong.

        Two unit conversions ride in here and they are not the same one: the model's length unit
        scales the input, the map unit scales the output. They agree in most files and in none of
        the interesting ones.

        In the file's own terms ``E = E0 + s(X*a - Y*b)``, with ``X`` in model units and ``E`` in
        map units. Substituting metres on both sides leaves the linear part as
        ``s * map_unit / model_unit`` and the translation as ``E0 * map_unit`` -- which is the whole
        derivation, and it cancels to plain ``s`` whenever a model is georeferenced in the unit it
        was authored in.
        """
        angle = math.radians(self.rotation_degrees)
        map_factor = self.map_unit_metres if self.map_unit_metres else 1.0
        linear = self.scale * map_factor / (model_unit_metres or 1.0)
        cos, sin = math.cos(angle) * linear, math.sin(angle) * linear
        east, north, height = self.origin_metres()
        # Column-major: translation occupies 12, 13, 14.
        return (
            cos, sin, 0.0, 0.0,
            -sin, cos, 0.0, 0.0,
            0.0, 0.0, linear, 0.0,
            east, north, height, 1.0,
        )  # fmt: skip


@dataclass(frozen=True)
class IfcHeader:
    schema: str | None
    description: tuple[str, ...]
    file_name: str | None
    timestamp: str | None
    authors: tuple[str, ...]
    organisations: tuple[str, ...]
    preprocessor: str | None
    originating_system: str | None


def parse_header(text: str) -> IfcHeader:
    """Read the ``HEADER`` section of a STEP physical file."""
    if _STEP_MAGIC not in text[:64]:
        raise IfcError('Not a STEP physical file -- no "ISO-10303-21" marker.')
    end = text.upper().find("ENDSEC;")
    header_text = text[:end] if end != -1 else text

    def entry(name: str) -> list[str] | None:
        match = re.search(rf"{name}\s*\((.*?)\)\s*;", header_text, re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        return split_step_attributes(match.group(1))

    schema = None
    schema_parts = entry("FILE_SCHEMA")
    if schema_parts:
        found = re.search(r"'([^']+)'", schema_parts[0])
        if found:
            schema = found.group(1)

    description = ()
    authors: tuple[str, ...] = ()
    organisations: tuple[str, ...] = ()
    preprocessor = originating = None
    file_name = timestamp = None

    description_parts = entry("FILE_DESCRIPTION")
    if description_parts:
        description = tuple(
            decode_step_string(value) for value in re.findall(r"'([^']*)'", description_parts[0])
        )

    name_parts = entry("FILE_NAME")
    if name_parts and len(name_parts) >= 2:
        file_name = _string_attribute(name_parts[0])
        timestamp = _string_attribute(name_parts[1])
        if len(name_parts) >= 3:
            authors = tuple(decode_step_string(v) for v in re.findall(r"'([^']*)'", name_parts[2]))
        if len(name_parts) >= 4:
            organisations = tuple(
                decode_step_string(v) for v in re.findall(r"'([^']*)'", name_parts[3])
            )
        if len(name_parts) >= 5:
            preprocessor = _string_attribute(name_parts[4])
        if len(name_parts) >= 6:
            originating = _string_attribute(name_parts[5])

    return IfcHeader(
        schema=schema,
        description=description,
        file_name=file_name,
        timestamp=timestamp,
        authors=authors,
        organisations=organisations,
        preprocessor=preprocessor,
        originating_system=originating,
    )


def _parse_storey(line: str, step_id: int) -> IfcStorey:
    body = line[line.index("(") + 1 : line.rindex(")")]
    attributes = split_step_attributes(body)

    def at(index: int) -> str:
        return attributes[index] if index < len(attributes) else "$"

    return IfcStorey(
        step_id=step_id,
        global_id=_string_attribute(at(0)),
        name=_string_attribute(at(2)),
        long_name=_string_attribute(at(7)),
        elevation=_float_attribute(at(9)),
    )


_MAP_CONVERSION = re.compile(r"^#\d+\s*=\s*IFCMAPCONVERSION\s*\((.*)\)\s*;?\s*$", re.IGNORECASE)
_PROJECTED_CRS = re.compile(r"^#(\d+)\s*=\s*IFCPROJECTEDCRS\s*\((.*)\)\s*;?\s*$", re.IGNORECASE)
_UNIT_LINE = re.compile(r"^#(\d+)\s*=\s*(IFCSIUNIT|IFCCONVERSIONBASEDUNIT)\s*\(", re.IGNORECASE)
_REFERENCE = re.compile(r"#(\d+)")


def parse_georeference(lines: Iterable[str]) -> IfcGeoreference | None:
    """Pull the map conversion, and the CRS it points at, out of raw STEP lines.

    Done textually rather than through IfcOpenShell because georeferencing is exactly the fact a
    bare installation should not have to install a geometry kernel to learn: it is seven numbers and
    a name near the top of the file, and every deployment can read it.
    """
    conversion: list[str] | None = None
    projected: dict[int, list[str]] = {}
    units: dict[int, str] = {}
    for line in lines:
        stripped = line.lstrip()
        match = _MAP_CONVERSION.match(stripped)
        if match:
            conversion = split_step_attributes(match.group(1))
            continue
        match = _PROJECTED_CRS.match(stripped)
        if match:
            projected[int(match.group(1))] = split_step_attributes(match.group(2))
            continue
        match = _UNIT_LINE.match(stripped)
        if match:
            units[int(match.group(1))] = stripped

    if conversion is None or len(conversion) < 5:
        return None

    # IfcMapConversion(SourceCRS, TargetCRS, Eastings, Northings, OrthogonalHeight,
    #                  XAxisAbscissa, XAxisOrdinate, Scale)
    eastings = _float_attribute(conversion[2])
    northings = _float_attribute(conversion[3])
    height = _float_attribute(conversion[4])
    if eastings is None or northings is None:
        return None

    abscissa = _float_attribute(conversion[5]) if len(conversion) > 5 else None
    ordinate = _float_attribute(conversion[6]) if len(conversion) > 6 else None
    scale = _float_attribute(conversion[7]) if len(conversion) > 7 else None
    # Both axis components absent means "no rotation", which is a real and common answer. Only one
    # present is a malformed pair, and treating it as zero rotation would silently mis-place the
    # model rather than say so.
    if abscissa is None and ordinate is None:
        rotation = 0.0
    elif abscissa is None or ordinate is None:
        return None
    else:
        rotation = math.degrees(math.atan2(ordinate, abscissa))

    crs = crs_description = datum = None
    map_unit = map_unit_metres = None
    target = _REFERENCE.search(conversion[1]) if len(conversion) > 1 else None
    attributes = projected.get(int(target.group(1))) if target else None
    if attributes is None and len(projected) == 1:
        attributes = next(iter(projected.values()))
    if attributes:
        crs = _string_attribute(attributes[0]) if attributes else None
        crs_description = _string_attribute(attributes[1]) if len(attributes) > 1 else None
        datum = _string_attribute(attributes[2]) if len(attributes) > 2 else None
        # IfcProjectedCRS.MapUnit, the seventh attribute. Resolving it is not optional: this is what
        # turns an easting of 729,013,348 from an implausible number into 729 km across a UTM zone.
        unit_reference = _REFERENCE.search(attributes[6]) if len(attributes) > 6 else None
        unit_line = units.get(int(unit_reference.group(1))) if unit_reference else None
        if unit_line:
            resolved = length_unit_metres(unit_line)
            if resolved:
                map_unit_metres, map_unit = resolved

    return IfcGeoreference(
        crs=crs,
        crs_description=crs_description,
        geodetic_datum=datum,
        eastings=eastings,
        northings=northings,
        orthogonal_height=height if height is not None else 0.0,
        rotation_degrees=rotation,
        scale=scale if scale is not None else 1.0,
        map_unit=map_unit,
        map_unit_metres=map_unit_metres,
    )


def length_unit_metres(text: str) -> tuple[float, str] | None:
    """Solve the model's length unit, as ``(metres_per_unit, label)``.

    IFC states units once, near the top, and everything numeric in the file is in them. Getting this
    wrong is the single highest-consequence misreading available in the format.
    """
    for match in _SI_UNIT.finditer(text):
        unit_type, prefix, unit_name = (group.upper() for group in match.groups())
        if unit_type != "LENGTHUNIT" or unit_name != "METRE":
            continue
        prefix = prefix.strip(". $")
        factor = _SI_PREFIX.get(prefix, 1.0)
        label = {1.0: "m", 1e-3: "mm", 1e-2: "cm"}.get(factor, f"{factor}m")
        return factor, label
    for match in _CONVERSION_UNIT.finditer(text):
        unit_type, name = match.group(1).upper(), match.group(2).lower()
        if unit_type != "LENGTHUNIT":
            continue
        if "foot" in name or "feet" in name:
            return 0.3048, "ft"
        if "inch" in name:
            return 0.0254, "in"
    return None


#: How far into a model too large to census we look for the map conversion. Authoring tools write
#: it with the project and context, which is the top of the DATA section in every file seen so far.
_GEOREFERENCE_SCAN_LINES = 20_000


def _head_lines(path: Path, limit: int) -> list[str]:
    lines: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for index, line in enumerate(stream):
            if index >= limit:
                break
            lines.append(line)
    return lines


def _add_georeference(
    summary: dict[str, Any], lines: Iterable[str], model_unit_metres: float | None = None
) -> None:
    found = parse_georeference(lines)
    if found is None:
        return
    east, north, height = found.origin_metres()
    summary["georeference"] = {
        "crs": found.crs,
        "crs_description": found.crs_description,
        "geodetic_datum": found.geodetic_datum,
        # Raw, as the file states them, in map_unit -- the audit trail.
        "eastings": found.eastings,
        "northings": found.northings,
        "orthogonal_height": found.orthogonal_height,
        "map_unit": found.map_unit,
        "map_unit_metres": found.map_unit_metres,
        # And in metres, which is what every consumer here actually wants.
        "eastings_metres": east,
        "northings_metres": north,
        "orthogonal_height_metres": height,
        "rotation_degrees": found.rotation_degrees,
        "scale": found.scale,
        # Named frames, because a matrix without them cannot be checked by anyone -- and this one
        # is metres in, metres out, so composing it with anything else here is safe.
        "source": "model-local",
        "target": found.crs or "projected-crs",
        "matrix": list(found.matrix(model_unit_metres or 1.0)),
        "matrix_units": "m",
    }


def summarise(path: str | Path, *, deep_limit: int = DEFAULT_DEEP_LIMIT) -> dict[str, Any]:
    """Header, units and a storey list. The census is skipped for very large models."""
    path = Path(path)
    size = path.stat().st_size
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        head = stream.read(8192)
    header = parse_header(head)

    summary: dict[str, Any] = {
        "ifc_schema": header.schema,
        "ifc_name": header.file_name,
        "ifc_timestamp": header.timestamp,
        "preprocessor": header.preprocessor,
        "originating_system": header.originating_system,
    }
    if header.authors:
        summary["authors"] = list(header.authors)
    if header.organisations:
        summary["organisations"] = list(header.organisations)
    if header.description:
        summary["description"] = list(header.description)

    if size > deep_limit:
        summary["census_skipped"] = (
            f"Model is {size / 1_048_576:.0f} MB, above the {deep_limit / 1_048_576:.0f} MB scan "
            "limit. Use the ifc adapter for a model this size."
        )
        # Where the model *is* survives the census limit. It is a handful of lines near the top of
        # the file, it is the one fact a 2 GB federated model most needs to state, and skipping it
        # because the model is large is exactly backwards -- large models are the georeferenced ones.
        head = _head_lines(path, _GEOREFERENCE_SCAN_LINES)
        head_unit = length_unit_metres("\n".join(head))
        if head_unit:
            summary["length_unit_metres"], summary["length_unit"] = head_unit
        _add_georeference(summary, head, head_unit[0] if head_unit else None)
        return summary

    census: dict[str, int] = {}
    storeys: list[IfcStorey] = []
    unit_text: list[str] = []
    geo_lines: list[str] = []
    entity_count = 0
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            stripped = line.lstrip()
            if not stripped.startswith("#"):
                continue
            match = _ENTITY.match(stripped)
            if not match:
                continue
            entity_count += 1
            entity = match.group(1).upper()
            census[entity] = census.get(entity, 0) + 1
            if entity in ("IFCSIUNIT", "IFCCONVERSIONBASEDUNIT") and len(unit_text) < 64:
                unit_text.append(stripped)
                # Also a georeference line: IfcProjectedCRS.MapUnit points at one of these, and the
                # map origin is meaningless without it.
                geo_lines.append(stripped)
            elif entity in ("IFCMAPCONVERSION", "IFCPROJECTEDCRS"):
                geo_lines.append(stripped)
            elif entity == "IFCBUILDINGSTOREY":
                storey_match = _STOREY.match(stripped)
                if storey_match:
                    try:
                        storeys.append(
                            _parse_storey(stripped.rstrip().rstrip(";"), int(storey_match.group(1)))
                        )
                    except (ValueError, IndexError):
                        continue

    summary["entity_count"] = entity_count
    summary["entity_census"] = dict(sorted(census.items(), key=lambda kv: -kv[1])[:40])
    unit = length_unit_metres("\n".join(unit_text))
    if unit:
        summary["length_unit_metres"], summary["length_unit"] = unit
    # After the unit, not before: the conversion matrix is metres-in metres-out, and the model's
    # own length unit is half of what makes that true.
    _add_georeference(summary, geo_lines, unit[0] if unit else None)
    storeys.sort(key=lambda s: (s.elevation if s.elevation is not None else 0.0, s.step_id))
    summary["storeys"] = [
        {
            "global_id": storey.global_id,
            "name": storey.name or storey.long_name,
            "long_name": storey.long_name,
            "elevation": storey.elevation,
        }
        for storey in storeys
    ]
    summary["storey_count"] = len(storeys)
    return summary


def summarise_fragments(path: str | Path) -> dict[str, Any]:
    """What can honestly be said about a ``.frag`` file.

    That Open Fragments are FlatBuffers. There is no magic number and no version field a reader can
    check without the schema, so this reports size and the presence of a companion index rather
    than pretending to parse. The rule from the research stands regardless: convert IFC to
    Fragments once, then load the Fragments -- never re-parse IFC in the browser.
    """
    path = Path(path)
    summary: dict[str, Any] = {
        "container": "flatbuffers",
        "note": "That Open Fragments carry no self-describing header; contents are not inspected.",
    }
    for candidate in (path.with_suffix(".json"), path.with_name(path.stem + "-properties.json")):
        if candidate.exists():
            summary["properties_sidecar"] = candidate.name
            break
    return summary
