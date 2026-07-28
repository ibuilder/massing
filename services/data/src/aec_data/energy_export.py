"""ENERGY phase 1 (BIG-TICKET SPRINT A) — the **envelope export**: model → zones · surfaces ·
constructions → **gbXML** and **EnergyPlus IDF**.

Phase 1 deliberately ships no solver binaries. It de-risks the whole track by proving the hard
half — turning an IFC into a well-formed thermal model — with everything verifiable offline. Phase 2
runs EnergyPlus / Radiance through the durable job queue and parses results back onto the model.

What the export is, precisely:

* **Zones** — one per ``IfcSpace`` (area/volume from ``Qto_SpaceBaseQuantities``, falling back to
  geometry). A model with no spaces exports a single whole-building zone rather than nothing, and
  says which it did (``zone_source``).
* **Surfaces** — one planar surface per envelope element (wall · roof · slab · window · door).
  Energy models use **zero-thickness** surfaces, so a wall's mid-plane face is the correct
  representation, not an approximation. Each surface carries real corner coordinates and is tagged
  ``exact`` when the element's mesh IS its bounding box (true for authored rectangular extrusions —
  checked, not assumed) or ``bbox`` when the geometry is irregular and the box is a simplification.
  A consumer can therefore tell exactly how much to trust each polygon.
* **Constructions** — from the model's own ``IfcMaterialLayerSet`` assemblies via
  ``assembly_thermal`` (layer thickness ÷ design conductivity + surface films → U). Elements with
  no assembly fall back to a named default construction, counted in the report.

Both writers are pure text/XML over that one intermediate model, so gbXML and IDF can never
disagree about the building.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import ifcopenshell
import ifcopenshell.geom as geom
import numpy as np

from . import assembly_thermal
from .geomconf import bounded_iterator

# IFC class → (gbXML surfaceType, IDF surface type, IDF outside boundary condition)
_SURFACE_KINDS: dict[str, tuple[str, str, str]] = {
    "IfcWall": ("ExteriorWall", "Wall", "Outdoors"),
    "IfcWallStandardCase": ("ExteriorWall", "Wall", "Outdoors"),
    "IfcCurtainWall": ("ExteriorWall", "Wall", "Outdoors"),
    "IfcRoof": ("Roof", "Roof", "Outdoors"),
    "IfcSlab": ("InteriorFloor", "Floor", "Adiabatic"),
    "IfcWindow": ("FixedWindow", "Window", "Outdoors"),
    "IfcDoor": ("NonSlidingDoor", "Door", "Outdoors"),
}
_DEFAULT_U = {"Wall": 0.30, "Roof": 0.20, "Floor": 0.25, "Window": 1.80, "Door": 2.00}
_BOX_TOL = 1e-4          # metres — how close a vertex must sit to a bbox corner to count as "exact"


def _f(x: float) -> float:
    """Round to millimetres so two runs of the same model produce byte-identical files."""
    return round(float(x), 4)


def _is_box(verts: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> bool:
    """True when every vertex sits on a corner of the bounding box (an authored rectangular
    extrusion does; a swept/irregular mesh does not)."""
    uniq = np.unique(np.round(verts, 4), axis=0)
    if len(uniq) > 8:
        return False
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    return all(np.min(np.linalg.norm(corners - v, axis=1)) <= _BOX_TOL for v in uniq)


def _mid_plane_polygon(lo: np.ndarray, hi: np.ndarray) -> tuple[list[list[float]], str, float]:
    """The element's largest face, pulled to the element's mid-plane along its thinnest axis —
    the zero-thickness surface an energy model wants. Returns (corners, orientation, area)."""
    dims = hi - lo
    thin = int(np.argmin(dims))                     # the thickness axis
    mid = (lo[thin] + hi[thin]) / 2.0
    axes = [i for i in range(3) if i != thin]
    a, b = axes
    corners = []
    for ua, ub in ((lo[a], lo[b]), (hi[a], lo[b]), (hi[a], hi[b]), (lo[a], hi[b])):
        pt = [0.0, 0.0, 0.0]
        pt[thin], pt[a], pt[b] = mid, ua, ub
        corners.append([_f(pt[0]), _f(pt[1]), _f(pt[2])])
    orientation = "horizontal" if thin == 2 else "vertical"
    area = float(dims[a] * dims[b])
    return corners, orientation, area


def _layer_k(layer: dict) -> float:
    """k = thickness ÷ R for one analyzed layer — self-consistent with the platform's own R/U."""
    t = float(layer.get("thickness_m") or 0.0)
    r = float(layer.get("r_value") or 0.0)
    return _f(t / r) if t > 0 and r > 0 else 1.0


