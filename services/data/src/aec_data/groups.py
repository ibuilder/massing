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
    cells: list[tuple[str, int, int]] = [(guid, 0, 0)]
    for i in range(nx):
        for j in range(ny):
            if i == 0 and j == 0:
                continue                                   # cell (0,0) is the original
            g = copy_element(model, guid, dx * i, dy * j, dz * i)
            _detach_inherited(model, model.by_guid(g))     # arrayed copies are independent occurrences
            made.append(g)
            cells.append((g, i, j))

    # R38-ARRAY-LIVE: persist the DEFINITION, not just the copies. Until this existed the array was a
    # one-shot — it produced independent elements and stored nothing, so there was nothing to re-edit
    # and changing a count meant deleting copies by hand. The group carries nx/ny/pitch, each member
    # carries its cell, and `set_array_params` reconciles the two.
    #
    # Note the ORDER: `_detach_inherited` above strips the copies' inherited group assignments so that
    # arraying a grouped element does not swell the SOURCE's group. The array group is assigned after
    # that, deliberately — it is a new membership, not a survival of the old one.
    grp = ifcopenshell.api.run("group.add_group", model,
                               name=f"{ARRAY_GROUP_PREFIX} {model.by_guid(guid).is_a()} {guid[:6]}")
    for g, i, j in cells:
        el = model.by_guid(g)
        _write_pset(model, el, ARRAY_MEMBER_PSET, {"i": i, "j": j})
        ifcopenshell.api.run("group.assign_group", model, group=grp, products=[el])
    _write_pset(model, grp, ARRAY_PSET,
                {"source": guid, "nx": nx, "ny": ny, "dx": dx, "dy": dy, "dz": dz})
    return {"source": guid, "guids": made, "count": len(made),
            "group": grp.GlobalId, "nx": nx, "ny": ny}


#: The array definition lives on the IfcGroup; each member carries its own cell index. Both are
#: ordinary property sets, so the array survives a round-trip through any IFC tool rather than
#: living in a sidecar this application would be the only reader of.
ARRAY_PSET = "Pset_MassingArray"
ARRAY_MEMBER_PSET = "Pset_MassingArrayMember"
ARRAY_GROUP_PREFIX = "Array"

#: How far (metres) a member may sit from its cell before it counts as MOVED. Generous on purpose:
#: the question is "did a person put this somewhere else", not "is the float exact".
ARRAY_MOVED_TOL = 1e-3


def _pset_of(el, name: str) -> dict:
    import ifcopenshell.util.element as ue
    return (ue.get_psets(el) or {}).get(name, {}) or {}


def _write_pset(model, el, name: str, props: dict) -> None:
    import ifcopenshell.util.element as ue
    existing = (ue.get_psets(el, psets_only=True) or {}).get(name)
    ps = (model.by_id(existing["id"]) if existing and existing.get("id")
          else ifcopenshell.api.run("pset.add_pset", model, product=el, name=name))
    ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties=props)


def _origin_of(el) -> tuple[float, float, float]:
    """World translation of an element's placement, as (x, y, z)."""
    import ifcopenshell.util.placement as up
    mtx = up.get_local_placement(el.ObjectPlacement)
    return (float(mtx[0][3]), float(mtx[1][3]), float(mtx[2][3]))


def _array_group(model: ifcopenshell.file, guid: str):
    """The array group a GUID belongs to (as source or member), or None."""
    try:
        el = model.by_guid(guid)
    except Exception:  # noqa: BLE001
        return None
    for rel in list(getattr(el, "HasAssignments", None) or []):
        if rel.is_a("IfcRelAssignsToGroup"):
            grp = rel.RelatingGroup
            if _pset_of(grp, ARRAY_PSET):
                return grp
    return None


