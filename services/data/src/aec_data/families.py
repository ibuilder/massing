"""Starter IFC family/type library — so a generated (or uploaded) model can be furnished and
equipped with real, data-rich, GUID-stable BIM content (furniture, sanitary fixtures, appliances,
plants), not just spaces.

openBIM has no single great free family library and manufacturer content is Revit-first, so we
*generate* a small curated catalog parametrically (same approach as massing.py): each entry builds
an IfcTypeProduct with a mapped representation (a sized box at minimal fidelity) directly in the
target model's body context. `place_type` (edit.py) then instances occurrences via type.assign_type,
which maps the type geometry onto each placement — exactly the existing "place a family" path.

This is the *content* layer on top of the placement machinery; richer geometry / real manufacturer
IFC content can replace a builder later without changing the catalog contract or the placement flow.
"""
from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.api

# Each family: key, label, the IFC *type* class, an optional PredefinedType, a category for the
# picker, and [width, depth, height] in metres (the minimal box representation).
CATALOG: list[dict[str, Any]] = [
    # --- furniture (IfcFurnitureType) ---
    {"key": "desk", "label": "Desk", "ifc_class": "IfcFurnitureType", "predefined": "DESK",
     "category": "Furniture", "dims": [1.4, 0.7, 0.75]},
    {"key": "chair", "label": "Chair", "ifc_class": "IfcFurnitureType", "predefined": "CHAIR",
     "category": "Furniture", "dims": [0.5, 0.5, 0.9]},
    {"key": "table", "label": "Table", "ifc_class": "IfcFurnitureType", "predefined": "TABLE",
     "category": "Furniture", "dims": [1.6, 0.9, 0.74]},
    {"key": "sofa", "label": "Sofa", "ifc_class": "IfcFurnitureType", "predefined": "SOFA",
     "category": "Furniture", "dims": [2.1, 0.9, 0.85]},
    {"key": "bed", "label": "Bed (queen)", "ifc_class": "IfcFurnitureType", "predefined": "BED",
     "category": "Furniture", "dims": [1.6, 2.1, 0.6]},
    {"key": "shelf", "label": "Bookshelf", "ifc_class": "IfcFurnitureType", "predefined": "SHELF",
     "category": "Furniture", "dims": [0.9, 0.3, 1.8]},
    {"key": "wardrobe", "label": "Wardrobe", "ifc_class": "IfcFurnitureType", "predefined": None,
     "category": "Furniture", "dims": [1.2, 0.6, 2.0]},
    {"key": "nightstand", "label": "Nightstand", "ifc_class": "IfcFurnitureType", "predefined": None,
     "category": "Furniture", "dims": [0.5, 0.4, 0.55]},
    {"key": "filing_cabinet", "label": "Filing cabinet", "ifc_class": "IfcFurnitureType", "predefined": "FILECABINET",
     "category": "Furniture", "dims": [0.5, 0.6, 1.3]},
    {"key": "workstation", "label": "Office workstation", "ifc_class": "IfcFurnitureType", "predefined": "DESK",
     "category": "Furniture", "dims": [1.6, 1.6, 1.2]},
    {"key": "kitchen_counter", "label": "Kitchen counter", "ifc_class": "IfcFurnitureType", "predefined": None,
     "category": "Furniture", "dims": [2.4, 0.6, 0.9]},
    # --- sanitary (IfcSanitaryTerminalType) ---
    {"key": "toilet", "label": "Toilet", "ifc_class": "IfcSanitaryTerminalType", "predefined": "WCSEAT",
     "category": "Sanitary", "dims": [0.4, 0.7, 0.8]},
    {"key": "sink", "label": "Sink", "ifc_class": "IfcSanitaryTerminalType", "predefined": "SINK",
     "category": "Sanitary", "dims": [0.6, 0.5, 0.85]},
    {"key": "bathtub", "label": "Bathtub", "ifc_class": "IfcSanitaryTerminalType", "predefined": "BATH",
     "category": "Sanitary", "dims": [1.7, 0.75, 0.6]},
    {"key": "urinal", "label": "Urinal", "ifc_class": "IfcSanitaryTerminalType", "predefined": "URINAL",
     "category": "Sanitary", "dims": [0.4, 0.35, 0.6]},
    {"key": "shower", "label": "Shower", "ifc_class": "IfcSanitaryTerminalType", "predefined": "SHOWER",
     "category": "Sanitary", "dims": [0.9, 0.9, 2.1]},
    {"key": "washbasin", "label": "Wash-hand basin", "ifc_class": "IfcSanitaryTerminalType", "predefined": "WASHHANDBASIN",
     "category": "Sanitary", "dims": [0.55, 0.45, 0.85]},
    # --- appliances (IfcElectricApplianceType) ---
    {"key": "fridge", "label": "Refrigerator", "ifc_class": "IfcElectricApplianceType", "predefined": "REFRIGERATOR",
     "category": "Appliance", "dims": [0.7, 0.7, 1.8]},
    {"key": "range", "label": "Range / cooktop", "ifc_class": "IfcElectricApplianceType", "predefined": "KITCHENMACHINE",
     "category": "Appliance", "dims": [0.76, 0.66, 0.9]},
    {"key": "dishwasher", "label": "Dishwasher", "ifc_class": "IfcElectricApplianceType", "predefined": "DISHWASHER",
     "category": "Appliance", "dims": [0.6, 0.6, 0.85]},
    {"key": "washer", "label": "Washing machine", "ifc_class": "IfcElectricApplianceType", "predefined": "WASHINGMACHINE",
     "category": "Appliance", "dims": [0.6, 0.6, 0.85]},
    {"key": "oven", "label": "Oven", "ifc_class": "IfcElectricApplianceType", "predefined": "FREESTANDINGELECTRICHEATER",
     "category": "Appliance", "dims": [0.6, 0.6, 0.6]},
    {"key": "microwave", "label": "Microwave", "ifc_class": "IfcElectricApplianceType", "predefined": "FREESTANDINGELECTRICHEATER",
     "category": "Appliance", "dims": [0.5, 0.35, 0.3]},
    # --- lighting (IfcLightFixtureType) ---
    {"key": "pendant_light", "label": "Pendant light", "ifc_class": "IfcLightFixtureType", "predefined": "POINTSOURCE",
     "category": "Lighting", "dims": [0.3, 0.3, 0.4]},
    {"key": "recessed_light", "label": "Recessed downlight", "ifc_class": "IfcLightFixtureType", "predefined": "DIRECTIONSOURCE",
     "category": "Lighting", "dims": [0.6, 0.6, 0.1]},
    {"key": "floor_lamp", "label": "Floor lamp", "ifc_class": "IfcLightFixtureType", "predefined": "POINTSOURCE",
     "category": "Lighting", "dims": [0.4, 0.4, 1.6]},
    # --- MEP equipment (HVAC / electrical) ---
    {"key": "ahu", "label": "Air-handling unit", "ifc_class": "IfcUnitaryEquipmentType", "predefined": "AIRHANDLER",
     "category": "MEP", "dims": [2.0, 1.2, 1.8]},
    {"key": "fan_coil", "label": "Fan-coil unit", "ifc_class": "IfcUnitaryEquipmentType", "predefined": "AIRCONDITIONINGUNIT",
     "category": "MEP", "dims": [1.0, 0.6, 0.3]},
    {"key": "diffuser", "label": "Air diffuser", "ifc_class": "IfcAirTerminalType", "predefined": "DIFFUSER",
     "category": "MEP", "dims": [0.6, 0.6, 0.2]},
    {"key": "electrical_panel", "label": "Electrical panel", "ifc_class": "IfcElectricDistributionBoardType", "predefined": "DISTRIBUTIONBOARD",
     "category": "MEP", "dims": [0.6, 0.2, 0.9]},
    {"key": "water_heater", "label": "Water heater", "ifc_class": "IfcUnitaryEquipmentType", "predefined": None,
     "category": "MEP", "dims": [0.6, 0.6, 1.5]},
    # --- openings (IfcDoorType / IfcWindowType) ---
    {"key": "single_door", "label": "Single door", "ifc_class": "IfcDoorType", "predefined": "DOOR",
     "category": "Openings", "dims": [0.9, 0.05, 2.1]},
    {"key": "double_door", "label": "Double door", "ifc_class": "IfcDoorType", "predefined": "DOOR",
     "category": "Openings", "dims": [1.8, 0.05, 2.1]},
    {"key": "fixed_window", "label": "Fixed window", "ifc_class": "IfcWindowType", "predefined": "WINDOW",
     "category": "Openings", "dims": [1.2, 0.05, 1.5]},
    {"key": "sliding_window", "label": "Sliding window", "ifc_class": "IfcWindowType", "predefined": "WINDOW",
     "category": "Openings", "dims": [1.8, 0.05, 1.5]},
    # --- enclosure (IfcWallType / IfcCurtainWallType) ---
    {"key": "partition_wall", "label": "Interior partition", "ifc_class": "IfcWallType", "predefined": "PARTITIONING",
     "category": "Enclosure", "dims": [3.0, 0.12, 3.0]},
    {"key": "exterior_wall", "label": "Exterior wall", "ifc_class": "IfcWallType", "predefined": "SOLIDWALL",
     "category": "Enclosure", "dims": [3.0, 0.25, 3.5]},
    {"key": "curtain_wall", "label": "Curtain-wall panel", "ifc_class": "IfcCurtainWallType", "predefined": None,
     "category": "Enclosure", "dims": [1.5, 0.2, 3.5]},
    # --- structural members (IfcColumnType / IfcBeamType) ---
    {"key": "steel_column", "label": "Steel column", "ifc_class": "IfcColumnType", "predefined": "COLUMN",
     "category": "Structural", "dims": [0.3, 0.3, 3.5]},
    {"key": "steel_beam", "label": "Steel beam", "ifc_class": "IfcBeamType", "predefined": "BEAM",
     "category": "Structural", "dims": [0.2, 0.4, 6.0]},
    {"key": "concrete_column", "label": "Concrete column", "ifc_class": "IfcColumnType", "predefined": "COLUMN",
     "category": "Structural", "dims": [0.5, 0.5, 3.5]},
    {"key": "concrete_beam", "label": "Concrete beam", "ifc_class": "IfcBeamType", "predefined": "BEAM",
     "category": "Structural", "dims": [0.3, 0.6, 7.0]},
    # --- transport ---
    {"key": "elevator_cab", "label": "Elevator cab", "ifc_class": "IfcTransportElementType", "predefined": "ELEVATOR",
     "category": "Transport", "dims": [2.0, 2.4, 2.4]},
    # --- plants / vegetation (IfcGeographicElementType) ---
    {"key": "tree", "label": "Tree", "ifc_class": "IfcGeographicElementType", "predefined": "VEGETATION",
     "category": "Plant", "dims": [1.5, 1.5, 4.0]},
    {"key": "shrub", "label": "Shrub", "ifc_class": "IfcGeographicElementType", "predefined": "VEGETATION",
     "category": "Plant", "dims": [0.8, 0.8, 1.0]},
    {"key": "planter", "label": "Planter", "ifc_class": "IfcFurnitureType", "predefined": None,
     "category": "Plant", "dims": [0.6, 0.6, 0.7]},
]

