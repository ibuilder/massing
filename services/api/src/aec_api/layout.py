"""Model → field layout (Wave 8 ②) — export the setout the field robots and total stations consume.

The 2026 field-robotics wave (Dusty FieldPrinter · Hilti Jaibot/PLT · Trimble/Leica robotic total
stations) reads two open primitives from the model:
  • a **PENZD / PNEZD points CSV** (Point-№, Easting, Northing, Z, Description) — the near-universal
    interchange for total stations and marking robots, and
  • **layered DXF** linework — for the floor printers.
This derives both from the IFC, in **real-world coordinates** (the IfcMapConversion is applied, so the
points land on the surveyor's grid, not the model's local origin), with the **IFC GlobalId carried in the
Description** so the round-trip stays anchored. It then closes the loop: import the total station's
as-installed shots, match by Point-№ / GlobalId, and compute deviation for verification.

Placement-based extraction (no meshing): the object placement of columns, footings, openings and walls
gives a reliable setout point; grid intersections are parsed from `IfcGridAxis` polylines (best-effort,
degrades to none). Pure functions over an `ifcopenshell` model + `ezdxf` (MIT); no vendor SDK.
"""
from __future__ import annotations

import csv
import io
import math
import re
from typing import Any

from aec_data.cells import cell as _cell

# Element classes whose object-placement is a useful field setout point, with a short code for the
# Description (surveyors read the code to know what they're staking).
LAYOUT_CLASSES: dict[str, str] = {
    "IfcColumn": "COL", "IfcFooting": "FTG", "IfcPile": "PILE",
    "IfcOpeningElement": "OPEN", "IfcWallStandardCase": "WALL", "IfcWall": "WALL",
    "IfcMember": "MBR", "IfcDiscreteAccessory": "ANCH", "IfcMechanicalFastener": "ANCH",
}
_CSV_ORDERS = {"PENZD": ("p", "e", "n", "z", "d"), "PNEZD": ("p", "n", "e", "z", "d")}


def _map_fn(model):
    """Return f(x,y,z)->(E,N,H) applying the IfcMapConversion (offset + rotation + scale). Identity when
    the model isn't georeferenced — the export then carries local coordinates (still internally consistent)."""
    from . import georef
    try:                                  # IfcMapConversion is IFC4+; older schemas raise on by_type
        mc = (georef.georeferencing(model) or {}).get("map_conversion")
    except Exception:
        mc = None
    if not mc:
        return lambda x, y, z: (x, y, z)
    e0 = mc.get("eastings") or 0.0
    n0 = mc.get("northings") or 0.0
    h0 = mc.get("orthogonal_height") or 0.0
    ab = mc.get("x_axis_abscissa"); ordn = mc.get("x_axis_ordinate")
    s = mc.get("scale") or 1.0
    if ab is None or ordn is None or not (ab or ordn):
        ab, ordn = 1.0, 0.0
    norm = math.hypot(ab, ordn) or 1.0
    cos, sin = ab / norm, ordn / norm

    def to_map(x, y, z):
        return (e0 + s * (cos * x - sin * y), n0 + s * (sin * x + cos * y), h0 + s * z)
    return to_map


def _placement_xyz(elem):
    """World translation of an element's ObjectPlacement (metres, model space)."""
    try:
        import ifcopenshell.util.placement as up
        m = up.get_local_placement(elem.ObjectPlacement)
        return float(m[0][3]), float(m[1][3]), float(m[2][3])
    except Exception:
        return None


