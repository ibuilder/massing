"""In-process model **property index** — the columnar element store the viewer + several engines read.
Loaded from the uploaded `props.json` (produced by `aec_data.cli index`), keyed `pid -> {guid -> record}`,
bounded LRU so a worker serving many projects doesn't hold every project's elements forever. Plus the
model-version-keyed result cache for the expensive read-only scans (facets/color-by/qa/…).

This lives in its own engine (not `routers/properties.py`) because the index is consumed by engines
(`bim_kpi`, `energy`, `evm`, `mcp_tools`, `reports`) as well as the router — an engine importing a
router's private globals is the wrong dependency direction. Public API: `ensure_loaded`, `get_index`,
`get_meta`, `load`, `scan_cached`. The `_`-prefixed names are kept as compatibility aliases."""
from __future__ import annotations

import gzip
import json
import os
import threading
from collections.abc import Callable
from typing import Any

from . import storage

# project_id -> { guid -> element record } (loaded from uploaded props.json). Bounded LRU so a worker
# that serves many projects doesn't hold every project's full element list in memory forever; evicted
# projects are transparently reloaded from storage on next access.
_INDEX: dict[str, dict[str, dict]] = {}
_META: dict[str, dict] = {}
_LRU: list[str] = []                    # pids in least→most-recently-used order
_MAX_PROJECTS = int(os.environ.get("AEC_PROPS_CACHE_PROJECTS", "16"))
# FastAPI runs sync endpoints on multiple threadpool threads, all of which populate/evict these caches.
# Serialize the populate+evict so an eviction can't fire mid-populate and drop a live project.
_INDEX_LOCK = threading.Lock()


def _touch(pid: str) -> None:
    """Mark `pid` most-recently-used and evict the least-recently-used over the cap.
    Caller must hold _INDEX_LOCK (only invoked from load())."""
    if pid in _LRU:
        _LRU.remove(pid)
    _LRU.append(pid)
    while len(_LRU) > max(1, _MAX_PROJECTS):
        old = _LRU.pop(0)
        _INDEX.pop(old, None)
        _META.pop(old, None)


def load(pid: str, payload: dict) -> int:
    """Populate the cache for `pid` from a parsed props.json payload. Returns the element count."""
    with _INDEX_LOCK:
        _META[pid] = {k: payload.get(k) for k in ("schema", "project", "counts", "facets")}
        _INDEX[pid] = {e["guid"]: e for e in payload.get("elements", [])}
        _touch(pid)
        return len(_INDEX[pid])


def ensure_loaded(pid: str) -> None:
    """Load the project's index from object storage if it isn't already cached."""
    if pid in _INDEX:
        return
    key = f"{pid}/props.json"
    if storage.exists(key):
        load(pid, json.loads(storage.get(key)))


def get_index(pid: str) -> dict[str, dict] | None:
    """The `{guid -> record}` map for a project (None if never uploaded). Call ensure_loaded first if
    you want an eviction-safe read."""
    return _INDEX.get(pid)


def get_meta(pid: str) -> dict | None:
    return _META.get(pid)


# Per-model-signature result cache for the expensive read-only scans (facets/color-by/qa/code/…). These
# are recomputed O(n·psets) per request today; the result only changes when the model does, so we key
# the cache on the model version (bumped by model_events on publish) and evict LRU-style. Single worker →
# in-process only. Multi-worker → also shared via Redis (gzip+json values, TTL) when AEC_REDIS_URL is
# set, so one worker's scan is reused by every other; fail-open to in-process on any Redis error.
_SCAN_CACHE: dict[tuple, object] = {}
_SCAN_CACHE_ORDER: list[tuple] = []
_SCAN_CACHE_MAX = 400
_SCAN_TTL = int(os.environ.get("AEC_SCAN_CACHE_TTL", "3600") or "3600")

_scan_redis = None
if os.environ.get("AEC_REDIS_URL", "").strip():
    try:                                    # lazy: redis is only a dep when REDIS_URL is set
        import redis as _redis_lib
        _scan_redis = _redis_lib.from_url(os.environ["AEC_REDIS_URL"].strip(),
                                          socket_timeout=0.25, socket_connect_timeout=0.25)
    except Exception:                        # noqa: BLE001 — redis missing / bad URL → in-process only
        _scan_redis = None


def scan_cached(pid: str, key: str, compute: Callable[[], Any]) -> Any:
    """Return a cached scan result for (pid, model-version, key), computing + caching on miss.
    Invalidated automatically when the model version bumps (model_events)."""
    from . import model_events
    ver = model_events.current(pid)["version"]
    rk = None
    if _scan_redis is not None:
        rk = f"scan:{pid}:{ver}:{key}"
        try:                                 # shared read across workers
            raw = _scan_redis.get(rk)
            if raw is not None:
                return json.loads(gzip.decompress(raw))
        except Exception:                    # noqa: BLE001 — Redis hiccup → fall through to in-process
            rk = None
    lck = (pid, ver, key)
    hit = _SCAN_CACHE.get(lck)
    if hit is not None:
        return hit
    res = compute()
    _SCAN_CACHE[lck] = res
    _SCAN_CACHE_ORDER.append(lck)
    while len(_SCAN_CACHE_ORDER) > _SCAN_CACHE_MAX:
        _SCAN_CACHE.pop(_SCAN_CACHE_ORDER.pop(0), None)
    if rk is not None:
        try:
            _scan_redis.setex(rk, _SCAN_TTL, gzip.compress(json.dumps(res).encode("utf-8")))
        except Exception:                    # noqa: BLE001 — caching is best-effort
            pass
    return res


# Compatibility aliases for the existing call sites (router + engines) — same objects, so mutation of
# _INDEX/_META stays shared.
_ensure_loaded = ensure_loaded
_load = load
_scan_cached = scan_cached
