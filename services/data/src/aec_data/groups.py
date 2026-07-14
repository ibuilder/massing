"""W10-3 · groups, assemblies & arrays — the organisational layer over placed elements.

Three IFC-native ways to compose elements, all GUID-stable:
  • **Group** (IfcGroup + IfcRelAssignsToGroup) — a non-geometric, non-hierarchical *set* of elements
    (a selection you can name, colour, schedule). Members keep their own containers.
  • **Assembly** (IfcElementAssembly + IfcRelAggregates) — a real *part-of* whole: a named element that
    aggregates its parts (a curtain-wall unit, a truss, a pre-cast panel). The assembly is spatially
    contained; its parts hang under it.
  • **Array** — parametric duplication: copy an element on a rectangular (nx × ny) grid at a fixed
    pitch, so a bay of columns / a run of fixtures is one action.

This builds directly on the W10-1 type system and the existing copy_element/placement machinery.
"""
from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.api


def _els(model: ifcopenshell.file, guids) -> list:
    """Resolve GUIDs → elements, silently skipping any that are missing."""
    out = []
    for g in guids or []:
        try:
            out.append(model.by_guid(g))
        except Exception:  # noqa: BLE001 — a stale/unknown GUID never aborts the batch
            pass
    return out


def create_group(model: ifcopenshell.file, name: str, guids) -> dict:
    """Author an IfcGroup named `name` and assign the given elements to it (a named set — think
    saved selection / system). Returns {guid, name, members}. Re-using a name adds to that group."""
    name = (name or "Group").strip() or "Group"
    els = _els(model, guids)
    grp = next((g for g in model.by_type("IfcGroup")
                if not g.is_a("IfcSystem") and (g.Name or "") == name), None)
    if grp is None:
        grp = ifcopenshell.api.run("group.add_group", model, name=name)
    if els:
        ifcopenshell.api.run("group.assign_group", model, group=grp, products=els)
    return {"guid": grp.GlobalId, "name": grp.Name, "members": _group_member_count(grp)}


def create_assembly(model: ifcopenshell.file, name: str, guids,
                    predefined: str | None = None) -> dict:
    """Author an IfcElementAssembly (a real part-of whole) that aggregates the given elements as its
    parts. The assembly is spatially contained in the first part's storey; parts are re-parented under
    it via IfcRelAggregates. Returns {guid, name, parts}."""
    import ifcopenshell.util.element as ue

    name = (name or "Assembly").strip() or "Assembly"
    parts = _els(model, guids)
    if not parts:
        raise ValueError("an assembly needs at least one part")
    asm = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcElementAssembly", name=name)
    if predefined and hasattr(asm, "PredefinedType"):
        try:
            asm.PredefinedType = predefined
        except Exception:  # noqa: BLE001 — invalid enum for the schema, skip
            pass
    # contain the assembly where its first part lives, so it sits in the spatial tree
    host = ue.get_container(parts[0])
    if host is not None:
        ifcopenshell.api.run("spatial.assign_container", model, products=[asm], relating_structure=host)
    # aggregate the parts under the assembly (this moves them out of direct spatial containment)
    ifcopenshell.api.run("aggregate.assign_object", model, products=parts, relating_object=asm)
    return {"guid": asm.GlobalId, "name": asm.Name, "parts": len(parts)}


def array_element(model: ifcopenshell.file, guid: str, nx: int = 2, ny: int = 1,
                  dx: float = 1.0, dy: float = 0.0, dz: float = 0.0) -> dict:
    """Rectangular parametric array: duplicate the element on an nx × ny grid at pitch (dx, dy) metres
    (dz per column for a raked/stacked array). The original is cell (0,0); every other cell is a
    GUID-stable copy. Returns {source, guids, count} (new copies only)."""
    from .edit import copy_element

    nx = max(1, int(nx))
    ny = max(1, int(ny))
    made: list[str] = []
    for i in range(nx):
        for j in range(ny):
            if i == 0 and j == 0:
                continue                                   # cell (0,0) is the original
            g = copy_element(model, guid, dx * i, dy * j, dz * i)
            _detach_inherited(model, model.by_guid(g))     # arrayed copies are independent occurrences
            made.append(g)
    return {"source": guid, "guids": made, "count": len(made)}


