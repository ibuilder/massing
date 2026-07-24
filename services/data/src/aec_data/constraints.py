"""AUTH-CONSTRAINTS ① (R18) — the broken-host / illegal-placement checker.

IFC already persists the constraint graph natively — hosts via IfcRelVoidsElement/IfcRelFillsElement,
levels via IfcRelContainedInSpatialStructure — so this slice VALIDATES that graph instead of inventing
a parallel one: an insert whose host was deleted must surface, not dangle silently.

Checks (attribute + placement based, no OCC):
- ``orphan_opening``  (error)   an IfcOpeningElement whose voided host is gone
- ``orphan_fill``     (error)   a door/window whose FillsVoids chain is broken
- ``insert_outside_host`` (error) an opening placed beyond its host wall's length, or taller than it
- ``uncontained_element`` (warning) a building element on no storey (and in no assembly/host chain)
- ``level_mismatch``  (warning) an element contained on one storey but sitting at another's elevation
- ``unfilled_opening`` (info)   a bare hole with no fill — often intentional, surfaced not judged
- ``unhosted_insert``  (info)   a door/window with no host opening (curtain-wall inserts are legit)

Pure over an opened model; every issue carries {kind, severity, guid, name, detail} so the feed is
directly renderable and rule_library/BCF-composable downstream.
"""
from __future__ import annotations

from typing import Any

_CHECK_CLASSES = ("IfcWall", "IfcColumn", "IfcBeam", "IfcSlab", "IfcDoor", "IfcWindow", "IfcRoof",
                  "IfcStair", "IfcRamp", "IfcCovering")
_LEVEL_TOL = 1.0          # metres of grace either side of the storey band for level_mismatch


def _name(el) -> str:
    return getattr(el, "Name", None) or el.is_a()


def _issue(kind: str, severity: str, el, detail: str) -> dict[str, Any]:
    return {"kind": kind, "severity": severity, "guid": el.GlobalId, "name": _name(el),
            "ifc_class": el.is_a(), "detail": detail}


def _contained_storey(el):
    for rel in (getattr(el, "ContainedInStructure", None) or []):
        s = getattr(rel, "RelatingStructure", None)
        if s is not None and s.is_a("IfcBuildingStorey"):
            return s
    return None


def _rect_extrusion(el, scale: float) -> tuple[float, float, float] | None:
    """(length, thickness, height) in metres for a rectangle-profile extrusion, else None."""
    rep = getattr(el, "Representation", None)
    if rep is None:
        return None
    for r in rep.Representations:
        for it in (r.Items or []):
            if it.is_a("IfcExtrudedAreaSolid") and it.SweptArea.is_a("IfcRectangleProfileDef"):
                p = it.SweptArea
                return (float(p.XDim) * scale, float(p.YDim) * scale, float(it.Depth) * scale)
    return None


