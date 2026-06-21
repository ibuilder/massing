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
    # --- sanitary (IfcSanitaryTerminalType) ---
    {"key": "toilet", "label": "Toilet", "ifc_class": "IfcSanitaryTerminalType", "predefined": "WCSEAT",
     "category": "Sanitary", "dims": [0.4, 0.7, 0.8]},
    {"key": "sink", "label": "Sink", "ifc_class": "IfcSanitaryTerminalType", "predefined": "SINK",
     "category": "Sanitary", "dims": [0.6, 0.5, 0.85]},
    {"key": "bathtub", "label": "Bathtub", "ifc_class": "IfcSanitaryTerminalType", "predefined": "BATH",
     "category": "Sanitary", "dims": [1.7, 0.75, 0.6]},
    # --- appliances (IfcElectricApplianceType) ---
    {"key": "fridge", "label": "Refrigerator", "ifc_class": "IfcElectricApplianceType", "predefined": "REFRIGERATOR",
     "category": "Appliance", "dims": [0.7, 0.7, 1.8]},
    {"key": "range", "label": "Range / cooktop", "ifc_class": "IfcElectricApplianceType", "predefined": "KITCHENMACHINE",
     "category": "Appliance", "dims": [0.76, 0.66, 0.9]},
    {"key": "dishwasher", "label": "Dishwasher", "ifc_class": "IfcElectricApplianceType", "predefined": "DISHWASHER",
     "category": "Appliance", "dims": [0.6, 0.6, 0.85]},
    {"key": "washer", "label": "Washing machine", "ifc_class": "IfcElectricApplianceType", "predefined": "WASHINGMACHINE",
     "category": "Appliance", "dims": [0.6, 0.6, 0.85]},
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


def ensure_type(model: ifcopenshell.file, key: str):
    """Find-or-build the IfcTypeProduct for a catalog family in `model`. Deduped by (class, label)
    so re-placing the same family reuses one type. Returns the type entity."""
    from .edit import _body_context  # lazy — avoid import cycle (edit references families in RECIPES)

    spec = _BY_KEY.get(key)
    if spec is None:
        raise ValueError(f"unknown family {key!r}; have {sorted(_BY_KEY)}")
    existing = next((t for t in model.by_type(spec["ifc_class"])
                     if (getattr(t, "Name", None) or "") == spec["label"]), None)
    if existing is not None:
        return existing
    import ifcopenshell.util.unit as uunit

    typ = ifcopenshell.api.run("root.create_entity", model, ifc_class=spec["ifc_class"],
                               name=spec["label"])
    _set_predefined(typ, spec["predefined"])
    w, d, h = (float(x) for x in spec["dims"])           # dims are in metres
    scale = uunit.calculate_unit_scale(model)            # metres per file unit
    body = _body_context(model)
    if body is not None:
        # profile dims are stored in file units (not auto-converted), so divide by scale;
        # the extrusion `depth` IS converted by add_profile_representation, so keep it in metres.
        # Position is REQUIRED by web-ifc (null Position → element skipped → invisible in the viewer).
        pos = model.create_entity("IfcAxis2Placement2D",
                                  Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0)),
                                  RefDirection=model.create_entity("IfcDirection", (1.0, 0.0)))
        profile = model.create_entity("IfcRectangleProfileDef", ProfileType="AREA", Position=pos,
                                      XDim=w / scale, YDim=d / scale)
        rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                                   profile=profile, depth=h)
        # assigning a representation to a *type* produces a RepresentationMap (mapped geometry),
        # which type.assign_type then maps onto every occurrence we place.
        ifcopenshell.api.run("geometry.assign_representation", model, product=typ, representation=rep)
    return typ


def add_family(model: ifcopenshell.file, key: str, storey: str | None = None,
               position=None) -> str | None:
    """Find-or-build a family type, then place one occurrence (storey-contained, optionally at an
    [E, N] point in metres). Returns the new element's GUID. GUID-stable like all authoring."""
    from .edit import place_type  # lazy — avoid import cycle

    typ = ensure_type(model, key)
    return place_type(model, typ.GlobalId, storey, position)