_BY_KEY = {f["key"]: f for f in CATALOG}


def catalog() -> list[dict[str, Any]]:
    """Public picker catalog — key, label, class, category, dims (no geometry builders)."""
    return [{"key": f["key"], "label": f["label"], "ifc_class": f["ifc_class"],
             "category": f["category"], "dims": f["dims"]} for f in CATALOG]


def _set_predefined(typ, predefined: str | None) -> None:
    """Set PredefinedType when the entity supports it and the enum value is valid; otherwise skip."""
    if not predefined or not hasattr(typ, "PredefinedType"):
        return
    try:
        typ.PredefinedType = predefined
    except Exception:        # invalid enum for this schema — fall back to no predefined type
        pass


def _variant_name(label: str, dims) -> str:
    """A Revit-style type name: the base label, plus the size for a parametric variant so distinct
    sizes are distinct types (e.g. "Desk 1.8×0.8×0.75 m")."""
    w, d, h = (float(x) for x in dims)
    return f"{label} {w:g}×{d:g}×{h:g} m"


def ensure_type(model: ifcopenshell.file, key: str, dims=None):
    """Find-or-build the IfcTypeProduct for a catalog family in `model`. Deduped by (class, name) so
    re-placing the same family reuses one type. Passing `dims` ([w, d, h] m) builds a distinct,
    parametrically-sized **type variant** (named with its size) — Revit-style type families.
    Returns the type entity."""
    spec = _BY_KEY.get(key)
    if spec is None:
        raise ValueError(f"unknown family {key!r}; have {sorted(_BY_KEY)}")
    use_dims = [float(x) for x in dims] if dims else [float(x) for x in spec["dims"]]
    if len(use_dims) != 3 or any(v <= 0 for v in use_dims):
        raise ValueError(f"dims must be three positive [w, d, h] metres, got {dims!r}")
    name = spec["label"] if not dims else _variant_name(spec["label"], use_dims)

    existing = next((t for t in model.by_type(spec["ifc_class"])
                     if (getattr(t, "Name", None) or "") == name), None)
    if existing is not None:
        return existing

    typ = ifcopenshell.api.run("root.create_entity", model, ifc_class=spec["ifc_class"],
                               name=name)
    _set_predefined(typ, spec["predefined"])
    # a sized-box mapped representation → RepresentationMap; type.assign_type maps it onto every
    # occurrence we place. Shared with create_type so all our types carry an editable box solid.
    _assign_box_representation(model, typ, use_dims)
    return typ


