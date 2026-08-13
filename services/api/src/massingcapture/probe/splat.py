"""Gaussian splat containers: ``.splat``, ``.ksplat``, ``.spz``, ``.sog``.

Splats get their own module and their own asset class because of a hard constraint from the capture
side: point-cloud output and 3DGS output **cannot be converted into each other after processing**.
A rig that produces both produces them from the same raw capture on two separate paths, and a
project that treats one as a fallback for the other will eventually measure off a radiance field.

So this module identifies and counts. It does not convert, and nothing downstream offers to.

PLY-encoded splats are handled in :mod:`massingcapture.probe.ply`, because the discrimination has to
happen at the header where the ``f_dc_0`` property lives.
"""

from __future__ import annotations

import gzip
import json
import struct
import zipfile
from pathlib import Path
from typing import Any

#: The ``.splat`` record: 3 float32 position, 3 float32 scale, 4 uint8 colour, 4 uint8 rotation.
SPLAT_RECORD_SIZE = 32

#: ``.spz`` magic, little-endian -- the ASCII bytes "NGSP".
_SPZ_MAGIC = 0x5053474E


class SplatError(ValueError):
    """A splat container did not read as its format."""


def summarise_splat(path: str | Path, *, max_samples: int = 500_000) -> dict[str, Any]:
    """Count and bound a raw ``.splat``.

    The format has no header at all -- it is a flat array of 32-byte records -- so a file whose size
    is not a multiple of the record size is either truncated or not a ``.splat``, and saying so is
    the only validation available.
    """
    path = Path(path)
    size = path.stat().st_size
    if size == 0 or size % SPLAT_RECORD_SIZE:
        raise SplatError(
            f"A .splat is a flat array of {SPLAT_RECORD_SIZE}-byte records; "
            f"{size} bytes is not a whole number of them."
        )
    count = size // SPLAT_RECORD_SIZE
    step = max(1, -(-count // max_samples))

    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    position = struct.Struct("<3f")
    with path.open("rb") as stream:
        index = 0
        while index < count:
            stream.seek(index * SPLAT_RECORD_SIZE)
            chunk = stream.read(12)
            if len(chunk) < 12:
                break
            for axis, value in enumerate(position.unpack(chunk)):
                if value < lo[axis]:
                    lo[axis] = value
                if value > hi[axis]:
                    hi[axis] = value
            index += step

    summary: dict[str, Any] = {
        "splat_format": "splat",
        "gaussian_count": count,
        "spherical_harmonic_bands": 0,
        "note": "Raw .splat carries DC colour only -- no view-dependent harmonics.",
    }
    if lo[0] != float("inf"):
        summary["bounds"] = [lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]]
        summary["bounds_sampled"] = step > 1
    return summary


def summarise_spz(path: str | Path) -> dict[str, Any]:
    """Read the ``.spz`` header. The payload is gzip, and the header is the first 16 bytes of it."""
    path = Path(path)
    with gzip.open(path, "rb") as stream:
        head = stream.read(16)
    if len(head) < 16:
        raise SplatError("Compressed .spz payload is shorter than its own header.")
    magic, version, count = struct.unpack_from("<III", head, 0)
    if magic != _SPZ_MAGIC:
        raise SplatError("Decompressed .spz payload does not start with the NGSP magic.")
    degree, fractional_bits, flags = struct.unpack_from("<3B", head, 12)
    return {
        "splat_format": "spz",
        "spz_version": version,
        "gaussian_count": count,
        "spherical_harmonic_bands": degree,
        "fractional_bits": fractional_bits,
        # Bit 0 marks a scene whose up axis is +Y rather than +Z. Recorded rather than corrected:
        # rotating a visual layer to match a project frame is an alignment decision, not a probe's.
        "antialiased": bool(flags & 0x01),
    }


def summarise_sog(path: str | Path) -> dict[str, Any]:
    """A ``.sog`` is a container of compressed textures plus a ``meta.json`` describing them."""
    path = Path(path)
    if not zipfile.is_zipfile(path):
        raise SplatError("A .sog is expected to be a zip container; this one is not.")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        meta: dict[str, Any] = {}
        for candidate in ("meta.json", "metadata.json"):
            if candidate in names:
                try:
                    meta = json.loads(archive.read(candidate).decode("utf-8"))
                except (ValueError, KeyError):
                    meta = {}
                break
    summary: dict[str, Any] = {"splat_format": "sog", "entries": names[:64]}
    count = meta.get("count") or meta.get("numSplats")
    if isinstance(count, int):
        summary["gaussian_count"] = count
    if isinstance(meta.get("shBands"), int):
        summary["spherical_harmonic_bands"] = meta["shBands"]
    means = meta.get("means") or {}
    if isinstance(means, dict) and isinstance(means.get("mins"), list):
        mins, maxs = means.get("mins"), means.get("maxs")
        if isinstance(maxs, list) and len(mins) >= 3 and len(maxs) >= 3:
            summary["bounds"] = [*(float(v) for v in mins[:3]), *(float(v) for v in maxs[:3])]
            summary["bounds_sampled"] = False
    return summary


def summarise_ksplat(path: str | Path) -> dict[str, Any]:
    """``.ksplat`` carries a version byte and a section table; the layout is viewer-specific.

    Reported rather than parsed. The format is defined by one viewer implementation and has changed
    layout between its own versions, so a parse written against today's would silently misread
    tomorrow's -- and nothing in this pipeline needs the interior of a visual-only asset.
    """
    path = Path(path)
    with path.open("rb") as stream:
        head = stream.read(4)
    return {
        "splat_format": "ksplat",
        "ksplat_version": head[0] if head else None,
        "note": "Viewer-specific container; contents are not inspected.",
    }


def summarise(path: str | Path) -> dict[str, Any]:
    """Dispatch on extension. Splat containers have no shared magic to dispatch on instead."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".splat":
        return summarise_splat(path)
    if suffix == ".spz":
        return summarise_spz(path)
    if suffix == ".sog":
        return summarise_sog(path)
    if suffix == ".ksplat":
        return summarise_ksplat(path)
    raise SplatError(f'No splat reader for "{suffix}".')
