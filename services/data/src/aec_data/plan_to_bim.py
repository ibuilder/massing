"""2D → BIM raise: turn a flat CAD floor plan (DXF) into a real, GUID-keyed IFC4 model — walls
extruded from the plan's line-work and IfcSpaces from its closed room polygons. The complement to the
scan-to-BIM deviation loop: one raises design intent *up* from 2D drafting into a model, the other
checks the *built* result back against it.

Estimators and drafters still live in 2D CAD. This gives them a one-click path from a legacy plan to
an openBIM model that flows straight into the viewer, QTO, the estimate, and coordination — instead of
re-modelling from scratch.

`parse_plan()` is pure over ezdxf (MIT) and needs no ifcopenshell — cheap enough for a preview.
`raise_plan()` writes the IFC via ifcopenshell.api (same wall/space patterns as massing.generate_ifc).
Permissive libs only: ezdxf reads DXF natively; DWG must be converted to DXF externally (no AGPL)."""
from __future__ import annotations

import math
from typing import Any

# DXF $INSUNITS header code -> metres-per-unit (shared convention with dxf_takeoff).
_INSUNITS_M = {0: 1.0, 1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0, 8: 2.54e-5, 9: 0.001, 10: 0.9144}
_INSUNITS_LABEL = {0: "unitless (assumed m)", 1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m",
                   8: "microinch", 9: "mil", 10: "yd"}


def _shoelace(pts: list[tuple[float, float]]) -> float:
    if len(pts) < 3:
        return 0.0
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _poly_points(e) -> tuple[list[tuple[float, float]], bool]:
    try:
        if e.dxftype() == "LWPOLYLINE":
            return [(p[0], p[1]) for p in e.get_points("xy")], bool(e.closed)
        pts = [(v.dxf.location[0], v.dxf.location[1]) for v in e.vertices]
        return pts, bool(e.is_closed)
    except Exception:       # noqa: BLE001 — malformed entity: skip it, don't crash the raise
        return [], False


def parse_plan(path: str, wall_layers: list[str] | None = None,
               min_wall_m: float = 0.15, min_room_m2: float = 1.0) -> dict[str, Any]:
    """Read a DXF and separate it into wall segments + room polygons, in metres.

    Walls: every LINE and every span of an open polyline (and the edges of closed polylines) on a
    wall layer. If `wall_layers` is None, we auto-detect layers whose name contains "wall"; failing
    that (no such layer), we take all line-work. Rooms: closed polylines enclosing >= `min_room_m2`.
    Segments shorter than `min_wall_m` (after unit scaling) are dropped as noise.

    Returns {segments:[[x1,y1,x2,y2,layer],...], rooms:[{points,area_m2,layer,centroid}],
    units, unit_scale, bounds, wall_count, room_count, total_wall_length_m, total_floor_area_m2}."""
    try:
        import ezdxf  # lazy — keeps import cheap and the dep swappable
    except ImportError as e:  # pragma: no cover — dep is declared
        raise RuntimeError("2D->BIM raise needs the 'ezdxf' package") from e
    try:
        doc = ezdxf.readfile(path)
    except Exception as e:  # noqa: BLE001 — surface a clean 4xx-able error for a bad upload
        raise RuntimeError(f"could not read DXF: {e}") from e

    insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    scale = _INSUNITS_M.get(insunits, 1.0)
    msp = doc.modelspace()

    # Which layers are walls? explicit arg > auto-detect "wall" layers > all line-work.
    layer_names = {ly.dxf.name for ly in doc.layers}
    if wall_layers:
        wall_set = {ly.lower() for ly in wall_layers}
    else:
        auto = {ly.lower() for ly in layer_names if "wall" in ly.lower()}
        wall_set = auto  # empty set => fall through to "all line-work" below
    room_hints = {ly.lower() for ly in layer_names if any(h in ly.lower() for h in ("room", "space", "area"))}

    def _is_wall_layer(layer: str) -> bool:
        return (not wall_set) or (layer.lower() in wall_set)

    segments: list[list] = []
    rooms: list[dict] = []
    seen: set[tuple] = set()
    xs: list[float] = []
    ys: list[float] = []

    def _add_seg(x1, y1, x2, y2, layer):
        x1, y1, x2, y2 = x1 * scale, y1 * scale, x2 * scale, y2 * scale
        if math.hypot(x2 - x1, y2 - y1) < min_wall_m:
            return
        ends = sorted([(round(x1, 3), round(y1, 3)), (round(x2, 3), round(y2, 3))])
        key = (ends[0], ends[1])                       # order-independent dedup
        if key in seen:
            return
        seen.add(key)
        segments.append([round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4), layer])
        xs.extend([x1, x2]); ys.extend([y1, y2])

    for e in msp:
        t = e.dxftype()
        layer = getattr(e.dxf, "layer", "0")
        if t == "LINE" and _is_wall_layer(layer):
            s, en = e.dxf.start, e.dxf.end
            _add_seg(s[0], s[1], en[0], en[1], layer)
        elif t in ("LWPOLYLINE", "POLYLINE"):
            pts, closed = _poly_points(e)
            if len(pts) < 2:
                continue
            spts = [(x * scale, y * scale) for x, y in pts]
            # a closed polygon on a room/space layer (or any closed loop enclosing area) -> room
            if closed and len(spts) >= 3:
                area = _shoelace(spts)
                is_room = (layer.lower() in room_hints) or (not room_hints and area >= min_room_m2)
                if is_room and area >= min_room_m2:
                    cx = sum(p[0] for p in spts) / len(spts)
                    cy = sum(p[1] for p in spts) / len(spts)
                    rooms.append({"points": [[round(x, 4), round(y, 4)] for x, y in spts],
                                  "area_m2": round(area, 2), "layer": layer,
                                  "centroid": [round(cx, 4), round(cy, 4)]})
            # edges become walls when the polyline is on a wall layer
            if _is_wall_layer(layer):
                rng = range(len(pts)) if closed else range(len(pts) - 1)
                for i in rng:
                    a = pts[i]; b = pts[(i + 1) % len(pts)]
                    _add_seg(a[0], a[1], b[0], b[1], layer)

    bounds = None
    if xs and ys:
        bounds = {"min": [round(min(xs), 3), round(min(ys), 3)],
                  "max": [round(max(xs), 3), round(max(ys), 3)]}
    total_len = round(sum(math.hypot(s[2] - s[0], s[3] - s[1]) for s in segments), 2)
    total_area = round(sum(r["area_m2"] for r in rooms), 2)
    return {
        "segments": segments, "rooms": rooms,
        "units": _INSUNITS_LABEL.get(insunits, "unknown"), "unit_scale": scale,
        "bounds": bounds,
        "wall_count": len(segments), "room_count": len(rooms),
        "total_wall_length_m": total_len, "total_floor_area_m2": total_area,
    }