# ─────────────────────────────────────────────────────────────────────────────
# W10-1 · first-class type/family system — custom types, type Psets, material sets,
# parametric dims edits that PROPAGATE to every occurrence (GUID-stable), and a type
# inspector. This deepens the ensure_type/place_type spine into a real family system.
# ─────────────────────────────────────────────────────────────────────────────

def _assign_box_representation(model: ifcopenshell.file, typ, dims) -> None:
    """Build a sized-box mapped representation (rectangle profile extruded to h) and assign it to a
    type — producing the RepresentationMap that place_type maps onto every occurrence. Shared by
    ensure_type and create_type so all our types carry an editable box solid."""
    import ifcopenshell.util.unit as uunit

    from .edit import _body_context  # lazy — avoid import cycle

    w, d, h = (float(x) for x in dims)
    scale = uunit.calculate_unit_scale(model)                # metres per file unit
    body = _body_context(model)
    if body is None:
        return
    pos = model.create_entity("IfcAxis2Placement2D",
                              Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0)),
                              RefDirection=model.create_entity("IfcDirection", (1.0, 0.0)))
    profile = model.create_entity("IfcRectangleProfileDef", ProfileType="AREA", Position=pos,
                                  XDim=w / scale, YDim=d / scale)
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                               profile=profile, depth=h)
    ifcopenshell.api.run("geometry.assign_representation", model, product=typ, representation=rep)


