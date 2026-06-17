"""Live presence + shared viewpoints (real-time collaboration). In-memory per-process store:
each client heartbeats (POST presence) with an optional camera viewpoint; peers read the active
roster (GET presence). Active = heartbeat within TTL seconds.

Per-process (like metrics): with multiple uvicorn workers each sees its own slice — fine for dev
/ single-worker; back it with Redis (or sticky sessions) for a multi-worker deployment."""
from __future__ import annotations

import threading
import time
from typing import Any

_TTL = 45                      # seconds since last heartbeat before a user is considered gone
_lock = threading.Lock()
# project_id -> user -> {"ts": float, "viewpoint": dict | None}
_seen: dict[str, dict[str, dict[str, Any]]] = {}


def touch(project_id: str, user: str, viewpoint: dict[str, Any] | None = None) -> None:
    with _lock:
        proj = _seen.setdefault(project_id, {})
        entry = proj.setdefault(user, {})
        entry["ts"] = time.time()
        if viewpoint is not None:          # only update on an explicit share, not plain heartbeats
            entry["viewpoint"] = viewpoint


def active(project_id: str, exclude: str | None = None, ttl: int = _TTL) -> list[dict[str, Any]]:
    """Roster of users seen within `ttl` seconds, newest first; prunes the stale ones."""
    now = time.time()
    with _lock:
        proj = _seen.get(project_id, {})
        for u in [u for u, e in proj.items() if now - e["ts"] > ttl]:
            del proj[u]
        out = [{"user": u, "seconds_ago": round(now - e["ts"], 1),
                "viewpoint": e.get("viewpoint")}
               for u, e in proj.items() if u != exclude]
    out.sort(key=lambda r: r["seconds_ago"])
    return out
