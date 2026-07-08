"""Model-change events — the propagation signal behind live 2D regeneration.

The 2D drawings (plans / sections / elevations) render **on demand** from the live model, so "keep the
2D in sync with the model" reduces to "tell everyone the moment the model changed, so they regenerate."
This is a per-project monotonic version that is **bumped when a new properties index is published** (the
canonical 'the model changed' signal). Clients learn about it two ways:

* pull — ``GET /drawings/sync-status`` returns the current ``version`` + content ``signature``;
* push — ``GET /drawings/stream`` (SSE) emits the new version the instant it changes, so open drawing
  views refresh themselves without polling.

**Multi-worker:** when ``AEC_REDIS_URL`` is set the version + signature live in a shared Redis hash, so a
publish on any worker is visible to an SSE stream on any other worker (an atomic ``HINCRBY``). This
mirrors how the rate-limiter / login-lockout share state. Redis is **fail-open** — any Redis error falls
back to the in-process registry, so the eventing infra can never take the API down (at worst a blip
degrades to per-worker versions until Redis recovers). Single-worker / no-Redis dev stays fully
in-process with zero config.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any

_LOCK = threading.Lock()
_STATE: dict[str, dict[str, Any]] = {}          # pid -> {version, signature, at}  (in-process fallback)

_REDIS_URL = os.environ.get("AEC_REDIS_URL", "").strip()
_redis = None
if _REDIS_URL:
    try:                                        # lazy: redis is only a dependency when REDIS_URL is set
        import redis as _redis_mod
        _redis = _redis_mod.from_url(_REDIS_URL, socket_timeout=0.25, socket_connect_timeout=0.25,
                                     decode_responses=True)
    except Exception:                            # noqa: BLE001 — redis not installed / bad URL → in-process
        _redis = None

_KEY = "model:ev:{pid}"                          # a Redis hash {version, signature, at} per project


def _bump_local(pid: str, signature: str | None) -> dict[str, Any]:
    with _LOCK:
        prev = _STATE.get(pid) or {"version": 0}
        _STATE[pid] = {"version": int(prev["version"]) + 1, "signature": signature, "at": time.time()}
        return dict(_STATE[pid])


def _current_local(pid: str) -> dict[str, Any]:
    with _LOCK:
        return dict(_STATE.get(pid) or {"version": 0, "signature": None, "at": None})


def bump(pid: str, signature: str | None = None) -> dict[str, Any]:
    """Record that the model for `pid` changed; increment its version. Shared via Redis when configured
    (atomic HINCRBY), fail-open to in-process. Returns the new state."""
    if _redis is not None:
        try:
            key = _KEY.format(pid=pid)
            now = time.time()
            with _redis.pipeline(transaction=True) as pipe:
                pipe.hincrby(key, "version", 1)
                pipe.hset(key, mapping={"signature": signature or "", "at": now})
                version, _ = pipe.execute()
            return {"version": int(version), "signature": signature, "at": now}
        except Exception:                        # noqa: BLE001 — Redis hiccup must not break publishing
            pass
    return _bump_local(pid, signature)


def current(pid: str) -> dict[str, Any]:
    """The current model version/signature for `pid` (version 0 if nothing published yet)."""
    if _redis is not None:
        try:
            h = _redis.hgetall(_KEY.format(pid=pid))
            if h:
                return {"version": int(h.get("version", 0)),
                        "signature": h.get("signature") or None,
                        "at": float(h["at"]) if h.get("at") else None}
            return {"version": 0, "signature": None, "at": None}
        except Exception:                        # noqa: BLE001 — fail-open to the in-process view
            pass
    return _current_local(pid)


def observe(pid: str, signature: str | None) -> dict[str, Any]:
    """Reconcile a freshly-computed signature with the registry: if it differs from what we last saw
    (e.g. another worker published and this worker just reloaded the index), bump; else leave as-is.
    Lets pull/push callers keep the version honest even without an explicit publish event."""
    cur = current(pid)
    if signature and signature != cur.get("signature"):
        return bump(pid, signature)
    return cur