def _rep_solid(typ):
    """The rectangular IfcExtrudedAreaSolid inside a type's mapped body representation (or None).
    Mutating THIS in place changes every occurrence at once — occurrences share the RepresentationMap
    via IfcMappedItem, which is exactly how parametric type edits propagate GUID-stably."""
    for rm in (getattr(typ, "RepresentationMaps", None) or []):
        rep = getattr(rm, "MappedRepresentation", None)
        for it in (getattr(rep, "Items", None) or []):
            if it.is_a("IfcExtrudedAreaSolid") and it.SweptArea and \
                    it.SweptArea.is_a("IfcRectangleProfileDef"):
                return it
    return None


def _type_dims(typ):
    """Read back a box type's [w, d, h] in metres from its extruded-solid rep, or None."""
    import ifcopenshell.util.unit as uunit

    solid = _rep_solid(typ)
    if solid is None:
        return None
    scale = uunit.calculate_unit_scale(typ.file)           # metres per file unit, from the owning file
    return [round(float(solid.SweptArea.XDim) * scale, 4),
            round(float(solid.SweptArea.YDim) * scale, 4),
            round(float(solid.Depth) * scale, 4)]


def _find_type(model: ifcopenshell.file, type_guid: str):
    t = next((t for t in model.by_type("IfcTypeProduct") if t.GlobalId == type_guid), None)
    if t is None:
        raise ValueError(f"type {type_guid!r} not found")
    return t


