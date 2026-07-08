"""BFAST / G3D / VIM reader (G2) — pure-Python interop for the Ara3D/VIM binary family.

Re-implemented from the public BFAST format (Ara3D SDK is MIT; this is an independent Python reader of
the documented layout — no Ara3D code copied). BFAST ("Binary Format for Array Serialization and
Transmission") is a trivial container: a 32-byte header, then a table of (begin, end) byte ranges, then
the raw buffers. Buffer 0 is a name list (null-separated); buffers 1..n are the named data arrays.

* **BFAST** — the container (`read_bfast` / `write_bfast`).
* **G3D** — geometry-in-BFAST: buffers named like ``g3d:vertex:position:0:float32:3`` / ``g3d:index:…``.
  `g3d_geometry` extracts vertex/index counts + bounding box (numpy).
* **VIM** — a BFAST whose buffers include ``header`` (key=value string), ``geometry`` (a nested G3D
  BFAST), and entity tables. `vim_info` reports schema/version + buffer inventory + geometry stats.

Scope: a **data/inspection** interop path (open + summarise .vim/.g3d, feed the columnar index). Full
VIM entity-table decode + viewer streaming is a follow-up — the format's entity tables are version-
dependent; this reads what is stable across versions.
"""
from __future__ import annotations

import struct
from typing import Any

import numpy as np

MAGIC = 0xBFA5          # little-endian BFAST magic; 0xA5BF signals opposite endianness
_ALIGN = 32


def read_bfast(data: bytes) -> dict[str, bytes]:
    """Parse a BFAST container into an ordered {name: raw-bytes} dict. Ranges are absolute file offsets,
    so buffer alignment is irrelevant to reading."""
    if len(data) < 32:
        raise ValueError("not a BFAST file (shorter than the 32-byte header)")
    magic, _data_start, _data_end, n = struct.unpack_from("<qqqq", data, 0)
    if magic != MAGIC:
        if magic == 0xA5BF00000000 or (magic >> 48) == 0xA5BF:
            raise ValueError("big-endian BFAST not supported by this reader")
        raise ValueError(f"not a BFAST file (bad magic {magic:#x})")
    if n <= 0:
        return {}
    ranges = [struct.unpack_from("<qq", data, 32 + i * 16) for i in range(n)]
    name_bytes = data[ranges[0][0]:ranges[0][1]]
    names = [s.decode("utf-8", "ignore") for s in name_bytes.split(b"\x00") if s]
    out: dict[str, bytes] = {}
    for i in range(1, n):
        nm = names[i - 1] if (i - 1) < len(names) else f"buffer_{i}"
        out[nm] = data[ranges[i][0]:ranges[i][1]]
    return out


def write_bfast(buffers: dict[str, bytes]) -> bytes:
    """Serialise {name: bytes} to a BFAST container (aligned data buffers). Useful for round-trips."""
    names = list(buffers)
    name_buf = ("\x00".join(names) + "\x00").encode("utf-8") if names else b""
    arrays = [name_buf, *[buffers[n] for n in names]]
    n = len(arrays)

    def align(x: int) -> int:
        return (x + _ALIGN - 1) // _ALIGN * _ALIGN
    ranges_off = 32
    data_start = align(ranges_off + n * 16)
    ranges, cursor = [], data_start
    for a in arrays:
        begin = align(cursor)
        ranges.append((begin, begin + len(a)))
        cursor = begin + len(a)
    data_end = ranges[-1][1] if ranges else data_start
    out = bytearray(align(data_end))
    struct.pack_into("<qqqq", out, 0, MAGIC, data_start, data_end, n)
    for i, (b, e) in enumerate(ranges):
        struct.pack_into("<qq", out, 32 + i * 16, b, e)
        out[b:e] = arrays[i]
    return bytes(out)


# --- G3D ------------------------------------------------------------------------------------------
_DTYPES = {"float32": np.float32, "float64": np.float64, "int8": np.int8, "uint8": np.uint8,
           "int16": np.int16, "uint16": np.uint16, "int32": np.int32, "uint32": np.uint32,
           "int64": np.int64}


def _attr(name: str) -> dict[str, Any] | None:
    """Parse a G3D attribute descriptor 'g3d:<assoc>:<semantic>:<index>:<dtype>:<arity>'."""
    parts = name.split(":")
    if len(parts) < 6 or parts[0] != "g3d":
        return None
    return {"assoc": parts[1], "semantic": parts[2], "index": parts[3],
            "dtype": parts[4], "arity": int(parts[5]) if parts[5].isdigit() else 1}


def g3d_geometry(buffers: dict[str, bytes]) -> dict[str, Any]:
    """Vertex/index counts + bounding box from a G3D buffer set."""
    verts = faces = None
    vbbox = None
    attrs = []
    for name, raw in buffers.items():
        a = _attr(name)
        if not a:
            continue
        attrs.append(a["semantic"])
        dt = _DTYPES.get(a["dtype"])
        if dt is None:
            continue
        arr = np.frombuffer(raw, dtype=dt)
        if a["semantic"] == "position" and a["arity"] == 3 and arr.size:
            verts = arr.reshape(-1, 3).astype(np.float64)
            vbbox = [verts.min(axis=0).tolist(), verts.max(axis=0).tolist()]
        elif a["semantic"] == "index":
            faces = arr
    return {"is_g3d": bool(attrs), "attributes": sorted(set(attrs)),
            "vertices": int(len(verts)) if verts is not None else 0,
            "indices": int(len(faces)) if faces is not None else 0,
            "triangles": int(len(faces) // 3) if faces is not None else 0,
            "bbox": vbbox}


# --- VIM ------------------------------------------------------------------------------------------
def _parse_header(raw: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in raw.decode("utf-8", "ignore").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def vim_info(data: bytes) -> dict[str, Any]:
    """Summarise a VIM file: schema/version (from its `header`), buffer inventory, and geometry stats
    (if a nested `geometry` G3D is present)."""
    top = read_bfast(data)
    header = _parse_header(top.get("header", b""))
    geom = {}
    if "geometry" in top:
        try:
            geom = g3d_geometry(read_bfast(top["geometry"]))
        except (ValueError, OSError):
            geom = {"is_g3d": False}
    return {
        "format": "VIM", "buffers": list(top),
        "vim_version": header.get("vim") or header.get("version"),
        "generator": header.get("generator"), "schema": header.get("schema"),
        "header": header, "geometry": geom,
        "note": "VIM data-layer inspection (buffers + header + geometry stats). Full entity-table decode "
                "and viewer streaming are a follow-up.",
    }