def _grid_points(model, to_map) -> list[dict]:
    """Best-effort grid intersections from IfcGridAxis polylines (U × V). Never raises."""
    pts: list[dict] = []
    try:
        import ifcopenshell.util.placement as up
    except Exception:
        return pts

    def _axis_line(ax):
        crv = getattr(ax, "AxisCurve", None)
        coords = getattr(crv, "Points", None) if crv is not None else None
        if not coords or len(coords) < 2:
            return None
        a = coords[0].Coordinates
        b = coords[-1].Coordinates
        return (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))

    def _intersect(l1, l2):
        (x1, y1), (x2, y2) = l1
        (x3, y3), (x4, y4) = l2
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(den) < 1e-9:
            return None
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

    for grid in model.by_type("IfcGrid"):
        try:
            gm = up.get_local_placement(grid.ObjectPlacement) if grid.ObjectPlacement else None
            gx, gy, gz = (float(gm[0][3]), float(gm[1][3]), float(gm[2][3])) if gm is not None else (0.0, 0.0, 0.0)
            us = [(getattr(a, "AxisTag", "U"), _axis_line(a)) for a in (grid.UAxes or [])]
            vs = [(getattr(a, "AxisTag", "V"), _axis_line(a)) for a in (grid.VAxes or [])]
            for ut, ul in us:
                for vt, vl in vs:
                    if not ul or not vl:
                        continue
                    ip = _intersect(ul, vl)
                    if ip is None:
                        continue
                    e, n, h = to_map(gx + ip[0], gy + ip[1], gz)
                    pts.append({"kind": "grid", "ifc_class": "IfcGrid", "guid": grid.GlobalId,
                                "tag": f"{ut}/{vt}", "e": e, "n": n, "z": h})
        except Exception:
            continue
    return pts


def points(model, classes: list[str] | None = None, include_grid: bool = True) -> list[dict[str, Any]]:
    """Layout setout points from the model, georeferenced. Each: number, E, N, Z, description (code +
    GlobalId), plus kind/ifc_class/guid. Grid intersections come first (they're the control skeleton)."""
    to_map = _map_fn(model)
    want = {c: LAYOUT_CLASSES.get(c, "PT") for c in (classes or LAYOUT_CLASSES)}
    rows: list[dict[str, Any]] = []
    if include_grid:
        rows.extend(_grid_points(model, to_map))
    seen: set[str] = set()
    for cls, code in want.items():
        for el in model.by_type(cls):
            g = getattr(el, "GlobalId", None)
            if not g or g in seen:
                continue
            xyz = _placement_xyz(el)
            if xyz is None:
                continue
            seen.add(g)
            e, n, z = to_map(*xyz)
            rows.append({"kind": "element", "ifc_class": cls, "guid": g,
                         "tag": getattr(el, "Name", None) or code, "e": e, "n": n, "z": z, "code": code})
    # number them P1.. and build the Description (code | grid-tag or name | GlobalId)
    out = []
    for i, r in enumerate(rows, start=1):
        if r["kind"] == "grid":
            desc = f"GRID-{r['tag']}|{r['guid']}"
        else:
            desc = f"{r.get('code', 'PT')}-{r['tag']}|{r['guid']}"
        out.append({"number": f"P{i}", "e": round(r["e"], 4), "n": round(r["n"], 4),
                    "z": round(r["z"], 4), "description": desc,
                    "kind": r["kind"], "ifc_class": r["ifc_class"], "guid": r["guid"]})
    return out


def to_penzd_csv(pts: list[dict], order: str = "PENZD", delimiter: str = ",", header: bool = True) -> str:
    """PENZD / PNEZD points file for total-station / robot import (configurable column order + delimiter)."""
    cols = _CSV_ORDERS.get(order.upper(), _CSV_ORDERS["PENZD"])
    label = {"p": "Point", "e": "Easting", "n": "Northing", "z": "Elevation", "d": "Description"}
    get = {"p": "number", "e": "e", "n": "n", "z": "z", "d": "description"}
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    if header:
        w.writerow([label[c] for c in cols])
    # CSV-SWEEP — the description is user text, but Easting/Northing/Elevation are routinely
    # NEGATIVE and a negative number opens with a formula lead. `cells.cell` passes plain numbers
    # through untouched, which is the only reason it is safe to apply to a survey points file at
    # all: escaping a coordinate would corrupt the import this format exists for.
    for p in pts:
        w.writerow([_cell(p[get[c]]) for c in cols])
    return buf.getvalue()