def _space_metrics(space) -> tuple[float, float]:
    import ifcopenshell.util.element as ue
    q = ue.get_pset(space, "Qto_SpaceBaseQuantities") or {}
    def num(*keys):
        for k in keys:
            v = q.get(k)
            try:
                if v is not None:
                    return float(v)
            except (TypeError, ValueError):
                continue
        return 0.0
    return num("NetFloorArea", "GrossFloorArea"), num("NetVolume", "GrossVolume")


def build(model: ifcopenshell.file) -> dict[str, Any]:
    """The intermediate thermal model both writers serialize: {zones, surfaces, constructions, …}."""
    import ifcopenshell.util.element as ue
    import ifcopenshell.util.unit as uunit

    scale = uunit.calculate_unit_scale(model)

    # --- constructions from the model's own layered assemblies -------------------------------------
    constructions: dict[str, dict[str, Any]] = {}
    guid_to_construction: dict[str, str] = {}
    try:
        thermal = assembly_thermal.from_model(model)
    except Exception:                                        # noqa: BLE001 — no assemblies is fine
        thermal = {"assemblies": []}
    for i, asm in enumerate(thermal.get("assemblies") or []):
        name = asm.get("name") or f"Assembly {i + 1}"
        constructions[name] = {
            "name": name, "u_value": asm.get("u_value"), "r_value": asm.get("r_value"),
            # conductivity is back-derived from the R this platform already computed for the layer
            # (k = thickness ÷ R), so the exported material reproduces OUR number rather than a
            # second, silently-different catalog lookup.
            "layers": [{"material": ly.get("material") or ly.get("name") or "Layer",
                        "thickness_m": _f(ly.get("thickness_m") or 0.0),
                        "conductivity": _layer_k(ly)}
                       for ly in (asm.get("layers") or [])],
            "source": "model",
        }
        for g in (asm.get("guids") or []):
            guid_to_construction[g] = name

    # --- zones -------------------------------------------------------------------------------------
    zones: list[dict[str, Any]] = []
    guid_to_zone: dict[str, str] = {}
    spaces = model.by_type("IfcSpace")
    storey_zone: dict[str, str] = {}
    if spaces:
        zone_source = "space"
        for sp in spaces:
            area, volume = _space_metrics(sp)
            zname = (getattr(sp, "LongName", None) or getattr(sp, "Name", None)
                     or f"Space {sp.GlobalId[:8]}")
            container = ue.get_container(sp)
            storey = getattr(container, "Name", None) or ""
            zones.append({"id": sp.GlobalId, "name": zname, "storey": storey,
                          "area_m2": _f(area), "volume_m3": _f(volume)})
            storey_zone.setdefault(storey, sp.GlobalId)
    else:
        zone_source = "whole_building"
        zones.append({"id": "ZONE-WHOLE-BUILDING", "name": "Whole building", "storey": "",
                      "area_m2": 0.0, "volume_m3": 0.0})

    # --- surfaces from real geometry ---------------------------------------------------------------
    surfaces: list[dict[str, Any]] = []
    default_construction_used: dict[str, int] = {}
    settings = geom.settings()
    it = bounded_iterator(geom, settings, model)
    if it.initialize():
        while True:
            shape = it.get()
            el = model.by_guid(shape.guid) if shape.guid else None
            cls = el.is_a() if el is not None else shape.type
            kind = _SURFACE_KINDS.get(cls)
            if kind is not None:
                verts = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3) * scale
                if verts.size:
                    lo, hi = verts.min(axis=0), verts.max(axis=0)
                    corners, orientation, area = _mid_plane_polygon(lo, hi)
                    gb_type, idf_type, boundary = kind
                    if idf_type in ("Wall", "Door", "Window") and orientation == "horizontal":
                        gb_type, idf_type = "Roof", "Roof"      # a flat "wall" is really a lid
                    if idf_type == "Floor" and orientation == "horizontal" and lo[2] <= 0.05:
                        gb_type, idf_type, boundary = "UndergroundSlab", "Floor", "Ground"
                    cname = guid_to_construction.get(shape.guid)
                    if not cname:
                        cname = f"Default {idf_type}"
                        default_construction_used[cname] = default_construction_used.get(cname, 0) + 1
                        constructions.setdefault(cname, {
                            "name": cname, "u_value": _DEFAULT_U.get(idf_type, 1.0), "r_value": None,
                            "layers": [{"material": f"{idf_type} default layer", "thickness_m": 0.2,
                                        "conductivity": 0.2 * _DEFAULT_U.get(idf_type, 1.0)}],
                            "source": "default"})
                    container = ue.get_container(el) if el is not None else None
                    storey = getattr(container, "Name", None) or ""
                    zone_id = storey_zone.get(storey) or zones[0]["id"]
                    guid_to_zone[shape.guid] = zone_id
                    surfaces.append({
                        "id": shape.guid, "name": (getattr(el, "Name", None) or cls),
                        "ifc_class": cls, "gbxml_type": gb_type, "idf_type": idf_type,
                        "boundary": boundary, "zone_id": zone_id, "construction": cname,
                        "orientation": orientation, "area_m2": _f(area),
                        "geometry": "exact" if _is_box(verts, lo, hi) else "bbox",
                        "corners": corners,
                    })
            if not it.next():
                break
    surfaces.sort(key=lambda s: (s["idf_type"], s["id"]))     # deterministic ordering

    exact = sum(1 for s in surfaces if s["geometry"] == "exact")
    return {
        "zones": zones, "zone_source": zone_source,
        "surfaces": surfaces,
        "constructions": [constructions[k] for k in sorted(constructions)],
        "counts": {"zones": len(zones), "surfaces": len(surfaces),
                   "constructions": len(constructions),
                   "surfaces_exact": exact, "surfaces_bbox": len(surfaces) - exact,
                   "default_constructions": sum(default_construction_used.values())},
        "note": ("zero-thickness mid-plane surfaces; 'exact' surfaces are authored rectangular "
                 "extrusions whose mesh IS its bounding box, 'bbox' ones are simplified"),
    }


