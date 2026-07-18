"""S4 — per-project **edit-history** for undo/redo of authoring edits.

Every `/edit` writes a new `source_ifc` file (`<base>_<stamp>.ifc`) and leaves the prior versions on disk,
so undo is simply *restoring a prior file path* + republishing — no geometry to reverse. The stack is a
sidecar in object storage (`{pid}/edit_history.json`), so there's no schema change. Bounded so it can't grow
without limit. The stored paths are ones the server itself wrote (from `Project.source_ifc`), never user
input; the caller still verifies the restored path exists and stays inside the project's IFC directory.
"""
from __future__ import annotations

import json

from . import pid_lock, storage

_MAX = 50


def _locked(fn):
    """Serialize load→mutate→save per project (DOC-RACE) — same rationale as docmanager._locked."""
    import functools

    @functools.wraps(fn)
    def wrap(pid, *a, **k):
        with pid_lock.mutating(pid):
            return fn(pid, *a, **k)
    return wrap


def _key(pid: str) -> str:
    return f"{storage.safe_seg(pid)}/edit_history.json"


def _load(pid: str) -> dict:
    try:
        d = json.loads(storage.get(_key(pid)).decode("utf-8"))
        return {"undo": list(d.get("undo") or []), "redo": list(d.get("redo") or [])}
    except Exception:  # noqa: BLE001 — no history yet / unreadable → empty
        return {"undo": [], "redo": []}


def _save(pid: str, d: dict) -> None:
    storage.put(_key(pid), json.dumps(d).encode("utf-8"))


@_locked
def push(pid: str, prev_path: str) -> None:
    """Record the pre-edit source path before a new edit advances it. A fresh edit invalidates redo."""
    if not prev_path:
        return
    d = _load(pid)
    d["undo"] = (d["undo"] + [prev_path])[-_MAX:]
    d["redo"] = []
    _save(pid, d)


@_locked
def undo(pid: str, current_path: str) -> str | None:
    """Pop the last pre-edit path (the version to restore); push `current_path` onto redo. None if empty."""
    d = _load(pid)
    if not d["undo"]:
        return None
    prev = d["undo"].pop()
    if current_path:
        d["redo"] = (d["redo"] + [current_path])[-_MAX:]
    _save(pid, d)
    return prev


@_locked
def redo(pid: str, current_path: str) -> str | None:
    """Pop the last undone path (re-apply); push `current_path` onto undo. None if empty."""
    d = _load(pid)
    if not d["redo"]:
        return None
    nxt = d["redo"].pop()
    if current_path:
        d["undo"] = (d["undo"] + [current_path])[-_MAX:]
    _save(pid, d)
    return nxt


def state(pid: str) -> dict:
    d = _load(pid)
    return {"can_undo": bool(d["undo"]), "can_redo": bool(d["redo"]),
            "undo_depth": len(d["undo"]), "redo_depth": len(d["redo"])}
