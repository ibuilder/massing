"""Images: dimensions, EXIF, GPS, and the two XMP blocks that matter.

Three things are worth extracting from a photograph on this pipeline, and all three are in the
standard library's reach.

**Is it a panorama?** The reliable answer is the ``GPano`` XMP block written by every 360 camera and
stitcher: ``ProjectionType="equirectangular"`` plus a heading. The unreliable answer is a 2:1 aspect
ratio, which is also what a wide crop looks like. Both are reported, labelled as what they are.

**Where was it taken?** Drone photographs carry GPS in EXIF and gimbal yaw in a DJI XMP block. That
is a camera pose per frame, which is the difference between a folder of JPEGs and a georeferenced
image set that ODM can process and the project can place.

**When?** ``DateTimeOriginal``, because construction capture is a timeline and a file's mtime is
whenever somebody last copied it off the card.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path
from typing import Any, BinaryIO

_JPEG_SOI = b"\xff\xd8"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_TIFF_LE = b"II*\x00"
_TIFF_BE = b"MM\x00*"

#: JPEG start-of-frame markers carrying dimensions. C4 is a Huffman table and C8/CC are not frames,
#: which is why the range is enumerated rather than written as C0..CF.
_SOF_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)

_EXIF_TAGS = {
    0x010F: "make",
    0x0110: "model",
    0x0112: "orientation",
    0x0132: "datetime",
    0x8769: "_exif_ifd",
    0x8825: "_gps_ifd",
}
_EXIF_SUB_TAGS = {
    0x829A: "exposure_time",
    0x829D: "f_number",
    0x8827: "iso",
    0x9003: "datetime_original",
    0x920A: "focal_length",
    0xA002: "pixel_x_dimension",
    0xA003: "pixel_y_dimension",
    0xA405: "focal_length_35mm",
}
_GPS_TAGS = {
    0x0001: "latitude_ref",
    0x0002: "latitude",
    0x0003: "longitude_ref",
    0x0004: "longitude",
    0x0005: "altitude_ref",
    0x0006: "altitude",
    0x0007: "timestamp",
    0x0010: "image_direction_ref",
    0x0011: "image_direction",
    0x001D: "datestamp",
}

#: TIFF field type to (struct code, byte width).
_TIFF_TYPES: dict[int, tuple[str, int]] = {
    1: ("B", 1), 2: ("s", 1), 3: ("H", 2), 4: ("I", 4), 5: ("II", 8),
    6: ("b", 1), 7: ("B", 1), 8: ("h", 2), 9: ("i", 4), 10: ("ii", 8),
    11: ("f", 4), 12: ("d", 8),
}  # fmt: skip


class ImageError(ValueError):
    """An image file did not read as the format it claimed."""


# -- dimensions ---------------------------------------------------------------------------------


def _jpeg_segments(stream: BinaryIO) -> tuple[tuple[int, int] | None, list[bytes]]:
    """Walk JPEG markers for dimensions and APP1 payloads, without decoding image data."""
    stream.seek(2)
    size: tuple[int, int] | None = None
    app1: list[bytes] = []
    while True:
        marker = stream.read(2)
        if len(marker) < 2 or marker[0] != 0xFF:
            break
        code = marker[1]
        if code in (0xD8, 0xD9):
            continue
        if code == 0xDA:
            # Start of scan: everything after this is entropy-coded data.
            break
        length_bytes = stream.read(2)
        if len(length_bytes) < 2:
            break
        length = struct.unpack(">H", length_bytes)[0] - 2
        payload = stream.read(length)
        if code in _SOF_MARKERS and len(payload) >= 5:
            height, width = struct.unpack_from(">HH", payload, 1)
            size = (width, height)
        elif code == 0xE1:
            app1.append(payload)
    return size, app1


def _png_size(head: bytes) -> tuple[int, int] | None:
    if len(head) < 24 or head[12:16] != b"IHDR":
        return None
    width, height = struct.unpack_from(">II", head, 16)
    return (width, height)


# -- EXIF ---------------------------------------------------------------------------------------


def _read_ifd(
    data: bytes, offset: int, endian: str, tags: dict[int, str], *, base: int = 0
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if offset + 2 > len(data):
        return out
    (count,) = struct.unpack_from(endian + "H", data, offset)
    for index in range(count):
        entry = offset + 2 + index * 12
        if entry + 12 > len(data):
            break
        tag, field_type, values = struct.unpack_from(endian + "HHI", data, entry)
        name = tags.get(tag)
        if name is None or field_type not in _TIFF_TYPES:
            continue
        code, width = _TIFF_TYPES[field_type]
        total = width * values
        if total <= 4:
            payload_offset = entry + 8
        else:
            (payload_offset,) = struct.unpack_from(endian + "I", data, entry + 8)
            payload_offset += base
        if payload_offset + total > len(data) or payload_offset < 0:
            continue
        payload = data[payload_offset : payload_offset + total]
        out[name] = _decode_field(payload, field_type, values, endian, code)
    return out


def _decode_field(payload: bytes, field_type: int, values: int, endian: str, code: str) -> Any:
    if field_type == 2:
        return payload.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()
    if field_type in (5, 10):
        pairs = struct.unpack(endian + code * values, payload)
        rationals = [
            (pairs[i] / pairs[i + 1]) if pairs[i + 1] else 0.0 for i in range(0, len(pairs), 2)
        ]
        return rationals[0] if values == 1 else rationals
    decoded = struct.unpack(endian + code * values, payload)
    return decoded[0] if values == 1 else list(decoded)


def parse_exif(payload: bytes) -> dict[str, Any]:
    """Decode an APP1 EXIF payload into a flat dictionary. Empty for anything unreadable."""
    if not payload.startswith(b"Exif\x00\x00"):
        return {}
    tiff = payload[6:]
    if tiff[:4] == _TIFF_LE:
        endian = "<"
    elif tiff[:4] == _TIFF_BE:
        endian = ">"
    else:
        return {}
    (ifd0_offset,) = struct.unpack_from(endian + "I", tiff, 4)
    result = _read_ifd(tiff, ifd0_offset, endian, _EXIF_TAGS)

    exif_offset = result.pop("_exif_ifd", None)
    if isinstance(exif_offset, int):
        result.update(_read_ifd(tiff, exif_offset, endian, _EXIF_SUB_TAGS))
    gps_offset = result.pop("_gps_ifd", None)
    if isinstance(gps_offset, int):
        gps = _read_ifd(tiff, gps_offset, endian, _GPS_TAGS)
        coordinates = _gps_to_degrees(gps)
        if coordinates:
            result.update(coordinates)
    return result


def _dms(values: Any) -> float | None:
    if isinstance(values, (list, tuple)) and len(values) >= 3:
        return float(values[0]) + float(values[1]) / 60 + float(values[2]) / 3600
    if isinstance(values, (int, float)):
        return float(values)
    return None


def _gps_to_degrees(gps: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    latitude = _dms(gps.get("latitude"))
    longitude = _dms(gps.get("longitude"))
    if latitude is not None:
        out["latitude"] = (
            -latitude if str(gps.get("latitude_ref", "N")).upper() == "S" else latitude
        )
    if longitude is not None:
        out["longitude"] = (
            -longitude if str(gps.get("longitude_ref", "E")).upper() == "W" else longitude
        )
    altitude = gps.get("altitude")
    if isinstance(altitude, (int, float)):
        # GPSAltitudeRef 1 means below sea level. Ignoring it puts a drone underground.
        out["altitude"] = -float(altitude) if gps.get("altitude_ref") == 1 else float(altitude)
    direction = gps.get("image_direction")
    if isinstance(direction, (int, float)):
        out["image_direction"] = float(direction)
        out["image_direction_ref"] = (
            "true" if str(gps.get("image_direction_ref", "T")).upper() == "T" else "magnetic"
        )
    return out


# -- XMP ----------------------------------------------------------------------------------------

_XMP_ATTRIBUTE = re.compile(r'([A-Za-z-]+):([A-Za-z0-9_]+)\s*=\s*"([^"]*)"')
_XMP_ELEMENT = re.compile(r"<([A-Za-z-]+):([A-Za-z0-9_]+)>([^<]*)</\1:\2>")

#: The namespaces worth keeping. Everything else in an XMP packet is provenance noise for this
#: purpose, and hoovering all of it into asset metadata makes manifests unreadable.
_XMP_NAMESPACES = frozenset({"GPano", "drone-dji", "Camera", "GImage", "GAudio"})


def parse_xmp(payload: bytes) -> dict[str, Any]:
    """Pull the panorama and drone namespaces out of an XMP packet.

    Regex rather than an XML parse, deliberately: XMP in the wild is frequently truncated by writers
    that got the APP1 length wrong, and a strict parse throws away a packet that a pattern match
    reads perfectly well.
    """
    try:
        text = payload.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, Any] = {}
    for namespace, key, value in _XMP_ATTRIBUTE.findall(text):
        if namespace in _XMP_NAMESPACES:
            out[f"{namespace}:{key}"] = _coerce(value)
    for namespace, key, value in _XMP_ELEMENT.findall(text):
        if namespace in _XMP_NAMESPACES:
            out[f"{namespace}:{key}"] = _coerce(value.strip())
    return out


def _coerce(value: str) -> Any:
    lowered = value.strip().lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        if "." in value or "e" in lowered:
            return float(value)
        return int(value)
    except ValueError:
        return value


# -- summary ------------------------------------------------------------------------------------


def summarise(path: str | Path) -> dict[str, Any]:
    """Dimensions, EXIF, GPS and panorama markers for a JPEG, PNG or TIFF."""
    path = Path(path)
    summary: dict[str, Any] = {}
    with path.open("rb") as stream:
        head = stream.read(32)
        if head.startswith(_JPEG_SOI):
            summary["image_format"] = "jpeg"
            size, app1_segments = _jpeg_segments(stream)
            if size:
                summary["width"], summary["height"] = size
            for payload in app1_segments:
                if payload.startswith(b"Exif\x00\x00"):
                    exif = parse_exif(payload)
                    if exif:
                        summary["exif"] = exif
                elif b"<x:xmpmeta" in payload[:200] or payload.startswith(b"http://ns.adobe.com/"):
                    xmp = parse_xmp(payload)
                    if xmp:
                        summary["xmp"] = xmp
        elif head.startswith(_PNG_MAGIC):
            summary["image_format"] = "png"
            stream.seek(0)
            size = _png_size(stream.read(64))
            if size:
                summary["width"], summary["height"] = size
        elif head[:4] in (_TIFF_LE, _TIFF_BE):
            summary["image_format"] = "tiff"
            stream.seek(0)
            summary.update(_tiff_dimensions(stream.read(65536)))
        else:
            raise ImageError("Not a JPEG, PNG or TIFF.")

    summary.update(panorama_markers(summary))
    _lift_capture_fields(summary)
    return summary


def _tiff_dimensions(data: bytes) -> dict[str, Any]:
    endian = "<" if data[:4] == _TIFF_LE else ">"
    try:
        (ifd0,) = struct.unpack_from(endian + "I", data, 4)
        fields = _read_ifd(data, ifd0, endian, {0x0100: "width", 0x0101: "height", 0x0102: "bits"})
    except struct.error:
        return {}
    out: dict[str, Any] = {}
    if isinstance(fields.get("width"), int):
        out["width"] = fields["width"]
    if isinstance(fields.get("height"), int):
        out["height"] = fields["height"]
    # A GeoTIFF is a TIFF carrying key 33922 or 34735. Worth naming, because an orthomosaic and a
    # scanned drawing arrive with the same extension and want opposite treatment.
    if b"\x82\x2f" in data[:4096] or b"ModelTiepoint" in data[:65536]:
        out["geotiff"] = True
    return out


def panorama_markers(summary: dict[str, Any]) -> dict[str, Any]:
    """Decide whether an image is an equirectangular panorama, and say on what evidence."""
    xmp = summary.get("xmp") or {}
    width = summary.get("width")
    height = summary.get("height")
    out: dict[str, Any] = {}

    projection = str(xmp.get("GPano:ProjectionType", "")).lower()
    if projection:
        out["projection"] = projection
    declared = projection == "equirectangular" or bool(xmp.get("GPano:UsePanoramaViewer"))
    ratio_suggests = bool(width and height and abs(width - 2 * height) <= max(2, height // 100))

    if declared:
        out["is_panorama"] = True
        out["panorama_evidence"] = "GPano XMP declares an equirectangular projection"
    elif ratio_suggests:
        out["is_panorama"] = True
        out["panorama_evidence"] = "2:1 aspect ratio -- inferred, not declared"
    else:
        out["is_panorama"] = False

    heading = xmp.get("GPano:PoseHeadingDegrees")
    if isinstance(heading, (int, float)):
        out["pano_heading"] = float(heading)
    for source, target in (
        ("GPano:PosePitchDegrees", "pano_pitch"),
        ("GPano:PoseRollDegrees", "pano_roll"),
        ("GPano:CroppedAreaImageWidthPixels", "pano_cropped_width"),
        ("GPano:FullPanoWidthPixels", "pano_full_width"),
    ):
        value = xmp.get(source)
        if isinstance(value, (int, float)):
            out[target] = float(value)
    if out.get("pano_cropped_width") and out.get("pano_full_width"):
        out["pano_partial"] = out["pano_cropped_width"] < out["pano_full_width"]
    return out


def _lift_capture_fields(summary: dict[str, Any]) -> None:
    """Promote the handful of EXIF/XMP fields the pipeline actually branches on.

    Nested under ``exif`` they are preserved; lifted to the top they are queryable without every
    consumer knowing which of three namespaces a drone happened to write its yaw into.
    """
    exif = summary.get("exif") or {}
    xmp = summary.get("xmp") or {}

    for source, target in (("latitude", "latitude"), ("longitude", "longitude")):
        if isinstance(exif.get(source), (int, float)):
            summary[target] = float(exif[source])
    if isinstance(exif.get("altitude"), (int, float)):
        summary["altitude"] = float(exif["altitude"])
    elif isinstance(xmp.get("drone-dji:AbsoluteAltitude"), (int, float)):
        summary["altitude"] = float(xmp["drone-dji:AbsoluteAltitude"])

    if isinstance(xmp.get("drone-dji:RelativeAltitude"), (int, float)):
        summary["relative_altitude"] = float(xmp["drone-dji:RelativeAltitude"])
    for source, target in (
        ("drone-dji:GimbalPitchDegree", "pitch"),
        ("drone-dji:GimbalRollDegree", "roll"),
    ):
        if isinstance(xmp.get(source), (int, float)):
            summary[target] = float(xmp[source])

    # Heading precedence, strongest first. The panorama case is the one that has to come before
    # EXIF: a 360 image's GPSImgDirection is whichever way the rig happened to be pointing when
    # the shutter first fired, whereas GPano:PoseHeadingDegrees is the heading of the stitched
    # image's centre column -- which is the number a viewer needs to align the sphere to north.
    is_panorama = bool(summary.get("is_panorama"))
    candidates: list[Any] = [xmp.get("drone-dji:GimbalYawDegree")]
    if is_panorama:
        candidates += [summary.get("pano_heading"), exif.get("image_direction")]
    else:
        candidates += [exif.get("image_direction"), summary.get("pano_heading")]
    for candidate in candidates:
        if isinstance(candidate, (int, float)):
            summary["yaw"] = float(candidate)
            break

    captured = exif.get("datetime_original") or exif.get("datetime")
    if isinstance(captured, str) and len(captured) >= 19:
        # EXIF writes "2024:06:01 14:22:31". Normalised to ISO, and marked naive rather than
        # stamped with a timezone the file never claimed.
        date, _, time = captured.partition(" ")
        summary["captured_at"] = f"{date.replace(':', '-')}T{time}"
    for source, target in (("make", "camera_make"), ("model", "camera_model")):
        if exif.get(source):
            summary[target] = exif[source]