# --- writers ----------------------------------------------------------------------------------------
def to_gbxml(model_or_built) -> str:
    """gbXML (v6.01 shape) — Campus / Building / Space / Surface + Construction / Layer / Material."""
    b = model_or_built if isinstance(model_or_built, dict) else build(model_or_built)
    root = ET.Element("gbXML", {
        "xmlns": "http://www.gbxml.org/schema", "temperatureUnit": "C", "lengthUnit": "Meters",
        "areaUnit": "SquareMeters", "volumeUnit": "CubicMeters", "useSIUnitsForResults": "true",
        "version": "6.01"})
    campus = ET.SubElement(root, "Campus", {"id": "campus-1"})
    location = ET.SubElement(campus, "Location")
    ET.SubElement(location, "Name").text = "Project site"
    ET.SubElement(location, "Elevation").text = "0"
    building = ET.SubElement(campus, "Building", {"id": "building-1", "buildingType": "Office"})
    ET.SubElement(building, "Name").text = "Building"
    ET.SubElement(building, "Area").text = str(_f(sum(z["area_m2"] for z in b["zones"])))
    for z in b["zones"]:
        sp = ET.SubElement(building, "Space", {"id": z["id"], "zoneIdRef": z["id"]})
        ET.SubElement(sp, "Name").text = z["name"]
        ET.SubElement(sp, "Area").text = str(z["area_m2"])
        ET.SubElement(sp, "Volume").text = str(z["volume_m3"])
    for s in b["surfaces"]:
        su = ET.SubElement(campus, "Surface", {
            "id": s["id"], "surfaceType": s["gbxml_type"], "constructionIdRef": s["construction"]})
        ET.SubElement(su, "Name").text = s["name"]
        ET.SubElement(su, "AdjacentSpaceId", {"spaceIdRef": s["zone_id"]})
        planar = ET.SubElement(su, "PlanarGeometry")
        loop = ET.SubElement(planar, "PolyLoop")
        for c in s["corners"]:
            pt = ET.SubElement(loop, "CartesianPoint")
            for v in c:
                ET.SubElement(pt, "Coordinate").text = str(v)
    for c in b["constructions"]:
        con = ET.SubElement(root, "Construction", {"id": c["name"]})
        if c.get("u_value") is not None:
            ET.SubElement(con, "U-value", {"unit": "WPerSquareMeterK"}).text = str(c["u_value"])
        ET.SubElement(con, "LayerId", {"layerIdRef": f"layer-{c['name']}"})
        ET.SubElement(con, "Name").text = c["name"]
        layer = ET.SubElement(root, "Layer", {"id": f"layer-{c['name']}"})
        for i, ly in enumerate(c["layers"]):
            mat_id = f"mat-{c['name']}-{i}"
            ET.SubElement(layer, "MaterialId", {"materialIdRef": mat_id})
            mat = ET.SubElement(root, "Material", {"id": mat_id})
            ET.SubElement(mat, "Name").text = ly["material"]
            ET.SubElement(mat, "Thickness", {"unit": "Meters"}).text = str(ly["thickness_m"])
            ET.SubElement(mat, "Conductivity", {"unit": "WPerMeterK"}).text = str(_f(ly["conductivity"]))
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def to_idf(model_or_built, version: str = "23.2") -> str:
    """EnergyPlus IDF — Building / Zone / Material / Construction / BuildingSurface:Detailed."""
    b = model_or_built if isinstance(model_or_built, dict) else build(model_or_built)
    out: list[str] = [
        "!- EnergyPlus envelope export (Massing ENERGY phase 1) — geometry + constructions only.",
        "!- No HVAC, schedules or loads: add them in the simulation setup.",
        f"Version,{version};",
        "",
        "Building,",
        "  Building,                !- Name",
        "  0.0,                     !- North Axis {deg}",
        "  City,                    !- Terrain",
        "  0.04,                    !- Loads Convergence Tolerance Value",
        "  0.4,                     !- Temperature Convergence Tolerance Value {deltaC}",
        "  FullExterior,            !- Solar Distribution",
        "  25;                      !- Maximum Number of Warmup Days",
        "",
        "GlobalGeometryRules,",
        "  UpperLeftCorner,         !- Starting Vertex Position",
        "  Counterclockwise,        !- Vertex Entry Direction",
        "  World;                   !- Coordinate System",
        "",
    ]
    for c in b["constructions"]:
        for i, ly in enumerate(c["layers"]):
            out += [
                "Material,",
                f"  {c['name']}-L{i},        !- Name",
                "  MediumRough,             !- Roughness",
                f"  {ly['thickness_m']},     !- Thickness {{m}}",
                f"  {_f(ly['conductivity'])},!- Conductivity {{W/m-K}}",
                "  800.0,                   !- Density {kg/m3}",
                "  900.0;                   !- Specific Heat {J/kg-K}",
                "",
            ]
        layer_names = ",\n".join(f"  {c['name']}-L{i}" for i in range(len(c["layers"])))
        out += ["Construction,", f"  {c['name']},", f"{layer_names};", ""]
    for z in b["zones"]:
        out += ["Zone,", f"  {z['name']},             !- Name",
                "  0, 0, 0, 0,              !- Direction of Relative North / Origin",
                "  1, 1;                    !- Type / Multiplier", ""]
    zone_name = {z["id"]: z["name"] for z in b["zones"]}
    for s in b["surfaces"]:
        verts = ",\n".join(f"  {c[0]}, {c[1]}, {c[2]}" for c in s["corners"])
        out += [
            "BuildingSurface:Detailed,",
            f"  {s['id']},               !- Name",
            f"  {s['idf_type']},         !- Surface Type",
            f"  {s['construction']},     !- Construction Name",
            f"  {zone_name.get(s['zone_id'], b['zones'][0]['name'])}, !- Zone Name",
            f"  {s['boundary']},         !- Outside Boundary Condition",
            "  ,                        !- Outside Boundary Condition Object",
            "  SunExposed,              !- Sun Exposure",
            "  WindExposed,             !- Wind Exposure",
            "  ,                        !- View Factor to Ground",
            f"  {len(s['corners'])},     !- Number of Vertices",
            f"{verts};",
            "",
        ]
    return "\n".join(out)


def export_file(ifc_path: str, fmt: str = "gbxml") -> str:
    from .ifc_loader import open_model
    built = build(open_model(ifc_path))
    return to_gbxml(built) if str(fmt).lower() == "gbxml" else to_idf(built)