def to_dxf(pts: list[dict]) -> bytes:
    """Layered DXF for floor printers (Dusty-style): a POINT + a text label per setout point, one layer
    per element type so print styles map cleanly."""
    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for p in pts:
        layer = (p["ifc_class"] if p["kind"] == "element" else "IFCGRID").replace("Ifc", "").upper()
        if layer not in doc.layers:
            doc.layers.add(layer)
        msp.add_point((p["e"], p["n"], p["z"]), dxfattribs={"layer": layer})
        msp.add_text(p["number"], dxfattribs={"layer": layer, "height": 0.15}).set_placement((p["e"] + 0.1, p["n"] + 0.1))
    out = io.BytesIO()
    with io.TextIOWrapper(out, encoding="utf-8", newline="") as tw:
        doc.write(tw)
        tw.flush()
        return out.getvalue()


#: An IFC GlobalId is 22 characters of base64-ish alphabet, and `points()` writes it as the last
#: `|`-delimited field of the Description. Anchored to the end so a tag containing a pipe cannot
#: produce a false GUID, and length-exact so a short code never matches.
_DESC_GUID = re.compile(r"\|([0-9A-Za-z_$]{22})\s*$")


def _measured_rows(rows: list[dict]) -> list[dict[str, Any]]:
    """Parse as-installed shots into `[{guid, number, e, n, z}]`, keeping BOTH join keys.

    The GUID is read from an explicit `guid` field or recovered from the Description the exporter
    wrote — `to_penzd_csv` puts it in the D column precisely so the round-trip stays anchored, and
    until 2026-10-12 nothing on the way back read it.
    """
    out: list[dict[str, Any]] = []
    for r in rows:
        num = str(r.get("number") or r.get("point") or r.get("Point") or "").strip()
        desc = str(r.get("description") or r.get("Description") or "")
        guid = str(r.get("guid") or r.get("GlobalId") or "").strip()
        if not guid:
            hit = _DESC_GUID.search(desc)
            guid = hit.group(1) if hit else ""
        if not num and not guid:
            continue
        try:
            e = float(r.get("e", r.get("Easting", 0)))
            n = float(r.get("n", r.get("Northing", 0)))
            z = float(r.get("z", r.get("Elevation", 0)))
        except (TypeError, ValueError):
            continue
        out.append({"guid": guid, "number": num, "e": e, "n": n, "z": z})
    return out


def _parse_measured(rows: list[dict], order: str = "PENZD") -> dict[str, tuple[float, float, float]]:
    """`{number: (e,n,z)}` — kept for callers that only need the number map."""
    return {r["number"]: (r["e"], r["n"], r["z"]) for r in _measured_rows(rows) if r["number"]}