def array_params(model: ifcopenshell.file, guid: str) -> dict[str, Any]:
    """The live array definition covering `guid`, or `{"array": None}` when it is not in one.

    Reported rather than inferred: an element that merely *looks* arrayed (three walls in a row
    somebody drew by hand) has no definition, and guessing one would let a later count change
    delete elements nobody arrayed.
    """
    grp = _array_group(model, guid)
    if grp is None:
        return {"array": None,
                "note": "this element is not part of a stored array; "
                        "arrays created before R38-ARRAY-LIVE stored no definition"}
    p = _pset_of(grp, ARRAY_PSET)
    members = []
    for rel in (grp.IsGroupedBy or []):
        for m in (rel.RelatedObjects or []):
            mp = _pset_of(m, ARRAY_MEMBER_PSET)
            members.append({"guid": m.GlobalId, "i": int(mp.get("i", 0)), "j": int(mp.get("j", 0)),
                            "is_source": m.GlobalId == p.get("source")})
    members.sort(key=lambda r: (r["i"], r["j"]))
    return {"array": {"group": grp.GlobalId, "name": grp.Name, "source": p.get("source"),
                      "nx": int(p.get("nx", 1)), "ny": int(p.get("ny", 1)),
                      "dx": float(p.get("dx", 0.0)), "dy": float(p.get("dy", 0.0)),
                      "dz": float(p.get("dz", 0.0)), "members": members,
                      "member_count": len(members)}}


def _expected_origin(base: tuple[float, float, float], i: int, j: int,
                     dx: float, dy: float, dz: float) -> tuple[float, float, float]:
    return (base[0] + dx * i, base[1] + dy * j, base[2] + dz * i)


def _moved(el, base, i, j, dx, dy, dz) -> float:
    """Distance between where a member IS and where its cell says it should be."""
    ex, ey, ez = _expected_origin(base, i, j, dx, dy, dz)
    ax, ay, az = _origin_of(el)
    return max(abs(ax - ex), abs(ay - ey), abs(az - ez))


