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


def compute_massing(p: dict) -> dict[str, Any]:
    """Zoning envelope → program. Inputs (metres): lot_width/lot_depth or lot_area, far,
    coverage_max, front/side/rear_setback, height_limit, floor_to_floor, efficiency, avg_unit_m2."""
    lot_w, lot_d = float(p.get("lot_width") or 0), float(p.get("lot_depth") or 0)
    lot_area = float(p.get("lot_area") or (lot_w * lot_d))
    if lot_area <= 0:
        raise ValueError("provide lot_area or lot_width × lot_depth")
    far = float(p.get("far", 1.0))
    coverage = float(p.get("coverage_max", 0.6))
    f2f = float(p.get("floor_to_floor", 3.5))
    ss, fs, rs = float(p.get("side_setback", 0)), float(p.get("front_setback", 0)), float(p.get("rear_setback", 0))
    height_limit = p.get("height_limit")

    if lot_w and lot_d:
        fw, fd = max(1.0, lot_w - 2 * ss), max(1.0, lot_d - fs - rs)
    else:
        side = math.sqrt(lot_area); fw = fd = max(1.0, side - 2 * ss)
    footprint = min(fw * fd, lot_area * coverage)
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
    }


def gridlines(extent: float, bay: float) -> list[float]:
    """Evenly-spaced grid line positions across `extent` (centred on 0) with spacing ≈ `bay` —
    columns land on both edges and the interior. Returns n+1 coordinates for n bays."""
    n = max(1, round(extent / max(0.5, bay)))
    step = extent / n
    return [round(-extent / 2 + i * step, 3) for i in range(n + 1)]


def generate_ifc(metrics: dict, out_path: str, name: str = "Massing Study",
                 frame: bool = False, bay: float = 7.5) -> str:
    """Write an IFC4 model: site → building → one storey + floor-plate space + slab per level.
    With `frame=True`, also generate a concrete structural frame on a ~`bay`-metre column grid —
    columns at every grid intersection (per floor) and beams along both axes — turning the massing
    into a real, GUID-stable structural model in one pass."""
    import ifcopenshell
    import ifcopenshell.api
    import numpy as np

    floors = int(metrics["floors"])
    fw, fd, f2f = float(metrics["plate_w"]), float(metrics["plate_d"]), float(metrics["floor_to_floor"])
    plate_area = round(fw * fd, 2)
    SLAB_T = 0.3   # m — thin floor plate per level: physical (renders) so the massing is visible
    #              (IfcSpace is forced transparent by the Fragments importer, so spaces alone show empty)
    COL, BEAM_W, BEAM_D = 0.6, 0.4, 0.6      # concrete column side, beam width, beam depth (m)

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

    gx = gridlines(fw, bay)
    gy = gridlines(fd, bay)
    for i in range(floors):
        elev = i * f2f
        storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey",
                                      name=f"Level {i + 1}")
        storey.Elevation = elev
        ifcopenshell.api.run("aggregate.assign_object", model, products=[storey], relating_object=building)
        space = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSpace",
                                     name=f"Level {i + 1} floor plate")
        space.LongName = f"Floor plate {i + 1}"
        matrix = np.eye(4); matrix[2, 3] = elev
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=space, matrix=matrix)
        profile = rect_profile(model, fw, fd)
        rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                   profile=profile, depth=f2f)
        ifcopenshell.api.run("geometry.assign_representation", model, product=space, representation=rep)
        ifcopenshell.api.run("aggregate.assign_object", model, products=[space], relating_object=storey)
        qto = ifcopenshell.api.run("pset.add_qto", model, product=space, name="Qto_SpaceBaseQuantities")
        ifcopenshell.api.run("pset.edit_qto", model, qto=qto,
                             properties={"NetFloorArea": plate_area, "GrossFloorArea": plate_area,
                                         "NetVolume": round(plate_area * f2f, 2), "Height": f2f})
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
    model.write(out_path)
    return out_path