def _apply_psets(model: ifcopenshell.file, product, psets) -> None:
    """Attach/merge type-level property sets: {pset_name: {prop: value}}. pset.add_pset is
    find-or-create, so re-applying the same pset name edits it rather than duplicating."""
    for pset_name, props in (psets or {}).items():
        if not props:
            continue
        pset = ifcopenshell.api.run("pset.add_pset", model, product=product, name=str(pset_name))
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset,
                             properties={str(k): v for k, v in props.items()})


def create_type(model: ifcopenshell.file, ifc_class: str, name: str, dims=None,
                predefined: str | None = None, psets=None) -> str:
    """W10-1: author a *custom* IfcTypeProduct ("family type") from scratch — any type class, an
    optional sized box representation ([w, d, h] m), an optional PredefinedType, and type-level
    property sets. Returns the new type's GUID. Deduped by (class, name): re-creating returns the
    existing type (and still applies psets), so it's idempotent."""
    if not ifc_class or not ifc_class.startswith("Ifc") or not ifc_class.endswith("Type"):
        raise ValueError(f"ifc_class must be an IfcXxxType, got {ifc_class!r}")
    name = (name or "").strip()
    if not name:
        raise ValueError("type name is required")
    existing = next((t for t in model.by_type(ifc_class)
                     if (getattr(t, "Name", None) or "") == name), None)
    if existing is not None:
        if psets:
            _apply_psets(model, existing, psets)
        return existing.GlobalId

    typ = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class, name=name)
    _set_predefined(typ, predefined)
    if dims:
        d = [float(x) for x in dims]
        if len(d) != 3 or any(v <= 0 for v in d):
            raise ValueError(f"dims must be three positive [w, d, h] metres, got {dims!r}")
        _assign_box_representation(model, typ, d)
    if psets:
        _apply_psets(model, typ, psets)
    return typ.GlobalId


def edit_type_params(model: ifcopenshell.file, type_guid: str, name: str | None = None,
                     dims=None, predefined: str | None = None, psets=None) -> dict:
    """W10-1: edit a type's parameters. Changing `dims` mutates the type's box solid IN PLACE, so
    the new size flows to **every placed occurrence at once** (they share the RepresentationMap) —
    GUID-stable, no re-placement. Also renames, re-stamps PredefinedType, and merges type Psets.
    Returns a summary of what changed."""
    import ifcopenshell.util.unit as uunit

    typ = _find_type(model, type_guid)
    changed: dict[str, Any] = {"guid": type_guid}
    if name and name.strip() and name.strip() != (getattr(typ, "Name", None) or ""):
        typ.Name = name.strip()
        changed["name"] = typ.Name
    if predefined is not None:
        _set_predefined(typ, predefined or None)
        changed["predefined"] = getattr(typ, "PredefinedType", None)
    if dims:
        d = [float(x) for x in dims]
        if len(d) != 3 or any(v <= 0 for v in d):
            raise ValueError(f"dims must be three positive [w, d, h] metres, got {dims!r}")
        solid = _rep_solid(typ)
        scale = uunit.calculate_unit_scale(model)
        if solid is not None:                              # mutate in place → propagates to occurrences
            w, dd, h = d
            solid.SweptArea.XDim = w / scale
            solid.SweptArea.YDim = dd / scale
            solid.Depth = h / scale
        else:                                              # no box solid yet — build one
            _assign_box_representation(model, typ, d)
        changed["dims"] = d
        changed["occurrences_updated"] = _occurrence_count(typ)
    if psets:
        _apply_psets(model, typ, psets)
        changed["psets"] = sorted(psets.keys())
    return changed


