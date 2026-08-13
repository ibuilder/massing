"""LAS and LAZ public header, VLRs, and the CRS hiding in them.

The LAS public header block is a fixed-layout struct that carries everything a project needs to
decide what to do with a point cloud -- count, extent, scale, offset -- and the georeferencing sits
just past it in the variable-length records. All of it is readable with ``struct``, so a project can
index a 40 GB aerial survey in a millisecond without laspy, PDAL, or a decompressor.

The CRS matters more here than anywhere else in the package. A LAS file is the one reality-capture
format that routinely arrives *already* in a projected national grid, and a project that ingests it
without reading the grid off it has silently thrown away the only georeference it was given.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

_SIGNATURE = b"LASF"

#: The compression bit. LAZ is a LAS file whose point format has bit 7 set, plus a "laszip encoded"
#: VLR describing the chunking. Everything in the public header stays readable either way, which is
#: what makes indexing a LAZ without a decompressor possible.
_COMPRESSION_BIT = 0x80

#: GeoTIFF key ids that name a CRS, in the order they should be preferred. A projected system is a
#: better answer than the geographic one it is based on.
_PROJECTED_CS_KEY = 3072
_GEOGRAPHIC_CS_KEY = 2048
_VERTICAL_CS_KEY = 4096

#: Whether the coordinates are projected, geographic or geocentric. This decides *which* unit key
#: applies, and getting it wrong is worse than reading no unit at all: a file in a projected system
#: normally also carries the angular unit of the geographic system underneath it, so a reader that
#: grabs the first unit key it finds calls a state-plane survey in feet "degrees".
_MODEL_TYPE_KEY = 1024
_PROJECTED_UNITS_KEY = 3076
_ANGULAR_UNITS_KEY = 2054

_MODEL_PROJECTED, _MODEL_GEOGRAPHIC, _MODEL_GEOCENTRIC = 1, 2, 3

#: EPSG unit-of-measure codes, and how many metres one is. Angular units have no metre factor --
#: a degree is a distance only once you say where on the ellipsoid you are standing.
_LINEAR_UNITS: dict[int, tuple[str, float]] = {
    9001: ("metre", 1.0),
    9002: ("foot", 0.3048),
    9003: ("US survey foot", 1200.0 / 3937.0),
    9005: ("Clarke's foot", 0.3047972654),
    9036: ("kilometre", 1000.0),
    9093: ("statute mile", 1609.344),
}
_ANGULAR_UNITS: dict[int, str] = {9101: "radian", 9102: "degree", 9105: "grad"}


class LasError(ValueError):
    """A file claimed to be LAS and its header did not read as one."""


@dataclass(frozen=True)
class LasHeader:
    version: str
    point_format: int
    compressed: bool
    point_count: int
    point_record_length: int
    scale: tuple[float, float, float]
    offset: tuple[float, float, float]
    #: Bounds as stored -- already in real coordinates, scale and offset applied by the writer.
    bounds: tuple[float, float, float, float, float, float]
    system_identifier: str
    generating_software: str
    creation_year: int | None
    creation_day: int | None
    header_size: int
    point_data_offset: int
    vlr_count: int
    #: Global encoding bit 4: coordinates are WGS84 rather than the CRS in the VLRs.
    wkt_crs: bool

    @property
    def has_colour(self) -> bool:
        """Point formats carrying RGB. 2, 3, 5, 7, 8 and 10 do; the rest do not."""
        return self.point_format in (2, 3, 5, 7, 8, 10)

    @property
    def has_time(self) -> bool:
        return self.point_format in (1, 3, 4, 5, 6, 7, 8, 9, 10)

    @property
    def has_waveform(self) -> bool:
        return self.point_format in (4, 5, 9, 10)


def _text(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()


def parse_header(data: bytes) -> LasHeader:
    """Read the public header block. Needs the first 375 bytes; tolerates being given more."""
    if len(data) < 227 or data[:4] != _SIGNATURE:
        raise LasError('Not a LAS file -- the header does not begin with "LASF".')

    version = f"{data[24]}.{data[25]}"
    global_encoding = struct.unpack_from("<H", data, 6)[0]
    system_identifier = _text(data[26:58])
    generating_software = _text(data[58:90])
    creation_day, creation_year = struct.unpack_from("<HH", data, 90)
    header_size, point_data_offset, vlr_count = struct.unpack_from("<HII", data, 94)
    raw_format = data[104]
    point_record_length = struct.unpack_from("<H", data, 105)[0]
    legacy_count = struct.unpack_from("<I", data, 107)[0]

    scale = struct.unpack_from("<3d", data, 131)
    offset = struct.unpack_from("<3d", data, 155)
    max_x, min_x, max_y, min_y, max_z, min_z = struct.unpack_from("<6d", data, 179)

    point_count = legacy_count
    if data[24] == 1 and data[25] >= 4 and len(data) >= 255:
        # LAS 1.4 moved the count to a 64-bit field; the legacy one is zero for point formats
        # above 5 and merely truncated for the rest, so the wide field wins whenever it is present.
        wide_count = struct.unpack_from("<Q", data, 247)[0]
        if wide_count:
            point_count = wide_count

    return LasHeader(
        version=version,
        point_format=raw_format & 0x3F,
        compressed=bool(raw_format & _COMPRESSION_BIT),
        point_count=point_count,
        point_record_length=point_record_length,
        scale=scale,
        offset=offset,
        bounds=(min_x, min_y, min_z, max_x, max_y, max_z),
        system_identifier=system_identifier,
        generating_software=generating_software,
        creation_year=creation_year or None,
        creation_day=creation_day or None,
        header_size=header_size,
        point_data_offset=point_data_offset,
        vlr_count=vlr_count,
        wkt_crs=bool(global_encoding & 0x10),
    )


@dataclass(frozen=True)
class VariableLengthRecord:
    user_id: str
    record_id: int
    description: str
    payload: bytes


def read_vlrs(stream: BinaryIO, header: LasHeader) -> list[VariableLengthRecord]:
    """Walk the variable-length records between the header and the point data."""
    stream.seek(header.header_size)
    records: list[VariableLengthRecord] = []
    for _ in range(header.vlr_count):
        raw = stream.read(54)
        if len(raw) < 54:
            break
        user_id = _text(raw[2:18])
        record_id, payload_length = struct.unpack_from("<HH", raw, 18)
        description = _text(raw[22:54])
        payload = stream.read(payload_length)
        records.append(VariableLengthRecord(user_id, record_id, description, payload))
        if stream.tell() > header.point_data_offset:
            break
    return records


def _geokeys(payload: bytes) -> dict[int, int]:
    """Parse a GeoTIFF GeoKeyDirectoryTag into ``{key_id: value}`` for inline values only.

    Keys whose value lives in a companion double or ASCII VLR are skipped: the ones that name a CRS
    are always inline shorts, and chasing the others would be effort spent on keys nobody reads.
    """
    if len(payload) < 8:
        return {}
    _, _, _, count = struct.unpack_from("<4H", payload, 0)
    keys: dict[int, int] = {}
    for index in range(count):
        start = 8 + index * 8
        if start + 8 > len(payload):
            break
        key_id, tiff_tag_location, _value_count, value = struct.unpack_from("<4H", payload, start)
        if tiff_tag_location == 0:
            keys[key_id] = value
    return keys


def _units_from_geokeys(keys: dict[int, int]) -> dict[str, Any]:
    """What one unit of X and Y *is*, which is not always a metre and is sometimes not a length.

    Everything downstream of a point cloud multiplies by a length: the decimation target, the
    tileset's geometric error, the envelope, the measurement tool. There is no way to write "metres
    per unit" honestly without reading this, and defaulting to 1.0 is a silent factor of 3.28 on any
    survey in feet and complete nonsense on anything in degrees.
    """
    model = keys.get(_MODEL_TYPE_KEY)
    # Geocentric coordinates are metres by definition and carry no unit key.
    if model == _MODEL_GEOCENTRIC:
        return {"horizontal_unit": "metre", "horizontal_unit_metres": 1.0}

    if model == _MODEL_GEOGRAPHIC:
        code = keys.get(_ANGULAR_UNITS_KEY)
        name = _ANGULAR_UNITS.get(code) if code else None
        # An angular unit is reported without a metre factor on purpose. Supplying one would mean
        # choosing a latitude, and a caller that has to ask for the factor is a caller that has
        # noticed it needs a projection.
        return {"horizontal_unit": name, "angular": True} if name else {"angular": True}

    # Projected, or unstated -- in which case the linear key is still the one that applies, because
    # a file carrying ProjLinearUnits at all is describing a projected system.
    code = keys.get(_PROJECTED_UNITS_KEY)
    if code and code in _LINEAR_UNITS:
        name, metres = _LINEAR_UNITS[code]
        return {"horizontal_unit": name, "horizontal_unit_metres": metres, "angular": False}
    if model == _MODEL_PROJECTED:
        return {"horizontal_unit": "metre", "horizontal_unit_metres": 1.0, "angular": False}
    return {}


def crs_from_vlrs(records: list[VariableLengthRecord]) -> dict[str, Any]:
    """Pull whatever georeferencing the VLRs carry: an EPSG code, a WKT string, or nothing."""
    found: dict[str, Any] = {}
    for record in records:
        if record.user_id == "LASF_Projection":
            if record.record_id == 34735:
                keys = _geokeys(record.payload)
                # 32767 is "user-defined", which names nothing.
                projected = keys.get(_PROJECTED_CS_KEY)
                geographic = keys.get(_GEOGRAPHIC_CS_KEY)
                vertical = keys.get(_VERTICAL_CS_KEY)
                if projected and projected != 32767:
                    found["crs"] = f"EPSG:{projected}"
                elif geographic and geographic != 32767:
                    found["crs"] = f"EPSG:{geographic}"
                if vertical and vertical != 32767:
                    found["vertical_crs"] = f"EPSG:{vertical}"
                found.update(_units_from_geokeys(keys))
            elif record.record_id in (2111, 2112):
                wkt = record.payload.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
                if wkt:
                    found["crs_wkt"] = wkt
                    found.setdefault("crs", _epsg_from_wkt(wkt) or "")
                    if not found["crs"]:
                        del found["crs"]
        elif record.user_id == "laszip encoded":
            found["laszip"] = True
    return found


def _epsg_from_wkt(wkt: str) -> str | None:
    """The trailing ``AUTHORITY["EPSG","27700"]`` of a WKT string, if it has one.

    Deliberately naive: this reads the *last* authority block, which in well-formed WKT is the one
    for the outermost CRS. A WKT that does not carry an authority is reported as WKT-only rather
    than guessed at, because a guessed EPSG code is worse than none.
    """
    marker = wkt.upper().rfind('AUTHORITY["EPSG"')
    if marker == -1:
        return None
    tail = wkt[marker:]
    start = tail.find(",", tail.find('"EPSG"'))
    if start == -1:
        return None
    digits = "".join(ch for ch in tail[start : start + 24] if ch.isdigit())
    return f"EPSG:{digits}" if digits else None


def summarise(path: str | Path) -> dict[str, Any]:
    """Header, VLR-derived CRS and the extent, without decompressing a byte of point data."""
    path = Path(path)
    with path.open("rb") as stream:
        header = parse_header(stream.read(375))
        records = read_vlrs(stream, header)
    min_x, min_y, min_z, max_x, max_y, max_z = header.bounds

    summary: dict[str, Any] = {
        "las_version": header.version,
        "point_format": header.point_format,
        "compressed": header.compressed,
        "point_count": header.point_count,
        "scale": list(header.scale),
        "offset": list(header.offset),
        "bounds": [min_x, min_y, min_z, max_x, max_y, max_z],
        "bounds_sampled": False,
        "has_color": header.has_colour,
        "has_gps_time": header.has_time,
        "system_identifier": header.system_identifier,
        "generating_software": header.generating_software,
        "vlr_count": header.vlr_count,
    }
    if header.creation_year:
        summary["creation_year"] = header.creation_year
        summary["creation_day"] = header.creation_day
    summary.update(crs_from_vlrs(records))
    if header.wkt_crs and "crs" not in summary:
        summary["crs"] = "EPSG:4326"
        summary["crs_source"] = "global encoding WGS84 bit"
    return summary
