"""FAMILY-DEPTH ④ — shared parameters (R18).

A project-level parameter registry — named, typed properties that live in a declared pset and
apply to declared IFC classes — so the same "FireRating" or "AcousticClass" means one thing
across elements, schedules, and tags:

- **Registry** (`load`/`save`): a validated storage blob (`{pid}/shared_params.json`, no
  migration). Each definition: `name` (unique, ≤50), `pset` (default `Pset_Shared`), `ptype`
  (`text` | `number` | `bool`), `applies_to` (IFC classes, ≤20), optional `label`/`description`.
  Hard cap 100 definitions (stored-data amplification rule). Values are written through the
  normal edit recipes (`set_element_pset` / `set_props_by_guid`) — the registry defines meaning,
  the edit pipeline owns mutation (GUID-stable, versioned, undoable).
- **Schedules**: `schedule_columns(defs, ifc_class)` → the extra column specs the computed
  door/window/room schedules append (see aec_data.drawing_schedules), so a registered parameter
  IS a schedule column — and therefore reachable by SCHED-CALC formulas — with zero extra wiring.
"""
from __future__ import annotations

import json
import re
from typing import Any

from . import storage

MAX_PARAMS = 100
_PTYPES = ("text", "number", "bool")
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_ .-]{0,49}$")
_CLASS = re.compile(r"^Ifc[A-Za-z]{2,48}$")


def _key(pid: str) -> str:
    return f"{pid}/shared_params.json"


def validate(defs: list[dict]) -> list[dict[str, Any]]:
    if not isinstance(defs, list):
        raise ValueError("shared params must be a list of definitions")
    if len(defs) > MAX_PARAMS:
        raise ValueError(f"at most {MAX_PARAMS} shared parameters")
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, d in enumerate(defs):
        if not isinstance(d, dict):
            raise ValueError(f"definition {i} must be an object")
        name = str(d.get("name") or "").strip()
        if not _NAME.match(name):
            raise ValueError(f"definition {i}: name must be 1–50 chars, letter-first "
                             "(letters/digits/_ . - space)")
        if name.lower() in seen:
            raise ValueError(f"duplicate shared parameter {name!r}")
        seen.add(name.lower())
        ptype = str(d.get("ptype") or "text").lower()
        if ptype not in _PTYPES:
            raise ValueError(f"{name}: ptype must be one of {_PTYPES}")
        pset = str(d.get("pset") or "Pset_Shared").strip()[:60] or "Pset_Shared"
        classes = d.get("applies_to") or []
        if not isinstance(classes, list) or not classes or len(classes) > 20:
            raise ValueError(f"{name}: applies_to must list 1–20 IFC classes")
        for c in classes:
            if not _CLASS.match(str(c)):
                raise ValueError(f"{name}: {c!r} is not an IFC class name")
        clean.append({"name": name, "pset": pset, "ptype": ptype,
                      "applies_to": [str(c) for c in classes],
                      "label": str(d.get("label") or name)[:60],
                      "description": str(d.get("description") or "")[:300]})
    return clean


def load(pid: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(storage.get(_key(pid)).decode("utf-8"))
    except Exception:                                  # noqa: BLE001 — absent blob = empty registry
        return []
    return data if isinstance(data, list) else []


def save(pid: str, defs: list[dict]) -> list[dict[str, Any]]:
    clean = validate(defs)
    storage.put(_key(pid), json.dumps(clean).encode("utf-8"))
    return clean


def schedule_columns(defs: list[dict], ifc_class: str) -> list[dict[str, str]]:
    """The extra schedule-column specs for one schedule kind (IfcDoor/IfcWindow/IfcSpace):
    [{label, pset, prop}] in registry order."""
    return [{"label": d["label"], "pset": d["pset"], "prop": d["name"]}
            for d in defs if ifc_class in (d.get("applies_to") or [])]