def _detach_inherited(model: ifcopenshell.file, el) -> None:
    """A deep element copy inherits the source's group/assembly assignments (copy_class copies the
    relationships). For an *array*, each copy should stand alone — strip those so arraying a grouped
    or assembled element doesn't silently swell the original group / double-aggregate the assembly."""
    for rel in list(getattr(el, "HasAssignments", None) or []):
        if rel.is_a("IfcRelAssignsToGroup"):
            ifcopenshell.api.run("group.unassign_group", model, group=rel.RelatingGroup, products=[el])
    for rel in list(getattr(el, "Decomposes", None) or []):
        if rel.is_a("IfcRelAggregates"):
            ifcopenshell.api.run("aggregate.unassign_object", model, products=[el])


def ungroup(model: ifcopenshell.file, guid: str) -> dict:
    """Dissolve an IfcGroup (removes the group + its assignment; members are untouched). Returns
    {removed: 1|0}."""
    grp = next((g for g in model.by_type("IfcGroup") if g.GlobalId == guid), None)
    if grp is None:
        return {"removed": 0}
    ifcopenshell.api.run("group.remove_group", model, group=grp)
    return {"removed": 1}


def _group_member_count(grp) -> int:
    return sum(len(rel.RelatedObjects) for rel in (getattr(grp, "IsGroupedBy", None) or []))


def list_groups(model: ifcopenshell.file) -> dict:
    """Every group and assembly in the model, with member counts — for a browser / selection sets.
    Groups and assemblies are listed separately (they mean different things)."""
    groups: list[dict] = []
    for g in model.by_type("IfcGroup"):
        if g.is_a("IfcSystem"):
            continue                                       # MEP systems have their own browser
        groups.append({"guid": g.GlobalId, "name": g.Name or g.is_a(),
                       "kind": "system" if g.is_a("IfcSystem") else "group",
                       "members": _group_member_count(g)})
    assemblies: list[dict] = []
    for a in model.by_type("IfcElementAssembly"):
        parts = sum(len(rel.RelatedObjects) for rel in (getattr(a, "IsDecomposedBy", None) or []))
        assemblies.append({"guid": a.GlobalId, "name": a.Name or "Assembly",
                           "predefined": getattr(a, "PredefinedType", None), "parts": parts})
    return {"groups": sorted(groups, key=lambda x: x["name"]),
            "assemblies": sorted(assemblies, key=lambda x: x["name"])}


def group_detail(model: ifcopenshell.file, guid: str) -> dict:
    """Inspector for one group or assembly: its members/parts as [{guid, name, ifc_class}]."""
    obj = next((g for g in model.by_type("IfcGroup") if g.GlobalId == guid), None)
    kind = "group"
    members: list[Any] = []
    if obj is not None:
        for rel in (getattr(obj, "IsGroupedBy", None) or []):
            members.extend(rel.RelatedObjects)
    else:
        obj = next((a for a in model.by_type("IfcElementAssembly") if a.GlobalId == guid), None)
        kind = "assembly"
        if obj is None:
            raise ValueError(f"group/assembly {guid!r} not found")
        for rel in (getattr(obj, "IsDecomposedBy", None) or []):
            members.extend(rel.RelatedObjects)
    return {
        "guid": guid, "kind": kind, "name": getattr(obj, "Name", None) or obj.is_a(),
        "member_count": len(members),
        "members": [{"guid": m.GlobalId, "name": getattr(m, "Name", None) or m.is_a(),
                     "ifc_class": m.is_a()} for m in members[:500]],
    }
