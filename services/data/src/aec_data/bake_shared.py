"""
Baked geometry shared across worker processes.

The in-process byte budget in `drawings.py` bounds **one** worker. A server runs several — uvicorn
with `--workers N`, or gunicorn — and a Python dict cannot span processes, so the same model is
tessellated once per worker. On a big model that is the single most expensive thing this system does,
paid N times for no benefit.

`diskcache` earns its dependency here in a way `cachetools` did not: this needs a store that is
correct when several processes write the same key at once, and hand-writing that over SQLite is
exactly the kind of code that works in testing and corrupts under load.

**Disabled unless `AEC_BAKE_SHARE_DIR` is set.** A cache that silently starts writing gigabytes into
a temp directory the operator never chose is a surprise, and on a single-worker deployment it buys
nothing — the in-process cache already covers that case.

The stored value is JSON lists of mesh arrays, not trimesh objects and not pickle. Vertices and
faces round-trip as nested lists (numpy `.tolist()` on the way in). What comes back is what went
in or nothing at all. JSONDisk is the answer to CVE-2025-69872 for this store: the values were
already arrays, so pickle was never load-bearing.
"""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger("aec.bake_share")

_ENV_DIR = "AEC_BAKE_SHARE_DIR"
_ENV_MB = "AEC_BAKE_SHARE_MB"

_cache: Any = None
_tried = False


def enabled() -> bool:
    return bool(os.environ.get(_ENV_DIR))


def _as_list(value):
    """JSONDisk cannot store numpy arrays or tuples. Nested lists round-trip as themselves.

    Bytes are refused (TypeError) rather than left for pickle: JSONDisk would fail the write
    anyway, and a silent fallback to Disk is exactly the advisory path this exists to close.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        raise TypeError("bake share stores JSON, not bytes")
    if hasattr(value, "tolist"):
        return _as_list(value.tolist())
    if isinstance(value, tuple):
        return [_as_list(x) for x in value]
    if isinstance(value, list):
        return [_as_list(x) for x in value]
    if isinstance(value, dict):
        return {str(k): _as_list(v) for k, v in value.items()}
    raise TypeError(f"bake share cannot JSON-encode {type(value).__name__}")


def _jsonable(payload):
    """Mesh rows → nested lists, or None if the shape is wrong.

    Production writes `(guid, cls, vertices, faces)` (R38-PLAN-IDENTITY). A payload we cannot
    encode is refused rather than pickled — falling back to pickle on 'just this one array'
    would re-open the advisory this exists to answer.
    """
    rows = []
    try:
        for row in payload:
            if len(row) == 4:
                guid, cls, verts, faces = row
                rows.append([guid, cls, _as_list(verts), _as_list(faces)])
            elif len(row) == 3:
                cls, verts, faces = row
                rows.append([cls, _as_list(verts), _as_list(faces)])
            else:
                return None
    except (TypeError, ValueError):
        return None
    return rows


def _from_json(raw):
    if not isinstance(raw, list):
        return None
    out = []
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) not in (3, 4):
            return None
        if len(row) == 4:
            guid, cls, verts, faces = row
            out.append((guid, cls, verts, faces))
        else:
            cls, verts, faces = row
            out.append((cls, verts, faces))
    return out


def _store():
    """The shared cache, or None. Opened once; a failure to open disables sharing rather than
    breaking rendering — geometry must still be produced on a box where the directory is unwritable."""
    global _cache, _tried
    if _cache is not None or _tried:
        return _cache
    _tried = True
    d = os.environ.get(_ENV_DIR)
    if not d:
        return None
    try:
        import diskcache
        limit = int(os.environ.get(_ENV_MB, "4096")) * 1024 * 1024
        os.makedirs(d, mode=0o700, exist_ok=True)
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass
        # JSONDisk: the pickle path is CVE-2025-69872. Geometry is arrays; JSON lists are enough.
        _cache = diskcache.Cache(
            d, size_limit=limit, eviction_policy="least-recently-used",
            disk=diskcache.JSONDisk)
        log.info("shared bake cache at %s (limit %d MB, JSONDisk)", d, limit // (1024 * 1024))
    except Exception as exc:            # noqa: BLE001 — sharing is an optimisation, never a hard dep
        log.warning("shared bake cache unavailable (%s) — falling back to per-process only", exc)
        _cache = None
    return _cache


def get(key: str):
    """Baked meshes for a content key, or None.

    Returns `[(ifc_class, vertices, faces), ...]` — arrays, not trimesh objects. The caller rebuilds
    the meshes, which keeps the on-disk format independent of the geometry library's version.
    """
    c = _store()
    if c is None:
        return None
    try:
        return _from_json(c.get(key))
    except Exception:                   # noqa: BLE001 — a corrupt or locked entry is a miss
        log.debug("shared bake read failed for %s", key, exc_info=True)
        return None


def put(key: str, payload) -> bool:
    """Store baked arrays under a content key. Never raises: a cache that cannot write must not stop
    a drawing being produced. Returns whether it actually stored."""
    c = _store()
    if c is None:
        return False
    try:
        encoded = _jsonable(payload)
        if encoded is None:
            return False
        return bool(c.set(key, encoded))
    except Exception:                   # noqa: BLE001
        log.debug("shared bake write failed for %s", key, exc_info=True)
        return False


def stats() -> dict:
    """What the shared cache holds — so the budget can be observed rather than assumed, the same
    reason `bake_cache_stats` exists for the in-process half."""
    c = _store()
    if c is None:
        return {"enabled": False, "reason": "AEC_BAKE_SHARE_DIR not set" if not enabled()
                else "cache could not be opened"}
    try:
        return {"enabled": True, "entries": len(c), "bytes": c.volume(),
                "limit_bytes": c.size_limit, "directory": c.directory}
    except Exception as exc:            # noqa: BLE001
        return {"enabled": True, "error": str(exc)[:120]}


def close() -> None:
    """Release the cache's file handles.

    Not needed in a server — the process holds the cache for its lifetime. It exists because a
    long-running process is not the only caller: a test, a CLI run, or a worker being recycled wants
    the SQLite file released, and on Windows an open handle makes the directory undeletable. A
    cleanup that raises would be worse than one that does nothing, so it never does.
    """
    global _cache, _tried
    c, _cache, _tried = _cache, None, False
    if c is not None:
        try:
            c.close()
        except Exception:               # noqa: BLE001 — closing must never raise
            pass