def check(model) -> dict[str, Any]:
    """Run every constraint check → {issues, counts, checked, note}. Placement-dependent checks skip
    elements they can't measure (counted in `checked`) rather than guessing."""
    import ifcopenshell.util.placement as uplace
    import ifcopenshell.util.unit as uunit
    import numpy as np

    scale = uunit.calculate_unit_scale(model)
    issues: list[dict[str, Any]] = []

    # --- host chain: openings and their fills ------------------------------------------------------
    openings = model.by_type("IfcOpeningElement")
    for op in openings:
        voids = getattr(op, "VoidsElements", None) or []
        host = getattr(voids[0], "RelatingBuildingElement", None) if voids else None
        if host is None:
            issues.append(_issue("orphan_opening", "error", op,
                                 "voids no existing element — its host was deleted"))
            continue
        if not (getattr(op, "HasFillings", None) or []):
            issues.append(_issue("unfilled_opening", "info", op,
                                 f"a bare hole in {_name(host)} with no door/window fill"))
        # illegal placement: the opening must sit within its host wall's extent
        dims = _rect_extrusion(host, scale)
        odims = _rect_extrusion(op, scale)
        if dims and odims and host.is_a("IfcWall"):
            try:
                hm = np.array(uplace.get_local_placement(host.ObjectPlacement), dtype=float)
                om = np.array(uplace.get_local_placement(op.ObjectPlacement), dtype=float)
                local = np.linalg.inv(hm) @ om                # opening origin in the wall's frame
                x = float(local[0, 3]) * scale                # metres along the wall axis
                z = float(local[2, 3]) * scale                # sill height in the wall's frame
                length, _, wall_h = dims
                o_w, _, o_h = odims
                if x + o_w / 2 < 0 or x - o_w / 2 > length:
                    issues.append(_issue(
                        "insert_outside_host", "error", op,
                        f"placed {x:.2f} m along a {length:.2f} m wall — outside its extent"))
                elif z + o_h > wall_h + 0.05:
                    issues.append(_issue(
                        "insert_outside_host", "error", op,
                        f"sill {z:.2f} m + height {o_h:.2f} m exceeds the {wall_h:.2f} m wall"))
            except (ValueError, TypeError, np.linalg.LinAlgError):
                pass                                          # unmeasurable placement — skip honestly

    for cls in ("IfcDoor", "IfcWindow"):
        for el in model.by_type(cls):
            fills = getattr(el, "FillsVoids", None) or []
            if not fills:
                issues.append(_issue("unhosted_insert", "info", el,
                                     "no host opening (fine for curtain-wall inserts)"))
            elif getattr(fills[0], "RelatingOpeningElement", None) is None:
                issues.append(_issue("orphan_fill", "error", el,
                                     "its host opening was deleted — the fill dangles"))

    # --- level containment + elevation sanity ------------------------------------------------------
    storeys = sorted(model.by_type("IfcBuildingStorey"),
                     key=lambda s: float(getattr(s, "Elevation", 0) or 0))
    bands: dict[str, tuple[float, float]] = {}
    for i, s in enumerate(storeys):
        lo = float(s.Elevation or 0) * scale
        hi = (float(storeys[i + 1].Elevation or 0) * scale) if i + 1 < len(storeys) else lo + 1e9
        bands[s.GlobalId] = (lo, hi)

    checked_level = 0
    for cls in _CHECK_CLASSES:
        for el in model.by_type(cls):
            st = _contained_storey(el)
            if st is None:
                hosted = bool(getattr(el, "FillsVoids", None))
                aggregated = bool(getattr(el, "Decomposes", None))
                if not hosted and not aggregated:
                    issues.append(_issue("uncontained_element", "warning", el,
                                         "on no storey (and not hosted or in an assembly)"))
                continue
            band = bands.get(st.GlobalId)
            if band is None:
                continue
            try:
                wm = np.array(uplace.get_local_placement(el.ObjectPlacement), dtype=float)
                z = float(wm[2, 3]) * scale
            except (ValueError, TypeError):
                continue
            checked_level += 1
            lo, hi = band
            if z < lo - _LEVEL_TOL or z >= hi + _LEVEL_TOL:
                issues.append(_issue(
                    "level_mismatch", "warning", el,
                    f"contained on {_name(st)} (elev {lo:.2f} m) but placed at z={z:.2f} m"))

    order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: (order.get(i["severity"], 3), i["kind"]))
    counts: dict[str, int] = {}
    for i in issues:
        counts[i["kind"]] = counts.get(i["kind"], 0) + 1
    return {
        "issues": issues, "issue_count": len(issues), "counts": counts,
        "errors": sum(1 for i in issues if i["severity"] == "error"),
        "warnings": sum(1 for i in issues if i["severity"] == "warning"),
        "checked": {"openings": len(openings), "elements_level_checked": checked_level,
                    "storeys": len(storeys)},
        "note": "IFC's own constraint graph (RelVoids/RelFills hosts, storey containment) validated: "
                "broken hosts and dangling fills are errors, missing containment and level/elevation "
                "disagreements are warnings, bare openings and unhosted inserts are informational.",
    }


def check_file(ifc_path: str) -> dict[str, Any]:
    from .ifc_loader import open_model
    return check(open_model(ifc_path))