def assign_material_set(model: ifcopenshell.file, type_guid: str, layers) -> dict:
    """W10-1: give a type an IfcMaterialLayerSet — ordered [{material, thickness(m)}] layers
    (walls/slabs/roofs). Occurrences inherit the material through the type. Replaces any prior set."""
    typ = _find_type(model, type_guid)
    if not layers:
        raise ValueError("at least one material layer is required")

    # drop any existing material association so re-assigning is clean/idempotent
    for rel in list(getattr(typ, "HasAssociations", None) or []):
        if rel.is_a("IfcRelAssociatesMaterial"):
            ifcopenshell.api.run("material.unassign_material", model, products=[typ])
            break

    mset = ifcopenshell.api.run("material.add_material_set", model,
                                name=f"{typ.Name or typ.is_a()} assembly", set_type="IfcMaterialLayerSet")
    total = 0.0
    for spec in layers:
        mname = str(spec.get("material") or "Material").strip() or "Material"
        thick = float(spec.get("thickness") or 0.1)
        mat = next((m for m in model.by_type("IfcMaterial") if m.Name == mname), None) \
            or ifcopenshell.api.run("material.add_material", model, name=mname)
        layer = ifcopenshell.api.run("material.add_layer", model, layer_set=mset, material=mat)
        ifcopenshell.api.run("material.edit_layer", model, layer=layer,
                             attributes={"LayerThickness": thick, "Name": mname})
        total += thick
    ifcopenshell.api.run("material.assign_material", model, products=[typ], material=mset)
    return {"guid": type_guid, "layers": len(layers), "total_thickness_m": round(total, 4)}


def _occurrence_count(typ) -> int:
    """How many placed occurrences reference this type (via IfcRelDefinesByType)."""
    return sum(len(rel.RelatedObjects) for rel in (getattr(typ, "Types", None) or []))


def type_detail(model: ifcopenshell.file, type_guid: str) -> dict:
    """W10-1 inspector: everything about one type — class, predefined, box dims, type Psets,
    material layers, and its placed occurrences (capped list + count)."""
    import ifcopenshell.util.element as ue

    typ = _find_type(model, type_guid)
    occ: list[dict] = []
    for rel in (getattr(typ, "Types", None) or []):
        for o in rel.RelatedObjects:
            occ.append({"guid": o.GlobalId, "name": getattr(o, "Name", None) or o.is_a(),
                        "ifc_class": o.is_a()})
    materials: list[dict] = []
    mat = ue.get_material(typ)
    if mat is not None and mat.is_a("IfcMaterialLayerSet"):
        for lyr in (mat.MaterialLayers or []):
            materials.append({"material": getattr(lyr.Material, "Name", None) if lyr.Material else None,
                              "thickness": lyr.LayerThickness})
    elif mat is not None and mat.is_a("IfcMaterial"):
        materials.append({"material": mat.Name, "thickness": None})
    return {
        "guid": type_guid,
        "name": getattr(typ, "Name", None) or typ.is_a(),
        "ifc_class": typ.is_a(),
        "predefined": getattr(typ, "PredefinedType", None),
        "dims": _type_dims(typ),
        "has_geometry": bool(getattr(typ, "RepresentationMaps", None)),
        "psets": ue.get_psets(typ, psets_only=True),
        "materials": materials,
        "occurrence_count": len(occ),
        "occurrences": occ[:200],
    }


def add_family(model: ifcopenshell.file, key: str, storey: str | None = None,
               position=None, dims=None) -> str | None:
    """Find-or-build a family type (optionally a parametrically-sized `dims` variant), then place one
    occurrence (storey-contained, optionally at an [E, N] point in metres). Returns the new element's
    GUID. GUID-stable like all authoring."""
    from .edit import place_type  # lazy — avoid import cycle

    typ = ensure_type(model, key, dims)
    return place_type(model, typ.GlobalId, storey, position)


def import_types_from_ifc(model: ifcopenshell.file, source) -> list[dict[str, Any]]:
    """Import external IFC **type content** (manufacturer / 3rd-party families) into `model` so they
    become placeable like the built-in catalog. `source` is an ifcopenshell file, a path, or raw
    bytes. Every IfcTypeProduct in the source is copied in (with its geometry) via
    `project.append_asset`, deduped by (class, name) against what the target already has. Returns the
    imported types as [{guid, name, ifc_class}] — place them with the normal place_type flow.
    """
    import ifcopenshell.util.element  # noqa: F401  (ensures util is importable for append_asset)

    if isinstance(source, ifcopenshell.file):
        lib = source
    elif isinstance(source, (bytes, bytearray)):
        lib = ifcopenshell.file.from_string(bytes(source).decode("utf-8", "ignore"))
    else:
        lib = ifcopenshell.open(str(source))

    have = {(t.is_a(), (getattr(t, "Name", None) or "")) for t in model.by_type("IfcTypeProduct")}
    imported: list[dict[str, Any]] = []
    for typ in lib.by_type("IfcTypeProduct"):
        sig = (typ.is_a(), (getattr(typ, "Name", None) or ""))
        if not sig[1] or sig in have:                 # skip nameless or already-present types
            continue
        try:
            new = ifcopenshell.api.run("project.append_asset", model, library=lib, element=typ)
        except Exception:                             # noqa: BLE001 — incompatible/loose type, skip it
            continue
        have.add(sig)
        imported.append({"guid": new.GlobalId, "name": new.Name or sig[1], "ifc_class": new.is_a()})
    return imported


