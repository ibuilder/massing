"""Generative massing — turn a municipal zoning envelope (lot, FAR, setbacks, height limit) into
a buildable program + a real IFC model (stacked floor-plate spaces). The IFC-native answer to
TestFit/Forma feasibility: the output is openBIM, so it flows straight into drawings, QTO, the
estimate, and the model→proforma link.

`compute_massing()` is pure (zoning math, unit-testable). `generate_ifc()` writes a minimal valid
IFC4 with a site/building + one IfcBuildingStorey and floor-plate IfcSpace per level (areas in the
Qto so the spaces/estimate/proforma engines read them).
"""
from __future__ import annotations

import math
from typing import Any

M2_TO_SF = 10.7639


def _polygon_area(poly: list) -> float:
    """Shoelace area (m²) of a closed polygon given as [[x,y],...] in metres."""
    n = len(poly)
    a = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def _signed_area(poly: list) -> float:
    n = len(poly); a = 0.0
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def offset_polygon(poly: list, d: float) -> list:
    """Inward-offset (shrink) a simple polygon by `d` metres — the real buildable footprint after a
    uniform setback, instead of approximating with the bounding box. Each edge is pushed inward along
    its normal and consecutive edges re-intersected. Returns the offset polygon, or [] if it collapses
    (setback larger than the parcel can take). Robust for convex parcels and mild concavity."""
    import math as _m

    pts = [[float(x), float(y)] for x, y in poly]
    if len(pts) < 3 or d <= 0:
        return pts
    if _signed_area(pts) < 0:                 # normalise to CCW so the left normal points inward
        pts = pts[::-1]
    n = len(pts)
    lines = []                                # each shifted edge as (point, unit-direction)
    for i in range(n):
        ax, ay = pts[i]; bx, by = pts[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        ln = _m.hypot(ex, ey) or 1e-9
        ux, uy = ex / ln, ey / ln
        nx, ny = -uy, ux                      # inward (left) normal for CCW
        lines.append(((ax + nx * d, ay + ny * d), (ux, uy)))

    def _intersect(l1, l2):
        (p1, d1), (p2, d2) = l1, l2
        denom = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(denom) < 1e-9:                 # parallel — fall back to the shifted endpoint
            return p2
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / denom
        return [p1[0] + d1[0] * t, p1[1] + d1[1] * t]

    out = [_intersect(lines[i - 1], lines[i]) for i in range(n)]
    # collapsed / over-offset (setback deeper than the parcel can take) → no buildable area. A
    # double-inversion can keep positive area, so also reject if any edge flipped direction.
    for i in range(n):
        ix, iy = pts[(i + 1) % n][0] - pts[i][0], pts[(i + 1) % n][1] - pts[i][1]
        ox, oy = out[(i + 1) % n][0] - out[i][0], out[(i + 1) % n][1] - out[i][1]
        if ix * ox + iy * oy < 0:             # edge reversed → polygon turned inside-out
            return []
    if _polygon_area(out) < 1.0 or _signed_area(out) <= 0:
        return []
    return [[round(x, 3), round(y, 3)] for x, y in out]


def compute_massing(p: dict) -> dict[str, Any]:
    """Zoning envelope → program. Inputs (metres): lot_width/lot_depth or lot_area or lot_polygon
    ([[x,y],…]), far, coverage_max, front/side/rear_setback, height_limit, floor_to_floor,
    efficiency, avg_unit_m2."""
    lot_w, lot_d = float(p.get("lot_width") or 0), float(p.get("lot_depth") or 0)
    lot_area = float(p.get("lot_area") or (lot_w * lot_d))
    poly = p.get("lot_polygon")
    ss, fs, rs = float(p.get("side_setback", 0)), float(p.get("front_setback", 0)), float(p.get("rear_setback", 0))
    far = float(p.get("far", 1.0))
    coverage = float(p.get("coverage_max", 0.6))
    f2f = float(p.get("floor_to_floor", 3.5))
    height_limit = p.get("height_limit")
    buildable_poly = None

    if poly and len(poly) >= 3:                  # real parcel: area from shoelace, dims from bbox
        lot_area = _polygon_area(poly)
        xs = [float(pt[0]) for pt in poly]; ys = [float(pt[1]) for pt in poly]
        lot_w, lot_d = max(xs) - min(xs), max(ys) - min(ys)
        # true inward polygon offset by a uniform setback — the real buildable footprint, not a
        # bounding-box guess. A polygon has no front/rear/side semantics, so use the average of the
        # provided (nonzero) setbacks.
        _nz = [v for v in (ss, fs, rs) if v > 0]
        sb = sum(_nz) / len(_nz) if _nz else 0.0
        if sb > 0:
            buildable_poly = offset_polygon(poly, sb)
            poly_fp = _polygon_area(buildable_poly) if buildable_poly else 0.0
        else:
            buildable_poly = [[float(x), float(y)] for x, y in poly]
            poly_fp = lot_area
    if lot_area <= 0:
        raise ValueError("provide lot_area, lot_width × lot_depth, or a lot_polygon")

    if buildable_poly is not None:               # polygon parcel → use the offset footprint area
        fp_raw = poly_fp
        bx = [pt[0] for pt in buildable_poly] or [0]; by = [pt[1] for pt in buildable_poly] or [0]
        fw, fd = (max(bx) - min(bx)) or 1.0, (max(by) - min(by)) or 1.0
    elif lot_w and lot_d:
        fw, fd = max(1.0, lot_w - 2 * ss), max(1.0, lot_d - fs - rs)
        fp_raw = fw * fd
    else:
        side = math.sqrt(lot_area); fw = fd = max(1.0, side - 2 * ss)
        fp_raw = fw * fd
    footprint = min(fp_raw, lot_area * coverage)
    # rescale plate dims to the coverage-capped footprint (keep aspect ratio)
    if fw * fd > footprint and fw * fd > 0:
        k = math.sqrt(footprint / (fw * fd)); fw, fd = fw * k, fd * k

    max_gfa = lot_area * far
    floors_by_far = max(1, math.ceil(max_gfa / footprint)) if footprint else 1
    floors_by_height = int(height_limit // f2f) if height_limit else floors_by_far
    floors = max(1, min(floors_by_far, floors_by_height))
    gfa = min(floors * footprint, max_gfa)
    binding = ("height" if floors_by_height < floors_by_far else
               ("coverage" if footprint >= lot_area * coverage - 1e-6 and floors >= floors_by_far else "FAR"))
    eff = float(p.get("efficiency", 0.82))
    avg_unit = float(p.get("avg_unit_m2", 0) or 0)
    units = int(gfa * eff / avg_unit) if avg_unit else 0

    return {
        "lot_area_m2": round(lot_area, 1), "far": far, "far_achieved": round(gfa / lot_area, 2),
        "footprint_m2": round(footprint, 1), "plate_w": round(fw, 2), "plate_d": round(fd, 2),
        "floors": floors, "floor_to_floor": f2f, "building_height_m": round(floors * f2f, 1),
        "buildable_gfa_m2": round(gfa, 1), "buildable_gfa_sf": round(gfa * M2_TO_SF),
        "net_sellable_m2": round(gfa * eff, 1), "units": units, "binding_constraint": binding,
        **({"buildable_polygon": buildable_poly} if buildable_poly is not None else {}),
    }


def gridlines(extent: float, bay: float) -> list[float]:
    """Evenly-spaced grid line positions across `extent` (centred on 0) with spacing ≈ `bay` —
    columns land on both edges and the interior. Returns n+1 coordinates for n bays."""
    n = max(1, round(extent / max(0.5, bay)))
    step = extent / n
    return [round(-extent / 2 + i * step, 3) for i in range(n + 1)]


def generate_ifc(metrics: dict, out_path: str, name: str = "Massing Study",
                 frame: bool = False, bay: float = 7.5, units: bool = False,
                 envelope: bool = False, wwr: float = 0.4, core: bool = False,
                 unit_layout: str = "grid", members: dict | None = None,
                 parking: int = 0) -> str:
    """Write an IFC4 model: site → building → one storey + slab per level. Each floor gets either a
    single floor-plate space, or — with `units=True` — the floor subdivided into per-unit IfcSpaces
    (the proforma's unit count), so areas/COBie/rent are grounded in real apartments. With
    `frame=True`, also generate a concrete structural frame on a ~`bay`-metre column grid. With
    `envelope=True`, wrap each floor in perimeter facade walls + ribbon windows at the given
    window-to-wall ratio `wwr` — so elevations show an enclosure and the energy model has real
    exterior-wall + glazing areas."""
    import math

    import ifcopenshell
    import ifcopenshell.api
    import numpy as np

    floors = int(metrics["floors"])
    fw, fd, f2f = float(metrics["plate_w"]), float(metrics["plate_d"]), float(metrics["floor_to_floor"])
    plate_area = round(fw * fd, 2)
    units_per_floor = max(1, round(int(metrics.get("units", 0)) / floors)) if units else 0
    # member sizes — defaults, overridable by the structural advisor (R3) via `members` (metres)
    mem = members or {}
    SLAB_T = float(mem.get("slab_m", 0.3))   # thin floor plate per level (renders the massing)
    COL = float(mem.get("column_m", 0.6))
    BEAM_W = float(mem.get("beam_width_m", 0.4))
    BEAM_D = float(mem.get("beam_depth_m", 0.6))

    def rect_profile(m, w, d):
        # web-ifc REQUIRES IfcProfileDef.Position (ifcopenshell tolerates None, web-ifc skips the
        # element silently → empty .frag). Always set an origin placement.
        pos = m.create_entity("IfcAxis2Placement2D",
                              Location=m.create_entity("IfcCartesianPoint", (0.0, 0.0)),
                              RefDirection=m.create_entity("IfcDirection", (1.0, 0.0)))
        return m.create_entity("IfcRectangleProfileDef", ProfileType="AREA", Position=pos, XDim=w, YDim=d)

    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name=name)
    # METRE length unit (scale 1.0) — all massing geometry/placements below are written in metres;
    # the default would be MILLIMETRE, which silently shrinks the model 1000x (renders empty).
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})
    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", model, context_type="Model",
                                context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Building")
    ifcopenshell.api.run("aggregate.assign_object", model, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[building], relating_object=site)

    def add_column(storey, elev, x, y):
        col = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcColumn", name="Column",
                                   predefined_type="COLUMN")
        m = np.eye(4); m[0, 3] = x; m[1, 3] = y; m[2, 3] = elev
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=col, matrix=m)
        rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                   profile=rect_profile(model, COL, COL), depth=f2f)
        ifcopenshell.api.run("geometry.assign_representation", model, product=col, representation=rep)
        ifcopenshell.api.run("spatial.assign_container", model, products=[col], relating_structure=storey)

    def add_beam(storey, elev, x1, y1, x2, y2):
        import math
        length = math.hypot(x2 - x1, y2 - y1) or 1.0
        dx, dy = (x2 - x1) / length, (y2 - y1) / length
        beam = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBeam", name="Beam",
                                    predefined_type="BEAM")
        m = np.array([[-dy, 0, dx, x1], [dx, 0, dy, y1], [0, 1, 0, elev], [0, 0, 0, 1]], dtype=float)
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=beam, matrix=m)
        rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                   profile=rect_profile(model, BEAM_W, BEAM_D), depth=length)
        ifcopenshell.api.run("geometry.assign_representation", model, product=beam, representation=rep)
        ifcopenshell.api.run("spatial.assign_container", model, products=[beam], relating_structure=storey)

    def make_space(storey, elev, name, longname, cx, cy, w, d, reference):
        sp = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSpace", name=name)
        sp.LongName = longname
        m = np.eye(4); m[0, 3] = cx; m[1, 3] = cy; m[2, 3] = elev
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=sp, matrix=m)
        rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                   profile=rect_profile(model, w, d), depth=f2f)
        ifcopenshell.api.run("geometry.assign_representation", model, product=sp, representation=rep)
        ifcopenshell.api.run("aggregate.assign_object", model, products=[sp], relating_object=storey)
        area = round(w * d, 2)
        qto = ifcopenshell.api.run("pset.add_qto", model, product=sp, name="Qto_SpaceBaseQuantities")
        ifcopenshell.api.run("pset.edit_qto", model, qto=qto,
                             properties={"NetFloorArea": area, "GrossFloorArea": area,
                                         "NetVolume": round(area * f2f, 2), "Height": f2f})
        ps = ifcopenshell.api.run("pset.add_pset", model, product=sp, name="Pset_SpaceCommon")
        ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties={"Reference": reference})
        return sp

    def unit_grid(n, w, d):
        cols = max(1, round(math.sqrt(n * w / d)))
        rows = max(1, math.ceil(n / cols))
        return cols, rows

    def add_box(cls, storey, elev, cx, cy, w, d, h, predefined=None, name=None):
        """A vertical box element (cx,cy plan centre, extruded up by h) — for cores/MEP stubs."""
        kw = {"predefined_type": predefined} if predefined else {}
        try:
            el = ifcopenshell.api.run("root.create_entity", model, ifc_class=cls,
                                      name=name or cls.replace("Ifc", ""), **kw)
        except Exception:                        # noqa: BLE001 — invalid predefined enum for this class
            el = ifcopenshell.api.run("root.create_entity", model, ifc_class=cls, name=name or cls.replace("Ifc", ""))
        m = np.eye(4); m[0, 3] = cx; m[1, 3] = cy; m[2, 3] = elev
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=el, matrix=m)
        rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                   profile=rect_profile(model, w, d), depth=h)
        ifcopenshell.api.run("geometry.assign_representation", model, product=el, representation=rep)
        ifcopenshell.api.run("spatial.assign_container", model, products=[el], relating_structure=storey)
        return el

    def add_planar(cls, storey, elev, x1, y1, x2, y2, length_frac, depth, height, psets=None):
        """A vertical planar element (wall/window) along the x1y1->x2y2 edge: a rectangular profile
        (edge length × `depth`) extruded up by `height`, centred on the edge and rotated to it."""
        length = math.hypot(x2 - x1, y2 - y1) or 1.0
        ang = math.atan2(y2 - y1, x2 - x1)
        c, s = math.cos(ang), math.sin(ang)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        el = ifcopenshell.api.run("root.create_entity", model, ifc_class=cls, name=cls.replace("Ifc", ""))
        m = np.array([[c, -s, 0, mx], [s, c, 0, my], [0, 0, 1, elev], [0, 0, 0, 1]], dtype=float)
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=el, matrix=m)
        rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                   profile=rect_profile(model, length * length_frac, depth), depth=height)
        ifcopenshell.api.run("geometry.assign_representation", model, product=el, representation=rep)
        ifcopenshell.api.run("spatial.assign_container", model, products=[el], relating_structure=storey)
        for pset_name, props in (psets or {}).items():
            ps = ifcopenshell.api.run("pset.add_pset", model, product=el, name=pset_name)
            ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties=props)
        return el

    gx = gridlines(fw, bay)
    gy = gridlines(fd, bay)
    for i in range(floors):
        elev = i * f2f
        storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey",
                                      name=f"Level {i + 1}")
        storey.Elevation = elev
        ifcopenshell.api.run("aggregate.assign_object", model, products=[storey], relating_object=building)
        if units_per_floor and unit_layout == "corridor":   # double-loaded corridor test-fit layout
            corridor_w = min(2.0, fd * 0.2)
            bay_d = max(2.5, (fd - corridor_w) / 2)
            per_side = math.ceil(units_per_floor / 2)
            uw = fw / per_side
            k = 0
            for side in (1, -1):                  # N then S of the central corridor
                cy = side * (corridor_w / 2 + bay_d / 2)
                for c in range(per_side):
                    if k >= units_per_floor:
                        break
                    k += 1
                    cx = -fw / 2 + (c + 0.5) * uw
                    make_space(storey, elev, f"L{i + 1} Unit {k:02d}", f"Unit {k:02d}",
                               cx, cy, uw * 0.96, bay_d * 0.96, "UNIT")
            make_space(storey, elev, f"L{i + 1} Corridor", "Corridor", 0.0, 0.0, fw, corridor_w, "CIRCULATION")
        elif units_per_floor:                    # subdivide the floor into per-unit apartments
            cols, rows = unit_grid(units_per_floor, fw, fd)
            cw, cd = fw / cols, fd / rows
            k = 0
            for r in range(rows):
                for c in range(cols):
                    if k >= units_per_floor:
                        break
                    k += 1
                    cx = -fw / 2 + (c + 0.5) * cw
                    cy = -fd / 2 + (r + 0.5) * cd
                    # 0.96 leaves a hair of demising-wall gap so units read as separate volumes
                    make_space(storey, elev, f"L{i + 1} Unit {k:02d}", f"Unit {k:02d}",
                               cx, cy, cw * 0.96, cd * 0.96, "UNIT")
        else:
            make_space(storey, elev, f"Level {i + 1} floor plate", f"Floor plate {i + 1}",
                       0.0, 0.0, fw, fd, "PLATE")
        # renderable floor plate (IfcSlab) so the massing is visible in the viewer
        slab = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSlab",
                                    name=f"Level {i + 1} plate", predefined_type="FLOOR")
        smat = np.eye(4); smat[2, 3] = elev
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=slab, matrix=smat)
        sprofile = rect_profile(model, fw, fd)
        srep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                    profile=sprofile, depth=SLAB_T)
        ifcopenshell.api.run("geometry.assign_representation", model, product=slab, representation=srep)
        ifcopenshell.api.run("spatial.assign_container", model, products=[slab], relating_structure=storey)

        if frame:                              # concrete frame: columns on the grid + beams both ways
            for x in gx:
                for y in gy:
                    add_column(storey, elev, x, y)
            for y in gy:                       # beams along X
                for j in range(len(gx) - 1):
                    add_beam(storey, elev, gx[j], y, gx[j + 1], y)
            for x in gx:                       # beams along Y
                for j in range(len(gy) - 1):
                    add_beam(storey, elev, x, gy[j], x, gy[j + 1])

        if envelope:                           # perimeter facade walls + ribbon windows per floor
            hw, hd = fw / 2, fd / 2
            edges = [(-hw, -hd, hw, -hd), (hw, hd, -hw, hd),     # front, back (along X)
                     (hw, -hd, hw, hd), (-hw, hd, -hw, -hd)]      # right, left (along Y)
            sill = f2f * 0.1
            for (x1, y1, x2, y2) in edges:
                add_planar("IfcWall", storey, elev, x1, y1, x2, y2, 1.0, 0.2, f2f,
                           psets={"Pset_WallCommon": {"IsExternal": True, "LoadBearing": False}})
                win = add_planar("IfcWindow", storey, elev + sill, x1, y1, x2, y2, 0.9, 0.05,
                                 max(0.3, f2f * float(wwr)))
                length = math.hypot(x2 - x1, y2 - y1) or 1.0
                try:
                    win.OverallWidth = length * 0.9
                    win.OverallHeight = max(0.3, f2f * float(wwr))
                except Exception:                # noqa: BLE001 — attributes are optional
                    pass

        if core:                               # service core: shafts + stair + MEP risers
            cw, cd = min(7.0, fw * 0.4), min(5.0, fd * 0.5)
            ccx, ccy = 0.0, fd / 2 - cd / 2 - 1.0    # core to the rear, off the facade
            half_w, half_d = cw / 2, cd / 2
            for (x1, y1, x2, y2) in [(ccx - half_w, ccy - half_d, ccx + half_w, ccy - half_d),
                                     (ccx + half_w, ccy + half_d, ccx - half_w, ccy + half_d),
                                     (ccx + half_w, ccy - half_d, ccx + half_w, ccy + half_d),
                                     (ccx - half_w, ccy + half_d, ccx - half_w, ccy - half_d)]:
                add_planar("IfcWall", storey, elev, x1, y1, x2, y2, 1.0, 0.2, f2f,
                           psets={"Pset_WallCommon": {"IsExternal": False, "LoadBearing": True}})
            add_box("IfcTransportElement", storey, elev, ccx - 1.4, ccy, 2.0, 2.4, f2f,
                    predefined="ELEVATOR", name="Elevator")
            add_box("IfcStair", storey, elev, ccx + 1.6, ccy, 2.6, cd * 0.8, f2f, name="Egress stair 1")
            add_box("IfcDuctSegment", storey, elev, ccx - half_w + 0.4, ccy + half_d - 0.4,
                    0.5, 0.5, f2f, name="Supply riser")
            add_box("IfcPipeSegment", storey, elev, ccx + half_w - 0.4, ccy + half_d - 0.4,
                    0.3, 0.3, f2f, name="Plumbing riser")
            # A2 — a SECOND means of egress, placed at the opposite corner from the rear core so the
            # two stairs are remote (≥⅓-diagonal separation, IBC 1007.1.1) — two code-positioned exits.
            esx, esy = -fw / 2 + 1.6, -(fd / 2 - cd / 2 - 1.0)
            add_box("IfcStair", storey, elev, esx, esy, 2.6, min(4.0, fd * 0.45), f2f, name="Egress stair 2")
    if parking:                                  # A2 — surface parking lot as real IfcSpace stalls
        STALL_W, STALL_D, AISLE = 2.5, 5.0, 7.0  # standard stall (m) + two-way drive aisle
        pstorey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey",
                                       name="Site Parking")
        pstorey.Elevation = 0.0
        ifcopenshell.api.run("aggregate.assign_object", model, products=[pstorey], relating_object=building)
        per_row = max(1, int(fw // STALL_W))      # stalls per row across the building width
        y0 = fd / 2 + 6.0                         # lot begins beyond the rear setback
        placed, row = 0, 0
        n = int(parking)
        while placed < n and row < 60:            # a module = two stall rows back-to-back + an aisle
            base = y0 + row * (2 * STALL_D + AISLE)
            for ry in (base + STALL_D / 2, base + STALL_D + AISLE + STALL_D / 2):
                x = -fw / 2 + STALL_W / 2
                col = 0
                while placed < n and col < per_row:
                    make_space(pstorey, 0.0, f"Stall {placed + 1:03d}", f"Parking {placed + 1:03d}",
                               x, ry, STALL_W * 0.94, STALL_D * 0.94, "PARKING")
                    x += STALL_W; col += 1; placed += 1
            row += 1
    from . import material_layers, materials
    materials.apply_palette(model)               # real IFC materials + surface colours (M1)
    material_layers.apply_layer_sets(model)      # Revit-style layered assemblies on walls/slabs/roofs (M3)
    model.write(out_path)
    return out_path


def dome_metrics(radius: float, efficiency: float = 0.85, avg_unit_m2: float = 0) -> dict[str, Any]:
    """Program metrics for a monolithic / earth dome house (a hemisphere of `radius` m)."""
    import math
    fa = math.pi * radius * radius
    return {"floors": 1, "footprint_m2": round(fa, 1), "plate_w": round(2 * radius, 2),
            "plate_d": round(2 * radius, 2), "floor_to_floor": round(radius, 2),
            "building_height_m": round(radius, 1), "buildable_gfa_m2": round(fa, 1),
            "buildable_gfa_sf": round(fa * M2_TO_SF), "net_sellable_m2": round(fa * efficiency, 1),
            "units": 1, "binding_constraint": "dome", "shape": "dome", "radius_m": radius}


def generate_dome_ifc(out_path: str, name: str = "Earth Dome House", radius: float = 8.0,
                      thickness: float = 0.3, segs: int = 32, rings: int = 14) -> str:
    """Write an IFC4 monolithic/earth dome: a hemispherical shell (IfcRoof as a triangulated face
    set) on a circular floor slab, with an interior IfcSpace carrying the floor area. Renders in the
    viewer (tessellation) and feeds budget/QTO/furnish like any other model."""
    import math

    import ifcopenshell
    import ifcopenshell.api
    import numpy as np

    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name=name)
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})
    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", model, context_type="Model",
                                context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Building")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Ground floor")
    ifcopenshell.api.run("aggregate.assign_object", model, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[building], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[storey], relating_object=building)

    def circle_profile(r):
        pos = model.create_entity("IfcAxis2Placement2D",
                                  Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0)),
                                  RefDirection=model.create_entity("IfcDirection", (1.0, 0.0)))
        return model.create_entity("IfcCircleProfileDef", ProfileType="AREA", Position=pos, Radius=float(r))

    def place(el, z=0.0):
        m = np.eye(4); m[2, 3] = z
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=el, matrix=m)

    # --- hemispherical shell as a triangulated face set (the dome roof) ---
    coords, faces = [], []
    for ri in range(rings + 1):
        phi = (math.pi / 2) * (ri / rings)          # 0 at apex → π/2 at base
        z, rad = radius * math.cos(phi), radius * math.sin(phi)
        for s in range(segs):
            th = 2 * math.pi * s / segs
            coords.append([round(rad * math.cos(th), 4), round(rad * math.sin(th), 4), round(z, 4)])
    for ri in range(rings):
        for s in range(segs):
            a = ri * segs + s + 1; b = ri * segs + (s + 1) % segs + 1
            c = (ri + 1) * segs + s + 1; d = (ri + 1) * segs + (s + 1) % segs + 1
            faces.append([a, c, d]); faces.append([a, d, b])     # 1-based, CCW
    plist = model.create_entity("IfcCartesianPointList3D", CoordList=coords)
    tfs = model.create_entity("IfcTriangulatedFaceSet", Coordinates=plist, CoordIndex=faces, Closed=False)
    shell_rep = model.create_entity("IfcShapeRepresentation", ContextOfItems=body,
                                    RepresentationIdentifier="Body", RepresentationType="Tessellation", Items=[tfs])
    roof = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcRoof", name="Dome shell")
    place(roof)
    roof.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[shell_rep])
    ifcopenshell.api.run("spatial.assign_container", model, products=[roof], relating_structure=storey)
    ps = ifcopenshell.api.run("pset.add_pset", model, product=roof, name="Pset_RoofCommon")
    ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties={"IsExternal": True})

    # --- circular floor slab ---
    slab = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSlab", name="Floor slab", predefined_type="BASESLAB")
    place(slab, -0.2)
    srep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                profile=circle_profile(radius), depth=0.2)
    ifcopenshell.api.run("geometry.assign_representation", model, product=slab, representation=srep)
    ifcopenshell.api.run("spatial.assign_container", model, products=[slab], relating_structure=storey)

    # --- interior space (carries the floor area) ---
    space = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSpace", name="Interior")
    space.LongName = "Dome interior"
    place(space)
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                               profile=circle_profile(radius * 0.97), depth=max(2.4, radius * 0.85))
    ifcopenshell.api.run("geometry.assign_representation", model, product=space, representation=rep)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[space], relating_object=storey)
    area = round(math.pi * radius * radius, 2)
    qto = ifcopenshell.api.run("pset.add_qto", model, product=space, name="Qto_SpaceBaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", model, qto=qto,
                         properties={"NetFloorArea": area, "GrossFloorArea": area})
    from . import material_layers, materials
    materials.apply_palette(model)               # real IFC materials + surface colours (M1)
    material_layers.apply_layer_sets(model)      # Revit-style layered assemblies on walls/slabs/roofs (M3)
    model.write(out_path)
    return out_path
