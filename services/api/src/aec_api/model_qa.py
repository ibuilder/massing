"""IFC model **integrity / hygiene** checks — the "common modelling mistakes" layer, complementary to
the LOIN/IDS *data-quality* checks in openbim_quality.py. Catches the defects a coordinator finds by
eye: duplicate GlobalIds, overlapping duplicate elements (same class stacked at one spot), physical
elements not contained in any storey (orphaned), IfcSpace with no space boundaries (unenclosed), and
blank element names. Pure over an opened ifcopenshell model; every check is guarded so a malformed
model degrades to "couldn't check" instead of 500ing."""
from __future__ import annotations

from typing import Any


def _loc(elem) -> tuple[float, float, float] | None:
    """World-ish placement origin (x, y, z) rounded — for spotting stacked duplicates."""
    try:
        import ifcopenshell.util.placement as placement
        if not getattr(elem, "ObjectPlacement", None):
            return None
        m = placement.get_local_placement(elem.ObjectPlacement)
        return (round(float(m[0][3]), 3), round(float(m[1][3]), 3), round(float(m[2][3]), 3))
    except Exception:       # noqa: BLE001 — bad placement: skip this element, don't crash the scan
        return None


def model_qa(model) -> dict[str, Any]:
    """Run the integrity checks and return per-check counts + a sample of offenders, plus a total."""
    checks: dict[str, Any] = {}

    # 1. duplicate GlobalIds — a data-integrity red flag (copy without regenerating the GUID)
    counts: dict[str, int] = {}
    for e in model.by_type("IfcRoot"):
        g = getattr(e, "GlobalId", None)
        if g:
            counts[g] = counts.get(g, 0) + 1
    dup = [g for g, n in counts.items() if n > 1]
    checks["duplicate_guids"] = {"count": len(dup), "sample": dup[:20]}

    elements = model.by_type("IfcElement")

    # 2. orphaned elements — physical elements not placed in any spatial structure (and not nested in a
    #    parent, and not an opening-fill like a door/window). "Wrong/no level" from the Revit-mistakes set.
    contained: set[int] = set()
    for rel in model.by_type("IfcRelContainedInSpatialStructure"):
        for e in (rel.RelatedElements or []):
            contained.add(e.id())
    nested: set[int] = set()
    for rel in (*model.by_type("IfcRelAggregates"), *model.by_type("IfcRelNests")):
        for e in (rel.RelatedObjects or []):
            nested.add(e.id())
    fills: set[int] = set()
    for rel in model.by_type("IfcRelFillsElement"):
        if getattr(rel, "RelatedBuildingElement", None):
            fills.add(rel.RelatedBuildingElement.id())
    orphans = [e for e in elements if e.id() not in contained and e.id() not in nested and e.id() not in fills]
    checks["orphaned_elements"] = {"count": len(orphans),
                                   "sample": [{"class": e.is_a(), "name": e.Name, "guid": e.GlobalId} for e in orphans[:20]]}

    # 3. overlapping duplicates — same class stacked at the identical placement origin
    buckets: dict[tuple, list] = {}
    for e in elements:
        loc = _loc(e)
        if loc is not None:
            buckets.setdefault((e.is_a(), loc), []).append(e)
    groups = [{"class": k[0], "location": list(k[1]), "count": len(v)} for k, v in buckets.items() if len(v) > 1]
    checks["overlapping_duplicates"] = {"count": sum(g["count"] - 1 for g in groups), "groups": groups[:20]}

    # 4. unenclosed spaces — an IfcSpace with no space-boundary relationships ("Room is not enclosed")
    bounded: set[int] = set()
    for rel in model.by_type("IfcRelSpaceBoundary"):
        sp = getattr(rel, "RelatingSpace", None)
        if sp:
            bounded.add(sp.id())
    spaces = model.by_type("IfcSpace")
    unenclosed = [s for s in spaces if s.id() not in bounded]
    checks["unenclosed_spaces"] = {"count": len(unenclosed), "total_spaces": len(spaces),
                                   "sample": [{"name": s.Name, "guid": s.GlobalId} for s in unenclosed[:20]]}

    # 5. blank names — elements with no Name (poor naming discipline)
    blank = [e for e in elements if not (getattr(e, "Name", None) or "").strip()]
    checks["blank_names"] = {"count": len(blank), "of_elements": len(elements),
                             "sample": [{"class": e.is_a(), "guid": e.GlobalId} for e in blank[:20]]}

    # 6. wrong storey — an element assigned to level A but placed at level B's elevation (the classic
    #    "wrong level" Revit mistake). Flag only when the element sits clearly closer to another storey.
    try:
        storeys = [(s, float(s.Elevation)) for s in model.by_type("IfcBuildingStorey")
                   if getattr(s, "Elevation", None) is not None]
        elev_by_id = {s.id(): ev for s, ev in storeys}
        assigned: dict[int, int] = {}                    # element id -> storey id
        for rel in model.by_type("IfcRelContainedInSpatialStructure"):
            st = getattr(rel, "RelatingStructure", None)
            if st is not None and st.is_a("IfcBuildingStorey") and st.id() in elev_by_id:
                for e in (rel.RelatedElements or []):
                    assigned[e.id()] = st.id()
        wrong = []
        margin = 1.0                                     # metres of clearance before we call it wrong
        for e in elements:
            sid = assigned.get(e.id())
            loc = _loc(e)
            if sid is None or loc is None or len(storeys) < 2:
                continue
            z = loc[2]
            a_elev = elev_by_id[sid]
            nearest_s, nearest_elev = min(storeys, key=lambda se: abs(z - se[1]))
            if nearest_s.id() != sid and (abs(z - a_elev) - abs(z - nearest_elev)) > margin:
                wrong.append({"class": e.is_a(), "name": e.Name, "guid": e.GlobalId,
                              "assigned_elev": round(a_elev, 2), "placed_z": round(z, 2),
                              "nearest_storey": nearest_s.Name})
        checks["wrong_storey"] = {"count": len(wrong), "sample": wrong[:20]}
    except Exception:            # noqa: BLE001 — malformed storeys: skip this check, don't crash the scan
        checks["wrong_storey"] = {"count": 0, "sample": [], "skipped": True}

    total = sum(checks[k]["count"] for k in checks)
    return {"element_count": len(elements), "total_issues": total, "clean": total == 0, "checks": checks,
            "note": "Model integrity (complementary to LOIN/IDS data checks): duplicate GUIDs, orphaned "
                    "elements, overlapping duplicates, unenclosed spaces, blank names, wrong-storey placement."}
