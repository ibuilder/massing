"""E57, read from its own index.

E57 is the important one for architecture. It is the interchange format registered scans actually
arrive in, and -- unlike every other point format -- it carries the *scanner's* view of the world:
where each setup stood, how it was oriented, whether the data is a structured grid or a loose cloud,
and what imagery came with it.

All of that lives in an XML section at the end of the file, and the header says exactly where. So a
project can read scan positions out of a 12 GB E57 without pye57, without libE57Format, and without
touching a point. That is the whole reason this module exists: extracting setup positions is the
single most useful thing you can do to a scan dataset, and it turns out to be free.

The one wrinkle is paging. E57 stores data in CRC-protected pages -- 1024 bytes of which four are a
checksum -- so a physical offset is not a logical one, and reading the XML means walking the pages
and dropping the checksums. :func:`read_logical` does that.
"""

from __future__ import annotations

import math
import struct
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO

_SIGNATURE = b"ASTM-E57"
_NS = "{http://www.astm.org/COMMIT/E57/2010-e57-v1.0}"

#: GPS epoch. E57 timestamps are seconds since this instant, in GPS time.
_GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc)

#: GPS runs ahead of UTC by the accumulated leap seconds -- 18 since 2017-01-01, and unchanged
#: since. Applied so a converted timestamp is right rather than eighteen seconds early; a scan
#: whose writer ignored the distinction is out by the same eighteen seconds either way, and no
#: amount of cleverness here can tell the two cases apart.
_GPS_UTC_LEAP_SECONDS = 18


class E57Error(ValueError):
    """A file claimed to be E57 and its header or index did not read as one."""


@dataclass(frozen=True)
class E57FileHeader:
    version: str
    file_length: int
    xml_physical_offset: int
    xml_logical_length: int
    page_size: int


def parse_header(data: bytes) -> E57FileHeader:
    if len(data) < 48 or data[:8] != _SIGNATURE:
        raise E57Error('Not an E57 file -- the header does not begin with "ASTM-E57".')
    major, minor = struct.unpack_from("<II", data, 8)
    file_length, xml_offset, xml_length, page_size = struct.unpack_from("<4Q", data, 16)
    if page_size < 8:
        raise E57Error(f"Implausible E57 page size {page_size}.")
    return E57FileHeader(f"{major}.{minor}", file_length, xml_offset, xml_length, page_size)


def _crc32c_table() -> tuple[int, ...]:
    table = []
    for index in range(256):
        crc = index
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
        table.append(crc)
    return tuple(table)


_CRC32C = _crc32c_table()


