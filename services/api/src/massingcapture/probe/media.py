"""ISO base media files: MP4, MOV, and the 360 variants.

360 video is the cheapest way to capture a construction walkthrough -- one person, one pass, four
minutes a floor -- and the most common thing a project is handed. Turning it into a walkthrough
means extracting frames as pano nodes, and *that* means knowing three things first: how long it is,
what resolution, and whether it is actually spherical.

The third is the one worth reading properly. A file is spherical if it says so, in one of two
places: the modern ``sv3d``/``svhd`` box from the Spherical Video V2 specification, or the older
Spherical Video V1 XML in a ``uuid`` box. Guessing from a 2:1 frame aspect catches anamorphic
footage and misses every 190-degree fisheye dual-lens file, so both markers are checked and the
inference is reported as an inference.

Frame extraction itself is FFmpeg's job and lives behind the ``media`` adapter. This module decides
whether extraction is worth starting.
"""

from __future__ import annotations

import contextlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

#: The Spherical Video V1 uuid box identifier.
_SPHERICAL_V1_UUID = bytes.fromhex("ffcc8263f8554a938814587a02521fdd")

#: Boxes worth descending into. Everything else is skipped by length, which is what makes walking a
#: 12 GB file cost a few dozen seeks.
_CONTAINERS = frozenset({b"moov", b"trak", b"mdia", b"minf", b"stbl", b"udta", b"edts"})

#: Seconds between the QuickTime epoch (1904-01-01) and the Unix epoch.
_QUICKTIME_EPOCH_OFFSET = 2_082_844_800


class MediaError(ValueError):
    """A media container did not read as one."""


@dataclass(frozen=True)
class Box:
    kind: bytes
    start: int
    size: int
    header_size: int

    @property
    def payload_start(self) -> int:
        return self.start + self.header_size

    @property
    def end(self) -> int:
        return self.start + self.size


def _read_box(stream: BinaryIO, offset: int, limit: int) -> Box | None:
    if offset + 8 > limit:
        return None
    stream.seek(offset)
    head = stream.read(8)
    if len(head) < 8:
        return None
    size, kind = struct.unpack(">I4s", head)
    header_size = 8
    if size == 1:
        extended = stream.read(8)
        if len(extended) < 8:
            return None
        size = struct.unpack(">Q", extended)[0]
        header_size = 16
    elif size == 0:
        size = limit - offset
    if size < header_size:
        return None
    return Box(kind, offset, size, header_size)


def _walk(stream: BinaryIO, start: int, limit: int, depth: int = 0):
    """Yield boxes depth-first. Depth-capped, because a malformed file can nest indefinitely."""
    offset = start
    while offset < limit and depth < 8:
        box = _read_box(stream, offset, limit)
        if box is None:
            return
        yield box, depth
        if box.kind in _CONTAINERS:
            yield from _walk(stream, box.payload_start, min(box.end, limit), depth + 1)
        offset = box.end
        if box.size <= 0:
            return


