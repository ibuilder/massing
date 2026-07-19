"""E6 — recipe-log design-option BRANCHES: named model snapshots you can switch between.

The recipe log already *is* the undo stack (S4); this makes it branchable: snapshot the current
source IFC as a named option ("Scheme A — steel frame"), keep editing, snapshot again, then switch
the project between options — each switch is itself undoable (it goes through the same
edit-history push as any edit). The metrics-comparison module (`design_options.py`) compares
numbers; THIS module carries the actual model files.

Storage: `{pid}/options/{slug}.ifc` + an index at `{pid}/options/index.json` (name, slug, created
timestamp, element count, note). Deliberately file-level — an option is a whole-model branch, not a
per-element overlay (that's W9-3 layers).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import storage

_INDEX = "options/index.json"


def _key(pid: str, name: str) -> str:
    return f"{pid}/options/{name}"


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    if not s:
        raise ValueError("an option needs a name")
    return s[:60]


def _load_index(pid: str) -> list[dict]:
    key = _key(pid, "index.json")
    if not storage.exists(key):
        return []
    try:
        data = json.loads(storage.get(key))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001 — a corrupt index lists as empty, snapshots re-add entries
        return []


def _save_index(pid: str, entries: list[dict]) -> None:
    storage.put(_key(pid, "index.json"), json.dumps(entries).encode())


def _element_count(ifc_path: str) -> int | None:
    try:
        from aec_data.ifc_loader import open_model  # type: ignore
        return len(open_model(ifc_path).by_type("IfcElement"))
    except Exception:  # noqa: BLE001 — a count is nice-to-have, never blocks a snapshot
        return None


def snapshot(pid: str, source_ifc: str, name: str, note: str | None = None) -> dict[str, Any]:
    """Branch the current model: copy the source IFC into option storage under a named slug.
    Re-using a name overwrites that option (it's a branch head, not an archive — the edit history
    keeps the archaeology)."""
    slug = _slug(name)
    data = Path(source_ifc).read_bytes()
    storage.put(_key(pid, f"{slug}.ifc"), data)
    entries = [e for e in _load_index(pid) if e.get("slug") != slug]
    entry = {"slug": slug, "name": name.strip(), "note": note,
             "created_at": datetime.now(timezone.utc).isoformat(),
             "size_bytes": len(data), "elements": _element_count(source_ifc)}
    entries.append(entry)
    _save_index(pid, entries)
    return entry


def list_options(pid: str, source_ifc: str | None = None) -> dict[str, Any]:
    """The project's option branches. When the current source is given, options whose bytes match
    it exactly are flagged `current` (so the UI shows where you are)."""
    entries = _load_index(pid)
    cur = Path(source_ifc).read_bytes() if source_ifc and Path(source_ifc).exists() else None
    for e in entries:
        key = _key(pid, f"{e['slug']}.ifc")
        e["available"] = storage.exists(key)
        e["current"] = bool(cur) and e["available"] and storage.get(key) == cur
    return {"options": sorted(entries, key=lambda e: e["created_at"], reverse=True),
            "count": len(entries)}


def load_option_bytes(pid: str, slug: str) -> bytes:
    key = _key(pid, f"{_slug(slug)}.ifc")
    if not storage.exists(key):
        raise FileNotFoundError(f"option {slug!r} not found")
    return storage.get(key)


def delete_option(pid: str, slug: str) -> bool:
    s = _slug(slug)
    key = _key(pid, f"{s}.ifc")
    existed = storage.exists(key)
    if existed:
        storage.delete(key)
    _save_index(pid, [e for e in _load_index(pid) if e.get("slug") != s])
    return existed


def diff_option(pid: str, slug: str, source_ifc: str) -> dict[str, Any]:
    """What separates the current model from an option branch: added/removed element GUIDs (option
    → current) and the per-class count deltas. GUID-set level — geometry-identical elements that
    merely moved don't show (that's the versions.py fingerprint diff's job within a branch)."""
    import tempfile

    from aec_data.ifc_loader import open_model  # type: ignore

    with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
        f.write(load_option_bytes(pid, slug))
        opt_path = f.name
    try:
        cur = open_model(source_ifc)
        opt = open_model(opt_path)

        def _els(m) -> dict[str, str]:
            return {el.GlobalId: el.is_a() for el in m.by_type("IfcElement")
                    if not el.is_a("IfcElementType")}
        cur_els, opt_els = _els(cur), _els(opt)
        added = sorted(set(cur_els) - set(opt_els))
        removed = sorted(set(opt_els) - set(cur_els))
        classes: dict[str, dict[str, int]] = {}
        for cls in set(cur_els.values()) | set(opt_els.values()):
            a = sum(1 for v in cur_els.values() if v == cls)
            b = sum(1 for v in opt_els.values() if v == cls)
            if a != b:
                classes[cls] = {"current": a, "option": b, "delta": a - b}
        return {"option": _slug(slug), "added_in_current": added[:100], "added_count": len(added),
                "removed_in_current": removed[:100], "removed_count": len(removed),
                "class_deltas": classes,
                "identical": not added and not removed and not classes}
    finally:
        Path(opt_path).unlink(missing_ok=True)
