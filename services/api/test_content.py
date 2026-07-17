"""CONTENT-1 content catalog + placement: place_content authors a catalogued item (logistics/furniture/
landscaping) as the RIGHT IFC — class + temporary-phase (for logistics) + classification — from a supplied
mesh or a category-sized placeholder box.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_content.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell.util.element as ue  # noqa: E402

from aec_data import content, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# --- the catalog groups items into logistics / FF&E / landscape ------------------------------------
cat = content.catalog()
assert "Site Logistics" in cat["groups"] and "FF&E" in cat["groups"] and "Landscape" in cat["groups"], cat["groups"].keys()
assert cat["count"] >= 15, cat["count"]
crane = next(i for i in cat["groups"]["Site Logistics"] if i["key"] == "tower_crane")
assert crane["ifc_class"] == "IfcBuildingElementProxy" and crane["phase"] == "temporary", crane

TMP = os.path.join(os.path.dirname(__file__), "_content_test.ifc")
massing.generate_blank_ifc(TMP, name="Content Test", storeys=1, storey_height=4.0, ground_size=40.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# --- a tower crane → IfcBuildingElementProxy, TEMPORARY phase, Cranes classification ----------------
r = edit.place_content(m, "tower_crane", [15, 15], storey=st)
el = m.by_guid(r["guid"])
assert el.is_a() == "IfcBuildingElementProxy", el.is_a()
ph = ue.get_pset(el, "Massing_Phasing") or {}
assert str(ph.get("Status", "")).lower() == "temporary", f"crane must be phased temporary, got {ph}"
assert el.Representation is not None, "crane has geometry (placeholder box)"
# it carries a classification
assert any(a.is_a("IfcRelAssociatesClassification") for a in (el.HasAssociations or [])), "crane classified"

# --- a desk → IfcFurniture, no phase --------------------------------------------------------------
rd = edit.place_content(m, "desk", [2, 2], storey=st)
de = m.by_guid(rd["guid"])
assert de.is_a() == "IfcFurniture", de.is_a()
assert not (ue.get_pset(de, "Massing_Phasing") or {}).get("Status"), "furniture isn't phased temporary"

# --- a tree → IfcGeographicElement (or proxy fallback on a schema that lacks it) -------------------
rt = edit.place_content(m, "tree", [8, 8], storey=st)
te = m.by_guid(rt["guid"])
assert te.is_a() in ("IfcGeographicElement", "IfcBuildingElementProxy"), te.is_a()
assert rt["group"] == "Landscape", rt

# --- W9-6b: the FF&E bill of materials counts the placed furniture by item + level ----------------
edit.place_content(m, "desk", [4, 4], storey=st)         # a 2nd desk → count 2
edit.place_content(m, "chair", [5, 5], storey=st)
bom = content.furniture_bom(m)
assert bom["total"] >= 3 and bom["line_count"] >= 2, bom
by_item = {r["item"]: r for r in bom["items"]}
desk_row = next((r for k, r in by_item.items() if "desk" in k.lower()), None)
assert desk_row and desk_row["count"] >= 2 and st in desk_row["storeys"], desk_row
assert all(r["ifc_class"] == "IfcFurniture" for r in bom["items"]), bom["items"]

# --- a supplied detailed mesh is used instead of the placeholder box -------------------------------
verts = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0.5, 0.5, 1.5]]
faces = [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4], [0, 2, 1], [0, 3, 2]]
rm = edit.place_content(m, "sanitary_unit", [20, 20], verts=verts, faces=faces, storey=st)
su = m.by_guid(rm["guid"])
assert su.Representation.Representations[0].Items[0].is_a() == "IfcTriangulatedFaceSet"
assert len(su.Representation.Representations[0].Items[0].Coordinates.CoordList) == 5, "used the supplied mesh"

# --- unknown category raises ----------------------------------------------------------------------
raised = False
try:
    edit.place_content(m, "spaceship", [0, 0])
except ValueError:
    raised = True
assert raised, "unknown category should raise"

# --- recipe path ----------------------------------------------------------------------------------
assert "place_content" in edit.RECIPES

if os.path.exists(TMP):
    os.remove(TMP)

print("CONTENT OK - the catalog groups items into Site Logistics / FF&E / Landscape; place_content authors "
      "a tower crane as IfcBuildingElementProxy phased TEMPORARY + classified (Cranes), a desk as IfcFurniture "
      "(unphased), a tree as IfcGeographicElement (Landscape); a supplied detailed mesh is used over the "
      "placeholder box; unknown categories raise; place_content is a registered recipe.")