def crc32c(data: bytes) -> int:
    """CRC-32C (Castagnoli), which is what E57 page checksums are.

    Not ``zlib.crc32`` -- that is the IEEE polynomial, and the two disagree on every input. E57
    additionally stores the result **big-endian** while the rest of the format is little-endian.
    Both facts were established by writing a file with libE57Format and testing the candidates
    against its bytes, because getting either wrong produces a file that reads perfectly here and
    is rejected as corrupt by every other tool.
    """
    crc = 0xFFFFFFFF
    for byte in data:
        crc = _CRC32C[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


def verify_pages(path: str | Path, *, limit: int | None = 64) -> list[int]:
    """Check page checksums and return the indices of any that fail.

    Opt-in, because it costs a read of every page it checks and nothing in the normal path needs
    it. Worth having because an E57's corruption is *detectable* -- the format went to the trouble
    of a per-page checksum, and a reader that never looks at one throws that away.
    """
    path = Path(path)
    bad: list[int] = []
    with path.open("rb") as stream:
        header = parse_header(stream.read(48))
        payload = header.page_size - 4
        stream.seek(0)
        index = 0
        while limit is None or index < limit:
            page = stream.read(header.page_size)
            if len(page) < header.page_size:
                break
            if int.from_bytes(page[payload:], "big") != crc32c(page[:payload]):
                bad.append(index)
            index += 1
    return bad


def read_logical(
    stream: BinaryIO, physical_offset: int, logical_length: int, page_size: int
) -> bytes:
    """Read ``logical_length`` bytes starting at a physical offset, skipping page checksums.

    The last four bytes of every page are a CRC, not payload. Reading straight through them yields
    XML with four bytes of noise every kilobyte, which parses right up until it does not.
    """
    payload_per_page = page_size - 4
    out = bytearray()
    page = physical_offset // page_size
    within = physical_offset % page_size
    while len(out) < logical_length:
        stream.seek(page * page_size)
        raw = stream.read(page_size)
        if not raw:
            break
        if within < payload_per_page:
            out += raw[within:payload_per_page]
        page += 1
        within = 0
    return bytes(out[:logical_length])


def _child(node: ElementTree.Element | None, name: str) -> ElementTree.Element | None:
    if node is None:
        return None
    return node.find(f"{_NS}{name}")


def _number(node: ElementTree.Element | None, name: str) -> float | None:
    found = _child(node, name)
    if found is None or found.text is None:
        return None
    try:
        return float(found.text.strip())
    except ValueError:
        return None


def _string(node: ElementTree.Element | None, name: str) -> str | None:
    found = _child(node, name)
    if found is None or found.text is None:
        return None
    text = found.text.strip()
    return text or None


def _gps_time_to_iso(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    try:
        moment = _GPS_EPOCH + timedelta(seconds=seconds - _GPS_UTC_LEAP_SECONDS)
    except (OverflowError, ValueError):
        return None
    # Writers that leave the field at zero are saying "unknown", not "January 1980".
    if moment.year < 1990:
        return None
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ScanSummary:
    """One ``data3D`` entry: a scanner setup, and what it recorded from there."""

    guid: str | None
    name: str | None
    point_count: int
    #: ``cartesian``, ``spherical`` or ``unknown``. Terrestrial scanners measure range, azimuth and
    #: elevation, and E57 lets a writer store exactly that rather than converting. Such a scan has
    #: no ``cartesianBounds`` at all, so a reader that knows only the cartesian form reports an
    #: extentless scan -- indistinguishable, downstream, from one that is genuinely empty.
    coordinates: str = "unknown"
    #: Setup position in the file's own coordinates.
    translation: tuple[float, float, float] | None = None
    #: Setup orientation as a quaternion in ``(x, y, z, w)`` order -- converted from E57's
    #: ``(w, x, y, z)`` structure on the way out, so callers never handle the other convention.
    rotation: tuple[float, float, float, float] | None = None
    bounds: tuple[float, float, float, float, float, float] | None = None
    has_colour: bool = False
    has_intensity: bool = False
    #: True when the scan carries ``rowIndex``/``columnIndex``, i.e. it is a structured grid rather
    #: than a loose cloud. This is what makes panorama reconstruction from the scan possible, which
    #: is exactly the NavVis-style workflow the research brief describes.
    structured: bool = False
    #: Grid dimensions, when structured.
    rows: int | None = None
    columns: int | None = None
    acquired_at: str | None = None
    sensor: str | None = None


@dataclass(frozen=True)
class ImageSummary:
    """One ``images2D`` entry. Spherical ones are panoramas the walkthrough can use directly."""

    guid: str | None
    name: str | None
    #: ``spherical``, ``pinhole``, ``cylindrical`` or ``visual``.
    representation: str
    width: int | None = None
    height: int | None = None
    translation: tuple[float, float, float] | None = None
    rotation: tuple[float, float, float, float] | None = None
    #: The scan this image was taken from, when the file says.
    associated_scan_guid: str | None = None
    #: Byte offset of the embedded JPEG/PNG blob, and its length, when present.
    blob_offset: int | None = None
    blob_length: int | None = None
    image_format: str | None = None


@dataclass(frozen=True)
class E57Summary:
    version: str
    guid: str | None
    scans: tuple[ScanSummary, ...] = ()
    images: tuple[ImageSummary, ...] = ()
    coordinate_metadata: str | None = None
    creation_date: str | None = None
    library_version: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def point_count(self) -> int:
        return sum(scan.point_count for scan in self.scans)

    @property
    def bounds(self) -> tuple[float, ...] | None:
        boxes = [scan.bounds for scan in self.scans if scan.bounds]
        if not boxes:
            return None
        return (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            min(b[2] for b in boxes),
            max(b[3] for b in boxes),
            max(b[4] for b in boxes),
            max(b[5] for b in boxes),
        )

    @property
    def panorama_count(self) -> int:
        return sum(1 for image in self.images if image.representation == "spherical")


def _pose(node: ElementTree.Element | None) -> tuple[Any, Any]:
    pose = _child(node, "pose")
    if pose is None:
        return None, None
    translation_node = _child(pose, "translation")
    rotation_node = _child(pose, "rotation")
    translation = None
    rotation = None
    if translation_node is not None:
        translation = (
            _number(translation_node, "x") or 0.0,
            _number(translation_node, "y") or 0.0,
            _number(translation_node, "z") or 0.0,
        )
    if rotation_node is not None:
        # E57 writes the scalar first. Everything downstream of here wants it last.
        rotation = (
            _number(rotation_node, "x") or 0.0,
            _number(rotation_node, "y") or 0.0,
            _number(rotation_node, "z") or 0.0,
            _number(rotation_node, "w") if _number(rotation_node, "w") is not None else 1.0,
        )
    return translation, rotation


def _critical_angles(low: float, high: float) -> list[float]:
    """The interval's endpoints plus every multiple of pi/2 inside it.

    Where ``sin`` and ``cos`` reach +-1. Including them is what makes the envelope below exact
    rather than merely a bound over the corners.
    """
    angles = [low, high]
    step = math.pi / 2
    index = math.ceil(low / step)
    while index * step < high:
        angles.append(index * step)
        index += 1
    return angles


def _spherical_envelope(box: ElementTree.Element) -> tuple[float, ...] | None:
    """A cartesian bounding box for a range/azimuth/elevation extent.

    Each axis is a *separable* product -- ``x = r cos(e) cos(a)``, ``y = r cos(e) sin(a)``,
    ``z = r sin(e)`` -- so the extreme over the box is attained where each factor is individually
    extreme. Evaluating the endpoints together with the interior quarter-turns is therefore not an
    approximation: it is the answer.
    """
    values = [
        _number(box, "rangeMinimum"),
        _number(box, "rangeMaximum"),
        _number(box, "azimuthMinimum"),
        _number(box, "azimuthMaximum"),
        _number(box, "elevationMinimum"),
        _number(box, "elevationMaximum"),
    ]
    if any(value is None for value in values):
        return None
    r_low, r_high, a_low, a_high, e_low, e_high = (float(value) for value in values)  # type: ignore[arg-type]

    low = [float("inf")] * 3
    high = [float("-inf")] * 3
    for radius in (r_low, r_high):
        for azimuth in _critical_angles(a_low, a_high):
            for elevation in _critical_angles(e_low, e_high):
                point = (
                    radius * math.cos(elevation) * math.cos(azimuth),
                    radius * math.cos(elevation) * math.sin(azimuth),
                    radius * math.sin(elevation),
                )
                for axis in range(3):
                    low[axis] = min(low[axis], point[axis])
                    high[axis] = max(high[axis], point[axis])
    return (*low, *high)


def _bounds(node: ElementTree.Element | None) -> tuple[float, ...] | None:
    box = _child(node, "cartesianBounds")
    if box is None:
        spherical = _child(node, "sphericalBounds")
        return _spherical_envelope(spherical) if spherical is not None else None
    values = [
        _number(box, "xMinimum"),
        _number(box, "yMinimum"),
        _number(box, "zMinimum"),
        _number(box, "xMaximum"),
        _number(box, "yMaximum"),
        _number(box, "zMaximum"),
    ]
    if any(v is None for v in values):
        return None
    return tuple(float(v) for v in values)  # type: ignore[arg-type]


_CARTESIAN_FIELDS = frozenset({"cartesianX", "cartesianY", "cartesianZ"})
_SPHERICAL_FIELDS = frozenset({"sphericalRange", "sphericalAzimuth", "sphericalElevation"})


def _coordinates(prototype_fields: set[str]) -> str:
    if prototype_fields >= _CARTESIAN_FIELDS:
        return "cartesian"
    if prototype_fields >= _SPHERICAL_FIELDS:
        return "spherical"
    return "unknown"


def _parse_scan(node: ElementTree.Element) -> ScanSummary:
    points = _child(node, "points")
    prototype = _child(points, "prototype")
    prototype_fields = (
        {child.tag.replace(_NS, "") for child in prototype} if prototype is not None else set()
    )
    record_count = 0
    if points is not None:
        try:
            record_count = int(points.get("recordCount", "0"))
        except ValueError:
            record_count = 0

    index_bounds = _child(node, "indexBounds")
    rows = columns = None
    if index_bounds is not None:
        row_max = _number(index_bounds, "rowMaximum")
        row_min = _number(index_bounds, "rowMinimum")
        column_max = _number(index_bounds, "columnMaximum")
        column_min = _number(index_bounds, "columnMinimum")
        if row_max is not None and row_min is not None:
            rows = int(row_max - row_min) + 1
        if column_max is not None and column_min is not None:
            columns = int(column_max - column_min) + 1

    translation, rotation = _pose(node)
    acquisition = _child(node, "acquisitionStart")
    sensor_parts = [
        _string(node, "sensorVendor"),
        _string(node, "sensorModel"),
    ]
    sensor = " ".join(part for part in sensor_parts if part) or None

    return ScanSummary(
        guid=_string(node, "guid"),
        name=_string(node, "name"),
        point_count=record_count,
        coordinates=_coordinates(prototype_fields),
        translation=translation,
        rotation=rotation,
        bounds=_bounds(node),
        has_colour={"colorRed", "colorGreen", "colorBlue"} <= prototype_fields,
        has_intensity="intensity" in prototype_fields,
        structured={"rowIndex", "columnIndex"} <= prototype_fields,
        rows=rows,
        columns=columns,
        acquired_at=_gps_time_to_iso(_number(acquisition, "dateTimeValue")),
        sensor=sensor,
    )


_REPRESENTATIONS = {
    "sphericalRepresentation": "spherical",
    "pinholeRepresentation": "pinhole",
    "cylindricalRepresentation": "cylindrical",
    "visualReferenceRepresentation": "visual",
}


def _parse_image(node: ElementTree.Element) -> ImageSummary | None:
    representation_node = None
    representation = None
    for tag, label in _REPRESENTATIONS.items():
        found = _child(node, tag)
        if found is not None:
            representation_node, representation = found, label
            break
    if representation_node is None or representation is None:
        return None

    blob_offset = blob_length = None
    image_format = None
    for candidate in ("jpegImage", "pngImage"):
        blob = _child(representation_node, candidate)
        if blob is not None:
            image_format = "jpeg" if candidate == "jpegImage" else "png"
            try:
                blob_offset = int(blob.get("fileOffset", "0")) or None
                blob_length = int(blob.get("length", "0")) or None
            except ValueError:
                blob_offset = blob_length = None
            break

    width = _number(representation_node, "imageWidth")
    height = _number(representation_node, "imageHeight")
    translation, rotation = _pose(node)
    return ImageSummary(
        guid=_string(node, "guid"),
        name=_string(node, "name"),
        representation=representation,
        width=int(width) if width else None,
        height=int(height) if height else None,
        translation=translation,
        rotation=rotation,
        associated_scan_guid=_string(node, "associatedData3DGuid"),
        blob_offset=blob_offset,
        blob_length=blob_length,
        image_format=image_format,
    )


def parse_index(xml_bytes: bytes) -> E57Summary:
    """Turn the E57 XML index into a summary. The whole point of the module."""
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as thrown:
        raise E57Error(f"E57 index is not well-formed XML: {thrown}") from thrown

    warnings: list[str] = []
    scans: list[ScanSummary] = []
    data3d = root.find(f"{_NS}data3D")
    if data3d is not None:
        for child in data3d:
            try:
                scans.append(_parse_scan(child))
            except (ValueError, TypeError) as thrown:  # noqa: PERF203
                warnings.append(f"A data3D entry could not be read: {thrown}")

    images: list[ImageSummary] = []
    images2d = root.find(f"{_NS}images2D")
    if images2d is not None:
        for child in images2d:
            parsed = _parse_image(child)
            if parsed is not None:
                images.append(parsed)

    major = _number(root, "versionMajor")
    minor = _number(root, "versionMinor")
    return E57Summary(
        version=f"{int(major or 1)}.{int(minor or 0)}",
        guid=_string(root, "guid"),
        scans=tuple(scans),
        images=tuple(images),
        coordinate_metadata=_string(root, "coordinateMetadata"),
        creation_date=_gps_time_to_iso(_number(_child(root, "creationDateTime"), "dateTimeValue")),
        library_version=_string(root, "e57LibraryVersion"),
        warnings=tuple(warnings),
    )


def read_summary(path: str | Path) -> E57Summary:
    """Open an E57, follow the header to its index, and summarise it."""
    path = Path(path)
    with path.open("rb") as stream:
        header = parse_header(stream.read(48))
        xml_bytes = read_logical(
            stream, header.xml_physical_offset, header.xml_logical_length, header.page_size
        )
    return parse_index(xml_bytes)


def summarise(path: str | Path) -> dict[str, Any]:
    """The dictionary form, for ``AssetRecord.metadata``."""
    summary = read_summary(path)
    out: dict[str, Any] = {
        "e57_version": summary.version,
        "guid": summary.guid,
        "scan_count": len(summary.scans),
        "point_count": summary.point_count,
        "image_count": len(summary.images),
        "panorama_count": summary.panorama_count,
        "structured_scans": sum(1 for scan in summary.scans if scan.structured),
        "has_color": any(scan.has_colour for scan in summary.scans),
        "has_intensity": any(scan.has_intensity for scan in summary.scans),
        "bounds_sampled": False,
    }
    coordinates = sorted({scan.coordinates for scan in summary.scans})
    if coordinates:
        out["coordinates"] = coordinates[0] if len(coordinates) == 1 else "mixed"
    if summary.bounds:
        out["bounds"] = list(summary.bounds)
    if summary.coordinate_metadata:
        out["crs_wkt"] = summary.coordinate_metadata
    if summary.creation_date:
        out["created"] = summary.creation_date
    if summary.library_version:
        out["library_version"] = summary.library_version
    acquisitions = sorted(scan.acquired_at for scan in summary.scans if scan.acquired_at)
    if acquisitions:
        out["first_scan_at"] = acquisitions[0]
        out["last_scan_at"] = acquisitions[-1]
    sensors = sorted({scan.sensor for scan in summary.scans if scan.sensor})
    if sensors:
        out["sensors"] = sensors
    out["scans"] = [
        {
            "guid": scan.guid,
            "name": scan.name,
            "point_count": scan.point_count,
            "position": list(scan.translation) if scan.translation else None,
            "rotation": list(scan.rotation) if scan.rotation else None,
            "coordinates": scan.coordinates,
            "structured": scan.structured,
            "rows": scan.rows,
            "columns": scan.columns,
            "acquired_at": scan.acquired_at,
        }
        for scan in summary.scans
    ]
    if summary.warnings:
        out["warnings"] = list(summary.warnings)
    return out
