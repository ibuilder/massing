"""COLLAB-1 · real-time multiplayer co-editing — the awareness layer.

Browser-based modeling means two people can have the same project open. This gives each of them a live
picture of the other: who else is here (reusing `presence.py`), and — the piece the viewer lacked — a
signal that **the model itself changed** so a second client reloads the geometry after the first
publishes an edit, instead of silently drifting out of date.

A project's *model signature* changes on every authoring publish (`/edit` rewrites `source_ifc` to a new
stamped file and appends a `ModelVersion`). The collab snapshot bundles that signature with the presence
roster; the SSE stream re-emits it whenever either the model or the roster changes. In-model comments
already exist as GUID-anchored `Topic`/`Comment` rows — this doesn't rebuild them, it makes the session
around them live.
"""
from __future__ import annotations

from typing import Any


def model_signature(db, pid: str) -> dict[str, Any] | None:
    """The current model version marker for a project — changes on every authoring publish. None if the
    project is unknown. `source` (the stamped IFC path) flips per edit; `version`/`element_count` come
    from the latest `ModelVersion` snapshot."""
    from .models import ModelVersion, Project

    p = db.get(Project, pid)
    if p is None:
        return None
    latest = (db.query(ModelVersion)
              .filter(ModelVersion.project_id == pid)
              .order_by(ModelVersion.version.desc())
              .first())
    return {
        "source": p.source_ifc,
        "version": latest.version if latest else 0,
        "element_count": latest.element_count if latest else 0,
        "has_model": bool(p.source_ifc),
    }


def snapshot(db, pid: str, user: str) -> dict[str, Any] | None:
    """The live collaboration picture for a project: the model signature + the roster of other users
    present (heartbeat within the presence TTL). None if the project is unknown."""
    from . import presence

    sig = model_signature(db, pid)
    if sig is None:
        return None
    editors = presence.active(pid, exclude=user)
    return {"model": sig, "editors": editors, "editor_count": len(editors)}


def stream_signature(snap: dict[str, Any]) -> tuple:
    """A hashable signature of a collab snapshot — changes when the model version OR the set of present
    users (and where each is looking) changes, so the SSE stream re-emits on either. Order-independent
    over editors."""
    m = snap["model"]
    editors = tuple(sorted((e.get("user"), str(e.get("viewpoint"))) for e in snap["editors"]))
    return (m["source"], m["version"], editors)