def summarise(path: str | Path) -> dict[str, Any]:
    """Duration, resolution, track count and spherical markers, without decoding a frame."""
    path = Path(path)
    size = path.stat().st_size
    summary: dict[str, Any] = {"container": "iso-bmff", "file_size": size}

    with path.open("rb") as stream:
        brand_box = _read_box(stream, 0, size)
        if brand_box is None:
            raise MediaError("File does not begin with a readable ISO base media box.")
        if brand_box.kind == b"ftyp":
            stream.seek(brand_box.payload_start)
            brand = stream.read(4)
            summary["major_brand"] = brand.decode("ascii", errors="replace").strip()

        tracks: list[dict[str, Any]] = []
        spherical_evidence: list[str] = []
        for box, _depth in _walk(stream, 0, size):
            if box.kind == b"mvhd":
                stream.seek(box.payload_start)
                payload = stream.read(min(box.size - box.header_size, 120))
                summary.update(_parse_mvhd(payload))
            elif box.kind == b"tkhd":
                stream.seek(box.payload_start)
                payload = stream.read(min(box.size - box.header_size, 92))
                track = _parse_tkhd(payload)
                if track:
                    tracks.append(track)
            elif box.kind in (b"sv3d", b"svhd", b"proj", b"prhd", b"equi"):
                spherical_evidence.append(box.kind.decode("ascii"))
            elif box.kind == b"uuid":
                stream.seek(box.payload_start)
                identifier = stream.read(16)
                if identifier == _SPHERICAL_V1_UUID:
                    spherical_evidence.append("spherical-video-v1")
                    payload = stream.read(min(box.size - box.header_size - 16, 8192))
                    summary.update(_parse_spherical_v1(payload))

    if tracks:
        summary["tracks"] = tracks
        video = [t for t in tracks if t.get("width") and t.get("height")]
        if video:
            widest = max(video, key=lambda t: t["width"] * t["height"])
            summary["width"] = widest["width"]
            summary["height"] = widest["height"]

    if spherical_evidence:
        summary["is_spherical"] = True
        summary["spherical_evidence"] = sorted(set(spherical_evidence))
    else:
        width, height = summary.get("width"), summary.get("height")
        ratio_suggests = bool(width and height and abs(width - 2 * height) <= max(2, height // 100))
        summary["is_spherical"] = ratio_suggests
        if ratio_suggests:
            summary["spherical_evidence"] = ["2:1 aspect ratio -- inferred, not declared"]

    duration = summary.get("duration_seconds")
    if duration and summary.get("width"):
        # A rough budget for the frame-extraction job the planner will schedule.
        summary["estimated_pano_frames_at_1fps"] = int(duration)
    return summary


def _parse_mvhd(payload: bytes) -> dict[str, Any]:
    if len(payload) < 4:
        return {}
    version = payload[0]
    try:
        if version == 1:
            created, _modified, timescale, duration = struct.unpack_from(">QQIQ", payload, 4)
        else:
            created, _modified, timescale, duration = struct.unpack_from(">IIII", payload, 4)
    except struct.error:
        return {}
    out: dict[str, Any] = {"timescale": timescale}
    if timescale:
        out["duration_seconds"] = round(duration / timescale, 3)
    if created > _QUICKTIME_EPOCH_OFFSET:
        from datetime import datetime, timezone

        moment = datetime.fromtimestamp(created - _QUICKTIME_EPOCH_OFFSET, tz=timezone.utc)
        out["created"] = moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return out


def _parse_tkhd(payload: bytes) -> dict[str, Any] | None:
    if len(payload) < 4:
        return None
    version = payload[0]
    offset = 4 + (32 if version == 1 else 20)
    # Track id sits at a version-dependent offset; width and height are the last two 16.16 fixed
    # point fields of the box, which is the stable way to find them.
    if len(payload) < offset + 60:
        return None
    try:
        width, height = struct.unpack_from(">II", payload, len(payload) - 8)
    except struct.error:
        return None
    track: dict[str, Any] = {}
    if width and height:
        track["width"] = width >> 16
        track["height"] = height >> 16
    with contextlib.suppress(struct.error):
        track["track_id"] = struct.unpack_from(">I", payload, 4 + (16 if version == 1 else 8))[0]
    return track or None


def _parse_spherical_v1(payload: bytes) -> dict[str, Any]:
    """The V1 spec puts an RDF/XML blob in the uuid box. Only three fields matter."""
    text = payload.decode("utf-8", errors="replace")
    out: dict[str, Any] = {}
    for tag, key in (
        ("ProjectionType", "projection"),
        ("StitchingSoftware", "stitching_software"),
        ("InitialViewHeadingDegrees", "initial_heading"),
    ):
        marker = f"<GSpherical:{tag}>"
        start = text.find(marker)
        if start == -1:
            continue
        end = text.find("</", start)
        value = text[start + len(marker) : end].strip()
        if key == "initial_heading":
            try:
                out[key] = float(value)
            except ValueError:
                continue
        else:
            out[key] = value
    return out
