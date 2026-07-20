"""IFCPATCH-LIB (R15) — one-click IFC maintenance recipes.

The clean-the-model half of authoring: deterministic passes that remove dead data an IFC accumulates
over its life. v1 ships the two safe, unambiguous purges (nothing that touches element geometry or
GUIDs, so pins / RFIs / clashes keyed by GlobalId survive):

  * ``purge_orphan_psets``  — remove ``IfcPropertySet`` not attached to any element or type
    (no ``IfcRelDefinesByProperties`` points at it AND no ``IfcTypeObject.HasPropertySets`` lists it).
    The owned ``IfcProperty`` values go with it (``remove_deep2``).
  * ``purge_empty_groups``  — remove a plain ``IfcGroup`` with no members (no ``IfcRelAssignsToGroup``
    assigns anything to it). Restricted to the exact ``IfcGroup`` type — never systems / zones /
    building-systems, which are meaningful even when sparsely populated.

``scan(model)`` reports what each recipe WOULD remove (a dry run) so the UI can show the count before
anything is written. The recipes are registered in ``edit.RECIPES`` so they ride the existing
GUID-stable apply→republish pipeline.
"""
from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.util.element as _ue


def _orphan_psets(model: ifcopenshell.file) -> list:
    """IfcPropertySets attached to nothing (element rel OR type list)."""
    used: set[int] = set()
    for r in model.by_type("IfcRelDefinesByProperties"):
        pd = getattr(r, "RelatingPropertyDefinition", None)
        if pd is not None:
            used.add(pd.id())
    for t in model.by_type("IfcTypeObject"):
        for ps in (getattr(t, "HasPropertySets", None) or []):
            used.add(ps.id())
    return [p for p in model.by_type("IfcPropertySet") if p.id() not in used]


def _empty_groups(model: ifcopenshell.file) -> list:
    """Plain IfcGroups (exact type) with no assigned members."""
    grouped: set[int] = set()
    for r in model.by_type("IfcRelAssignsToGroup"):
        g = getattr(r, "RelatingGroup", None)
        if g is not None and (r.RelatedObjects or []):
            grouped.add(g.id())
    return [g for g in model.by_type("IfcGroup") if g.is_a() == "IfcGroup" and g.id() not in grouped]


def purge_orphan_psets(model: ifcopenshell.file) -> int:
    """Remove every orphaned IfcPropertySet (+ its owned properties). Returns the count removed."""
    n = 0
    for ps in _orphan_psets(model):
        _ue.remove_deep2(model, ps)
        n += 1
    return n


def purge_empty_groups(model: ifcopenshell.file) -> int:
    """Remove every empty plain IfcGroup (+ its owning IfcRelDeclares/aggregation stubs). Returns count."""
    n = 0
    for g in _empty_groups(model):
        _ue.remove_deep2(model, g)
        n += 1
    return n


# recipe name → (label, mutator) — registered into edit.RECIPES so the apply→republish path is free
RECIPES = {
    "purge_orphan_psets": ("Purge orphaned property sets", purge_orphan_psets),
    "purge_empty_groups": ("Purge empty groups", purge_empty_groups),
}


def extract_subset(model: ifcopenshell.file, keep_guids: set[str]) -> dict[str, Any]:
    """SUBSET-EXPORT — prune the model **in place** to just the physical elements whose ``GlobalId`` is
    in ``keep_guids`` (a discipline / selector slice you hand a consultant as a standalone IFC).

    Every ``IfcElement`` (wall/slab/column/door/MEP/…) NOT in the keep-set is removed with the
    ``root.remove_product`` API (which also detaches its spatial-containment / opening / property
    relationships and purges the owned geometry — ``remove_deep2`` alone can't, since a placed element
    has inverses). The **spatial skeleton** — ``IfcProject``, ``IfcSite``, ``IfcBuilding``,
    ``IfcBuildingStorey``, ``IfcSpace`` — and shared units / geometric contexts are left intact, so the
    pruned file is a valid IFC the kept elements are still correctly contained in, with GUIDs unchanged.
    Caller opens a throwaway copy of the source (never the live model) and writes the result. Returns
    ``{available, kept, removed}``."""
    import ifcopenshell.api.root  # local import — the api package is heavier than the util helpers

    keep = {g for g in keep_guids if g}
    elements = model.by_type("IfcElement")
    if not elements:
        return {"available": False, "kept": 0, "removed": 0,
                "message": "model has no IfcElement to subset"}
    removed = 0
    for e in list(elements):
        if getattr(e, "GlobalId", None) not in keep:
            ifcopenshell.api.root.remove_product(model, product=e)
            removed += 1
    return {"available": True, "kept": len(elements) - removed, "removed": removed}


def scan(model: ifcopenshell.file) -> dict[str, Any]:
    """Dry-run maintenance report — how many entities each recipe WOULD remove (no mutation)."""
    orphan_ps = _orphan_psets(model)
    empty_g = _empty_groups(model)
    recipes = [
        {"recipe": "purge_orphan_psets", "label": RECIPES["purge_orphan_psets"][0],
         "removable": len(orphan_ps),
         "sample": [p.Name for p in orphan_ps[:20] if getattr(p, "Name", None)]},
        {"recipe": "purge_empty_groups", "label": RECIPES["purge_empty_groups"][0],
         "removable": len(empty_g),
         "sample": [g.Name for g in empty_g[:20] if getattr(g, "Name", None)]},
    ]
    return {"total_entities": len(list(model)),
            "cleanable": sum(r["removable"] for r in recipes),
            "recipes": recipes}


def scan_file(ifc_path: str) -> dict[str, Any]:
    from .ifc_loader import open_model
    return scan(open_model(ifc_path))
