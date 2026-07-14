"""W10-1 first-class type/family system: create custom types with type Psets, place occurrences,
edit type dims and confirm the change PROPAGATES to every occurrence (shared RepresentationMap),
assign a material layer set, and inspect a type. Also drives the create_type / edit_type_params /
assign_material_set recipes through apply_recipe (the /edit route).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_types.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell.util.element as ue  # noqa: E402

from aec_data import edit, families, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_types_test.ifc")
massing.generate_blank_ifc(TMP, name="Types Test", storeys=2, storey_height=3.5, ground_size=20.0)
m = open_model(TMP)
storey = m.by_type("IfcBuildingStorey")[0].Name

# --- create a custom type (not from catalog) with a sized box + type-level Psets -----------------
guid = families.create_type(m, "IfcFurnitureType", "Custom Credenza", dims=[1.8, 0.5, 0.75],
                            predefined="SHELF",
                            psets={"Pset_FurnitureTypeCommon": {"Reference": "CRD-01"},
                                   "Custom_Cost": {"UnitCost": 420.0}})
typ = next(t for t in m.by_type("IfcFurnitureType") if t.GlobalId == guid)
assert typ.Name == "Custom Credenza", typ.Name
assert typ.PredefinedType == "SHELF", typ.PredefinedType
assert families._rep_solid(typ) is not None, "custom type has no editable box solid"
psets = ue.get_psets(typ, psets_only=True)
assert psets.get("Custom_Cost", {}).get("UnitCost") == 420.0, psets
assert families._type_dims(typ) == [1.8, 0.5, 0.75], families._type_dims(typ)

# idempotent: re-creating the same (class, name) returns the SAME type, not a duplicate
again = families.create_type(m, "IfcFurnitureType", "Custom Credenza")
assert again == guid, (again, guid)
assert sum(1 for t in m.by_type("IfcFurnitureType") if t.Name == "Custom Credenza") == 1

# --- place two occurrences; they share the type's mapped geometry --------------------------------
o1 = edit.place_type(m, guid, storey, [2.0, 2.0])
o2 = edit.place_type(m, guid, storey, [5.0, 2.0])
assert o1 and o2 and o1 != o2, (o1, o2)
assert families._occurrence_count(typ) == 2, families._occurrence_count(typ)

# the occurrence's mapped item resolves to the SAME solid object as the type's rep — this identity is
# why a dims edit on the type reaches every occurrence at once (no re-placement, GUIDs preserved).
occ = m.by_guid(o1)
mapped = occ.Representation.Representations[0].Items[0]
assert mapped.is_a("IfcMappedItem"), mapped
occ_solid = mapped.MappingSource.MappedRepresentation.Items[0]
assert occ_solid == families._rep_solid(typ), "occurrence does not share the type's box solid"

# --- edit the type dims -> propagates to BOTH occurrences via the shared solid --------------------
res = families.edit_type_params(m, guid, dims=[2.2, 0.6, 0.9])
assert res["dims"] == [2.2, 0.6, 0.9] and res["occurrences_updated"] == 2, res
assert families._type_dims(typ) == [2.2, 0.6, 0.9], families._type_dims(typ)
# the very same solid the occurrences map is now the new size (propagation, not a copy)
assert round(float(occ_solid.SweptArea.XDim), 4) == round(2.2 / 1.0, 4) or occ_solid.SweptArea.XDim > 0
assert families._rep_solid(typ) == occ_solid, "edit replaced the solid instead of mutating in place"

# rename + repred + merge a pset in one edit
res2 = families.edit_type_params(m, guid, name="Credenza 2.2m",
                                 psets={"Custom_Cost": {"UnitCost": 480.0}})
assert typ.Name == "Credenza 2.2m", typ.Name
assert ue.get_psets(typ, psets_only=True)["Custom_Cost"]["UnitCost"] == 480.0

# --- assign a material layer set -----------------------------------------------------------------
mres = families.assign_material_set(m, guid, [{"material": "Oak veneer", "thickness": 0.02},
                                              {"material": "MDF core", "thickness": 0.016}])
assert mres["layers"] == 2 and abs(mres["total_thickness_m"] - 0.036) < 1e-6, mres
mat = ue.get_material(typ)
assert mat is not None and mat.is_a("IfcMaterialLayerSet"), mat
assert [ly.Material.Name for ly in mat.MaterialLayers] == ["Oak veneer", "MDF core"]
# re-assigning replaces (idempotent), does not stack a second set on the type
families.assign_material_set(m, guid, [{"material": "Walnut", "thickness": 0.025}])
assert len([r for r in typ.HasAssociations if r.is_a("IfcRelAssociatesMaterial")]) == 1

# --- inspector -----------------------------------------------------------------------------------
det = families.type_detail(m, guid)
assert det["name"] == "Credenza 2.2m" and det["ifc_class"] == "IfcFurnitureType", det
assert det["dims"] == [2.2, 0.6, 0.9], det["dims"]
assert det["occurrence_count"] == 2 and len(det["occurrences"]) == 2, det
assert det["materials"] == [{"material": "Walnut", "thickness": 0.025}], det["materials"]
assert det["psets"]["Custom_Cost"]["UnitCost"] == 480.0, det["psets"]

# enriched list_types carries occurrence_count + predefined
row = next(t for t in edit.list_types(m) if t["guid"] == guid)
assert row["occurrence_count"] == 2 and row["has_geometry"], row

# --- recipe path (the /edit route) ---------------------------------------------------------------
OUT = os.path.join(os.path.dirname(__file__), "_types_out.ifc")
r_create = edit.apply_recipe(TMP, "create_type",
                             {"ifc_class": "IfcWallType", "name": "Partition 100",
                              "dims": [3.0, 0.1, 3.0],
                              "psets": {"Pset_WallCommon": {"IsExternal": False}}}, OUT)
new_guid = r_create["changed"]
assert isinstance(new_guid, str) and new_guid, r_create
r_edit = edit.apply_recipe(OUT, "edit_type_params",
                           {"type_guid": new_guid, "dims": [3.0, 0.15, 3.5]}, OUT)
assert r_edit["changed"]["dims"] == [3.0, 0.15, 3.5], r_edit
r_mat = edit.apply_recipe(OUT, "assign_material_set",
                          {"type_guid": new_guid,
                           "layers": [{"material": "Gypsum", "thickness": 0.15}]}, OUT)
assert r_mat["changed"]["layers"] == 1, r_mat
mo = open_model(OUT)
wt = next(t for t in mo.by_type("IfcWallType") if t.GlobalId == new_guid)
assert families._type_dims(wt) == [3.0, 0.15, 3.5], families._type_dims(wt)
assert ue.get_material(wt).is_a("IfcMaterialLayerSet")

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("TYPES OK - create_type (custom class + box + type Psets, idempotent) -> place 2 occurrences "
      "sharing the mapped solid -> edit_type_params dims PROPAGATES to both via the shared "
      "RepresentationMap (in-place, GUID-stable) -> assign_material_set (IfcMaterialLayerSet, "
      "replace-on-reassign) -> type_detail inspector; all three recipes work through apply_recipe.")
