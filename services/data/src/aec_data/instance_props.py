"""FAMILY-DEPTH ② — instance-level parameter overrides, made first-class.

IFC already layers occurrence property sets over type property sets (an occurrence value shadows
the type's for every conforming consumer). What was missing is the *authoring* surface:

- `effective_properties(model, guid)` — the merged view a properties panel needs: every
  pset/property with its **effective value**, its **source** (`instance` | `type`), the shadowed
  `type_value` where an override is in play, and an `overridden` flag. Deterministic ordering.
- `reset_property_to_type(model, guid, pset, prop)` — remove the occurrence-level property so the
  type's value shows through again (the "reset to type" button). Removing the last property of an
  occurrence pset removes the now-empty pset + its relationship. Errors name what's missing;
  resetting a property that has no type backing is refused (that would silently DELETE data, not
  reset it — use the normal pset editor to remove instance-only properties deliberately).
"""
from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.util.element as ue

_SKIP_KEYS = ("id",)          # get_psets() bookkeeping, not a property


def _clean(psets: dict) -> dict[str, dict[str, Any]]:
    return {name: {k: v for k, v in (props or {}).items() if k not in _SKIP_KEYS}
            for name, props in (psets or {}).items()
            if isinstance(props, dict)}


def effective_properties(model: ifcopenshell.file, guid: str) -> dict[str, Any]:
    try:
        el = model.by_guid(guid)
    except RuntimeError:
        el = None
    if el is None:
        raise ValueError(f"element {guid} not found")
    typ = ue.get_type(el)
    type_psets = _clean(ue.get_psets(typ)) if typ is not None else {}
    inst_psets = _clean(ue.get_psets(el, should_inherit=False))
    out: dict[str, Any] = {"guid": guid, "type_guid": typ.GlobalId if typ is not None else None,
                           "type_name": getattr(typ, "Name", None) if typ is not None else None,
                           "psets": {}}
    override_count = 0
    for pset in sorted(set(type_psets) | set(inst_psets)):
        rows: dict[str, Any] = {}
        t_props = type_psets.get(pset, {})
        i_props = inst_psets.get(pset, {})
        for prop in sorted(set(t_props) | set(i_props)):
            if prop in i_props:
                overridden = prop in t_props and t_props[prop] != i_props[prop]
                rows[prop] = {"value": i_props[prop], "source": "instance",
                              "overridden": overridden,
                              "type_value": t_props.get(prop)}
                if overridden:
                    override_count += 1
            else:
                rows[prop] = {"value": t_props[prop], "source": "type",
                              "overridden": False, "type_value": t_props[prop]}
        out["psets"][pset] = rows
    out["override_count"] = override_count
    return out


def _occurrence_pset(el, pset_name: str):
    for rel in getattr(el, "IsDefinedBy", []) or []:
        if rel.is_a("IfcRelDefinesByProperties"):
            ps = rel.RelatingPropertyDefinition
            if ps is not None and ps.is_a("IfcPropertySet") and ps.Name == pset_name:
                return rel, ps
    return None, None


def reset_property_to_type(model: ifcopenshell.file, guid: str, pset: str, prop: str) -> dict[str, Any]:
    try:
        el = model.by_guid(guid)
    except RuntimeError:
        el = None
    if el is None:
        raise ValueError(f"element {guid} not found")
    typ = ue.get_type(el)
    type_props = _clean(ue.get_psets(typ)).get(pset, {}) if typ is not None else {}
    if prop not in type_props:
        raise ValueError(f"{pset}.{prop} has no type-level value to reset to — removing it would "
                         "delete data, not reset it")
    rel, ps = _occurrence_pset(el, pset)
    if ps is None:
        raise ValueError(f"element carries no occurrence pset {pset!r} — nothing to reset")
    keep = [p for p in (ps.HasProperties or []) if getattr(p, "Name", None) != prop]
    if len(keep) == len(ps.HasProperties or []):
        raise ValueError(f"no occurrence-level {pset}.{prop} on this element — already from type")
    removed = [p for p in (ps.HasProperties or []) if getattr(p, "Name", None) == prop]
    if keep:
        ps.HasProperties = keep
    else:
        # last property gone → drop the empty pset and its defining relationship entirely
        model.remove(rel)
        model.remove(ps)
    for p in removed:
        model.remove(p)
    return {"guid": guid, "pset": pset, "prop": prop, "now": type_props[prop], "source": "type"}