def raise_plan(path: str, out_path: str, wall_height: float = 3.0, wall_thickness: float = 0.2,
               storey_elevation: float = 0.0, wall_layers: list[str] | None = None,
               name: str = "Raised from 2D") -> dict[str, Any]:
    """Build an IFC4 model from a DXF plan: one IfcBuildingStorey with an IfcWall per detected
    segment and an IfcSpace per detected room. Writes to `out_path` and returns the parse stats plus
    {ifc_path, wall_count, space_count}. Geometry is in metres; every element gets a stable GUID."""
    import ifcopenshell
    import ifcopenshell.api
    import numpy as np

    plan = parse_plan(path, wall_layers=wall_layers)
    if not plan["segments"] and not plan["rooms"]:
        raise RuntimeError("no wall segments or room polygons found in the DXF")

    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name=name)
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})
    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", model, context_type="Model",
                                context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Building")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Level 1")
    storey.Elevation = float(storey_elevation)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[building], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[storey], relating_object=building)

    def rect_profile(w, d):
        # web-ifc requires IfcProfileDef.Position — always set an origin placement (per massing.py).
        pos = model.create_entity("IfcAxis2Placement2D",
                                  Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0)),
                                  RefDirection=model.create_entity("IfcDirection", (1.0, 0.0)))
        return model.create_entity("IfcRectangleProfileDef", ProfileType="AREA", Position=pos,
                                   XDim=max(w, 1e-3), YDim=max(d, 1e-3))

    wall_n = 0
    for x1, y1, x2, y2, layer in plan["segments"]:
        length = math.hypot(x2 - x1, y2 - y1) or 1.0
        ang = math.atan2(y2 - y1, x2 - x1)
        c, s = math.cos(ang), math.sin(ang)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name=f"Wall {wall_n + 1}")
        m = np.array([[c, -s, 0, mx], [s, c, 0, my], [0, 0, 1, storey_elevation], [0, 0, 0, 1]], dtype=float)
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=wall, matrix=m)
        rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                   profile=rect_profile(length, wall_thickness), depth=wall_height)
        ifcopenshell.api.run("geometry.assign_representation", model, product=wall, representation=rep)
        ifcopenshell.api.run("spatial.assign_container", model, products=[wall], relating_structure=storey)
        ps = ifcopenshell.api.run("pset.add_pset", model, product=wall, name="Pset_WallCommon")
        ifcopenshell.api.run("pset.edit_pset", model, pset=ps,
                             properties={"IsExternal": False, "Reference": layer})
        wall_n += 1

    space_n = 0
    for room in plan["rooms"]:
        pts = room["points"]
        space = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSpace",
                                     name=f"Room {space_n + 1}")
        space.LongName = room.get("layer") or "Room"
        # arbitrary polygon profile in world XY (identity placement), extruded up by wall_height
        ifc_pts = [model.create_entity("IfcCartesianPoint", (float(x), float(y))) for x, y in pts]
        ifc_pts.append(ifc_pts[0])                     # close the loop
        polyline = model.create_entity("IfcPolyline", Points=ifc_pts)
        profile = model.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA",
                                      OuterCurve=polyline)
        m = np.eye(4); m[2, 3] = storey_elevation
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=space, matrix=m)
        rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                   profile=profile, depth=wall_height)
        ifcopenshell.api.run("geometry.assign_representation", model, product=space, representation=rep)
        ifcopenshell.api.run("aggregate.assign_object", model, products=[space], relating_object=storey)
        qto = ifcopenshell.api.run("pset.add_qto", model, product=space, name="Qto_SpaceBaseQuantities")
        ifcopenshell.api.run("pset.edit_qto", model, qto=qto,
                             properties={"NetFloorArea": room["area_m2"], "GrossFloorArea": room["area_m2"],
                                         "Height": wall_height,
                                         "NetVolume": round(room["area_m2"] * wall_height, 2)})
        space_n += 1

    model.write(out_path)
    return {**plan, "ifc_path": out_path, "wall_count": wall_n, "space_count": space_n,
            "wall_height_m": wall_height, "wall_thickness_m": wall_thickness}