# --- FAMILY-DEPTH ① (R18): named type catalogs — one family, many cataloged sizes -------------------
# A catalog names the sizes a firm actually places ("Desk 1600 × 800") instead of raw dims; each
# resolves through the SAME ensure_type variant machinery (deduped, parametric), so a cataloged type
# and an ad-hoc dims variant are the same kind of IfcTypeProduct.
TYPE_CATALOGS: dict[str, list[dict[str, Any]]] = {
    "desk": [{"name": "1400 × 700", "dims": [1.4, 0.7, 0.75]},
             {"name": "1600 × 800", "dims": [1.6, 0.8, 0.75]},
             {"name": "1800 × 900", "dims": [1.8, 0.9, 0.75]}],
    "table": [{"name": "4-seat 1200", "dims": [1.2, 0.9, 0.74]},
              {"name": "6-seat 1800", "dims": [1.8, 0.9, 0.74]},
              {"name": "8-seat 2400", "dims": [2.4, 1.1, 0.74]}],
    "sofa": [{"name": "2-seat 1600", "dims": [1.6, 0.9, 0.85]},
             {"name": "3-seat 2100", "dims": [2.1, 0.9, 0.85]}],
    "bed": [{"name": "Single 900", "dims": [0.9, 2.0, 0.6]},
            {"name": "Queen 1600", "dims": [1.6, 2.1, 0.6]},
            {"name": "King 1800", "dims": [1.8, 2.1, 0.6]}],
    "wardrobe": [{"name": "2-door 1200", "dims": [1.2, 0.6, 2.0]},
                 {"name": "3-door 1800", "dims": [1.8, 0.6, 2.0]}],
    "kitchen_counter": [{"name": "Run 1800", "dims": [1.8, 0.6, 0.9]},
                        {"name": "Run 2400", "dims": [2.4, 0.6, 0.9]},
                        {"name": "Run 3000", "dims": [3.0, 0.6, 0.9]}],
    "bathtub": [{"name": "1500 compact", "dims": [1.5, 0.7, 0.6]},
                {"name": "1700 standard", "dims": [1.7, 0.75, 0.6]}],
    "shower": [{"name": "800 square", "dims": [0.8, 0.8, 2.1]},
               {"name": "900 square", "dims": [0.9, 0.9, 2.1]},
               {"name": "1200 walk-in", "dims": [1.2, 0.9, 2.1]}],
}


def catalog_types(key: str) -> list[dict[str, Any]]:
    """The named type catalog for a family — the curated sizes, or the base dims as 'Standard' when
    no catalog exists. Raises ValueError on an unknown family."""
    spec = _BY_KEY.get(key)
    if spec is None:
        raise ValueError(f"unknown family {key!r}; have {sorted(_BY_KEY)}")
    entries = TYPE_CATALOGS.get(key)
    if not entries:
        return [{"name": "Standard", "dims": list(spec["dims"])}]
    return [{"name": e["name"], "dims": list(e["dims"])} for e in entries]


def catalog_dims(key: str, type_name: str) -> list[float]:
    """Resolve a cataloged type name → its dims (case-insensitive). Raises ValueError with the
    available names so a typo comes back actionable."""
    entries = catalog_types(key)
    want = str(type_name or "").strip().lower()
    for e in entries:
        if e["name"].lower() == want:
            return e["dims"]
    raise ValueError(f"unknown type {type_name!r} for family {key!r}; "
                     f"catalog: {', '.join(e['name'] for e in entries)}")
