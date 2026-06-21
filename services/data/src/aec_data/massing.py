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


def generate_ifc(metrics: dict, out_path: str, name: str = "Massing Study") -> str:
    """Write an IFC4 massing model: site → building → one storey + floor-plate space per level."""
    import ifcopenshell
    import ifcopenshell.api
    import numpy as np

    floors = int(metrics["floors"])
    fw, fd, f2f = float(metrics["plate_w"]), float(metrics["plate_d"]), float(metrics["floor_to_floor"])
    plate_area = round(fw * fd, 2)

    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name=name)
    ifcopenshell.api.run("unit.assign_unit", model)  # metric SI
    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", model, context_type="Model",
                                context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Building")
    ifcopenshell.api.run("aggregate.assign_object", model, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[building], relating_object=site)

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
        profile = model.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=fw, YDim=fd)
        rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                   profile=profile, depth=f2f)
        ifcopenshell.api.run("geometry.assign_representation", model, product=space, representation=rep)
        ifcopenshell.api.run("aggregate.assign_object", model, products=[space], relating_object=storey)
        qto = ifcopenshell.api.run("pset.add_qto", model, product=space, name="Qto_SpaceBaseQuantities")
        ifcopenshell.api.run("pset.edit_qto", model, qto=qto,
                             properties={"NetFloorArea": plate_area, "GrossFloorArea": plate_area,
                                         "NetVolume": round(plate_area * f2f, 2), "Height": f2f})
    model.write(out_path)
    return out_path