def set_array_params(model: ifcopenshell.file, guid: str, nx: int | None = None,
                     ny: int | None = None, dx: float | None = None, dy: float | None = None,
                     dz: float | None = None, force: bool = False) -> dict[str, Any]:
    """R38-ARRAY-LIVE — change a placed array's count or pitch, adding and removing members to match.

    Omitted parameters keep their stored value, so a caller can change only the count.

    **Shrinking an array DELETES elements, and that is the whole risk of this recipe.** A member that
    has been moved away from its cell is no longer a generated copy — somebody authored it — and
    deleting it destroys work that cannot be recovered from the definition. So a member whose actual
    placement differs from its cell by more than `ARRAY_MOVED_TOL` is **refused**: nothing is deleted,
    the offending members are named with their offsets, and the caller can pass `force=True` to say
    "yes, delete them anyway". The default is the safe one because the dangerous default here is the
    plausible one — an array editor that silently drops edited members looks like it is working.

    Re-pitching has the same hazard in a quieter form: moving a member that a person repositioned
    would silently discard their placement. Moved members are therefore left where they are and
    reported in `kept_moved`, rather than being snapped back to the grid.
    """
    info = array_params(model, guid)
    if not info["array"]:
        return {"status": "not_an_array", "changed": False, **info}
    a = info["array"]
    grp = model.by_guid(a["group"])
    src_guid = a["source"]
    try:
        src = model.by_guid(src_guid)
    except Exception:  # noqa: BLE001
        return {"status": "source_missing", "changed": False, "source": src_guid,
                "note": "the array's source element is gone; the definition cannot be re-evaluated "
                        "without it. Nothing was changed."}

    nx = max(1, int(a["nx"] if nx is None else nx))
    ny = max(1, int(a["ny"] if ny is None else ny))
    dx = float(a["dx"] if dx is None else dx)
    dy = float(a["dy"] if dy is None else dy)
    dz = float(a["dz"] if dz is None else dz)

    base = _origin_of(src)
    by_cell = {(m["i"], m["j"]): m for m in a["members"]}
    wanted = {(i, j) for i in range(nx) for j in range(ny)}

    # --- members that fall outside the new extent are deletion candidates ---------------------------
    doomed = [m for (i, j), m in by_cell.items() if (i, j) not in wanted and not m["is_source"]]
    authored = []
    for m in doomed:
        try:
            el = model.by_guid(m["guid"])
        except Exception:  # noqa: BLE001 — already gone; nothing to protect
            continue
        off = _moved(el, base, m["i"], m["j"], a["dx"], a["dy"], a["dz"])
        if off > ARRAY_MOVED_TOL:
            authored.append({**m, "offset_m": round(off, 4)})
    if authored and not force:
        return {"status": "would_delete_authored", "changed": False,
                "authored_members": authored, "would_delete": len(doomed),
                "note": (f"{len(authored)} of {len(doomed)} member(s) due for deletion have been MOVED "
                         "from their cell, so they are authored elements rather than generated copies. "
                         "Nothing was deleted. Re-send with force=true to delete them anyway — this is "
                         "refused by default because an array editor that silently drops edited "
                         "members looks exactly like one that is working.")}

    from .edit import copy_element, delete_element

    removed = [m["guid"] for m in doomed]
    for g in removed:
        delete_element(model, g)

    # --- fill the cells the new extent adds ---------------------------------------------------------
    added: list[dict] = []
    for i in range(nx):
        for j in range(ny):
            if (i, j) in by_cell or (i == 0 and j == 0):
                continue
            ox, oy, oz = _expected_origin(base, i, j, dx, dy, dz)
            g = copy_element(model, src_guid, ox - base[0], oy - base[1], oz - base[2])
            el = model.by_guid(g)
            _detach_inherited(model, el)
            _write_pset(model, el, ARRAY_MEMBER_PSET, {"i": i, "j": j})
            ifcopenshell.api.run("group.assign_group", model, group=grp, products=[el])
            added.append({"guid": g, "i": i, "j": j})

    # --- members a person repositioned stay put, and are reported ------------------------------------
    # --- a pitch change MOVES the members that are still on the grid ---------------------------------
    #
    # This used only to *detect* off-grid members and report them; it never repositioned anything. So
    # changing dx/dy/dz relaid only the cells the change happened to ADD, while every existing member
    # stayed at the old spacing — a silently mixed-pitch array that looks authored rather than broken.
    #
    # It compounded on the next call. `_moved` measures against the CURRENT params, so once the pset
    # said "new pitch" every un-moved member read as displaced, the authored-member guard saw them all
    # as hand-edited, and a subsequent shrink was refused with a message about protecting edits that
    # were never made. A change that half-applies is worse than one that refuses: it leaves the model
    # in a state no operation the user performed could have produced.
    #
    # The distinction the original code was reaching for still holds, and is now the thing that
    # decides: a member sitting where the OLD pitch put it is a generated copy and follows the array;
    # a member somewhere else was moved by hand and is left alone, reported, never snapped back.
    kept_moved = []
    relaid = []
    if (dx, dy, dz) != (a["dx"], a["dy"], a["dz"]):
        from .edit import move_element

        for (i, j), m in by_cell.items():
            if (i, j) not in wanted or m["is_source"]:
                continue
            try:
                el = model.by_guid(m["guid"])
            except Exception:  # noqa: BLE001
                continue
            if _moved(el, base, i, j, a["dx"], a["dy"], a["dz"]) > ARRAY_MOVED_TOL:
                kept_moved.append({**m, "note": "repositioned by hand; left where it is"})
                continue
            # On its old cell → a generated copy. Move it by the delta between old and new cell.
            ox, oy, oz = _expected_origin(base, i, j, a["dx"], a["dy"], a["dz"])
            nx_, ny_, nz_ = _expected_origin(base, i, j, dx, dy, dz)
            if max(abs(nx_ - ox), abs(ny_ - oy), abs(nz_ - oz)) > ARRAY_MOVED_TOL:
                move_element(model, m["guid"], nx_ - ox, ny_ - oy, nz_ - oz)
                relaid.append({**m, "note": "moved to the new pitch"})

    _write_pset(model, grp, ARRAY_PSET,
                {"source": src_guid, "nx": nx, "ny": ny, "dx": dx, "dy": dy, "dz": dz})
    return {"status": "ok", "changed": bool(added or removed or relaid),
            "group": a["group"], "source": src_guid,
            "nx": nx, "ny": ny, "dx": dx, "dy": dy, "dz": dz,
            "added": added, "removed": removed, "kept_moved": kept_moved,
            "forced": bool(force and authored),
            "note": ("members repositioned by hand were left in place, not snapped back to the grid"
                     if kept_moved else "")}


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
        pset = _pset_of(g, ARRAY_PSET)
        row = {"guid": g.GlobalId, "name": g.Name or g.is_a(),
               "kind": "system" if g.is_a("IfcSystem") else "group",
               "members": _group_member_count(g)}
        if pset:
            row["array"] = {"source": pset.get("source"),
                            "nx": int(pset.get("nx", 1)), "ny": int(pset.get("ny", 1)),
                            "dx": float(pset.get("dx", 0.0)), "dy": float(pset.get("dy", 0.0)),
                            "dz": float(pset.get("dz", 0.0))}
        groups.append(row)
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