def verify(design: list[dict], measured: list[dict], tolerance_m: float = 0.02) -> dict[str, Any]:
    """Compare as-installed shots to the design setout, match **by GlobalId first**, compute 3-D
    deviation, and flag the points out of tolerance (each a candidate BCF topic / field-verification
    issue) **beside what could not be compared at all**.

    LAYOUT-RENUMBER — THE JOIN KEY WAS POSITIONAL
    ---------------------------------------------
    This matched on `number` alone, and `points()` assigns `number` as `P{i}` over its own iteration
    order. So the key is a POSITION, not an identity: re-publish the model, or export with a
    different `classes` filter, and every point is renumbered. A survey shot against last week's
    export then matches a *different element* by the same number — and the deviation is computed
    against the wrong design point, silently and plausibly. **That is the repository's first
    non-negotiable, inverted** ("reference model elements by GlobalId, never by a transient id"), and
    this module's own docstring already said *"match by Point-№ / GlobalId"*: the fix was documented
    and never built. The Description carries the GlobalId, so the stable key was in the file the
    whole time.

    AND BOTH UNMATCHED SIDES WERE DROPPED IN SILENCE
    ------------------------------------------------
    A design point with no shot was `continue`; a shot matching no design point was never looked at.
    So a survey file from the wrong floor, or one whose numbering had been regenerated, returned
    `checked: 0`, `out_of_tolerance: []`, `max_deviation_m: 0.0` — **character-for-character what a
    perfect as-built returns.** This is PROGRESS-DARK's defect (`capture_diff` promised "never
    silently dropped" and silently dropped) in a module that sweep never reached; the counts are the
    same repair, and `comparable` exists so no caller can mistake "nothing matched" for "nothing
    wrong".
    """
    parsed = _measured_rows(measured)
    by_guid: dict[str, int] = {}
    by_number: dict[str, int] = {}
    for i, r in enumerate(parsed):
        if r["guid"]:
            by_guid.setdefault(r["guid"], i)
        if r["number"]:
            by_number.setdefault(r["number"], i)

    # TWO PASSES, so the precedence is a statement rather than a loop order. Every GUID match is
    # taken first; only then may a number — a position — claim a remaining shot. A one-pass version
    # lets an early design point consume by number a shot that a later one owns by GlobalId.
    unclaimed = set(range(len(parsed)))
    match: dict[int, tuple[int, str]] = {}
    for di, p in enumerate(design):
        i = by_guid.get(str(p.get("guid") or ""))
        if i is not None and i in unclaimed:
            match[di] = (i, "guid")
            unclaimed.discard(i)
    for di, p in enumerate(design):
        if di in match:
            continue
        i = by_number.get(str(p.get("number") or ""))
        if i is not None and i in unclaimed:
            match[di] = (i, "number")
            unclaimed.discard(i)

    devs = []
    unshot: list[str] = []
    for di, p in enumerate(design):
        hit = match.get(di)
        if hit is None:
            unshot.append(str(p.get("number") or p.get("guid") or "?"))
            continue
        i, on = hit
        mv = parsed[i]
        d = math.dist((p["e"], p["n"], p["z"]), (mv["e"], mv["n"], mv["z"]))
        devs.append({"number": p["number"], "guid": p["guid"], "ifc_class": p["ifc_class"],
                     "deviation_m": round(d, 4), "in_tolerance": d <= tolerance_m,
                     "matched_on": on,
                     "design": {"e": p["e"], "n": p["n"], "z": p["z"]},
                     "measured": {"e": round(mv["e"], 4), "n": round(mv["n"], 4),
                                  "z": round(mv["z"], 4)}})
    out = [d for d in devs if not d["in_tolerance"]]
    by_number_only = [d for d in devs if d["matched_on"] == "number"]
    unmatched = [parsed[i]["number"] or parsed[i]["guid"] for i in sorted(unclaimed)]
    n_design = len(design)
    return {"tolerance_m": tolerance_m, "checked": len(devs), "in_tolerance": len(devs) - len(out),
            "out_of_tolerance": out, "deviations": devs,
            "max_deviation_m": max((d["deviation_m"] for d in devs), default=0.0),
            # WHAT COULD NOT BE COMPARED, which is the half that was missing.
            "design_points": n_design, "shots_supplied": len(parsed),
            "matched_on_guid": len(devs) - len(by_number_only),
            "matched_on_number": len(by_number_only),
            "number_matched_points": [d["number"] for d in by_number_only][:200],
            "unshot": len(unshot), "unshot_numbers": unshot[:200],
            "unmatched_shots": len(unmatched), "unmatched_numbers": unmatched[:200],
            "coverage_pct": round(100 * len(devs) / n_design, 1) if n_design else 0.0,
            # `comparable` is false when nothing matched. A caller reading `out_of_tolerance == []`
            # on an unmatched file would otherwise report a clean as-built, which is the whole defect.
            "comparable": bool(devs),
            "note": "As-installed vs design setout, matched by GlobalId first and by Point-№ only as a "
                    "fallback \u2014 the number is positional (`P1..` in export order), so a number match is "
                    "a match on where the point sat in a particular export and not on which element it "
                    "is. Points out of tolerance should be raised as field-verification issues (BCF), "
                    "anchored to the element GlobalId."
                    + (f" {len(devs)} of {n_design} design point(s) were shot ("
                       f"{len(by_number_only)} by number only); {len(unmatched)} supplied shot(s) "
                       f"matched no design point." if n_design else " No design setout points.")
                    + ("" if devs else " NOTHING MATCHED: this is not a clean as-built \u2014 no comparison "
                       "was made. Check that the shots came from this model's export (the Description "
                       "column carries the GlobalId) rather than a re-numbered or different one.")}
