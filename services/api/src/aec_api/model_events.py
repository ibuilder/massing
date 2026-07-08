"""In-process model-change events — the tractable slice of live 2D propagation without an event bus.

The 2D drawings (plans / sections / elevations) render **on demand** from the live model, so "keep the
2D in sync with the model" reduces to "tell everyone the moment the model changed, so they regenerate."
This is an in-process, per-project monotonic version that is **bumped when a new properties index is
published** (the canonical 'the model changed' signal). Clients learn about it two ways:

* pull — ``GET /drawings/sync-status`` returns the current ``version`` + content ``signature``;
* push — ``GET /drawings/stream`` (SSE) emits the new version the instant it changes, so open drawing
  views refresh themselves without polling.

Single-process/worker scope by design (like the property ``_INDEX`` cache and the presence registry) —
no external broker. Multi-worker deployments already share the published index via object storage, and
each worker bumps its own version on the next ``_ensure_loaded`` reload; the SSE stream also re-emits on
a signature change, so a client still converges. A cross-worker broker would be the next step if needed.
"""
from __future__ import annotations

import threading
import time
from typing import Any

_LOCK = threading.Lock()
_STATE: dict[str, dict[str, Any]] = {}          # pid -> {version, signature, at}


def bump(pid: str, signature: str | None = None) -> dict[str, Any]:
    """Record that the model for `pid` changed; increment its version. Returns the new state."""
    with _LOCK:
        prev = _STATE.get(pid) or {"version": 0}
        _STATE[pid] = {"version": int(prev["version"]) + 1, "signature": signature, "at": time.time()}
        return dict(_STATE[pid])


def current(pid: str) -> dict[str, Any]:
    """The current model version/signature for `pid` (version 0 if nothing has been published yet)."""
    with _LOCK:
        return dict(_STATE.get(pid) or {"version": 0, "signature": None, "at": None})


def observe(pid: str, signature: str | None) -> dict[str, Any]:
    """Reconcile a freshly-computed signature with the registry: if it differs from what we last saw
    (e.g. another worker published and this worker just reloaded the index), bump; else leave as-is.
    Lets pull/push callers keep the version honest without a central broker."""
    cur = current(pid)
    if signature and signature != cur.get("signature"):
        return bump(pid, signature)
    return cur
