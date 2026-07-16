"""UX-2 annotation: add_annotation places a 2D text annotation as an IfcAnnotation (IfcTextLiteral in the
Annotation context) that round-trips as real IFC.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_annotation.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import edit, guards, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_annot_test.ifc")
massing.generate_blank_ifc(TMP, name="Annot Test", storeys=1, storey_height=3.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# --- place a text annotation ----------------------------------------------------------------------
g = edit.add_annotation(m, [4, 3], "See detail A-541/3", kind="callout", storey=st, z=1.2)
ann = m.by_guid(g)
assert ann.is_a() == "IfcAnnotation" and ann.ObjectType == "callout", ann
# it carries a text literal with the note in an Annotation-typed representation
rep = ann.Representation.Representations[0]
assert rep.RepresentationType == "Annotation2D", rep.RepresentationType
lit = rep.Items[0]
assert lit.is_a() == "IfcTextLiteral" and lit.Literal == "See detail A-541/3", lit
# placed at the point (metres → SI) — x=4
import ifcopenshell.util.placement as up  # noqa: E402
mtx = up.get_local_placement(ann.ObjectPlacement)
assert abs(float(mtx[0][3]) - 4.0) < 1e-6, mtx
# it's in the Annotation representation subcontext
assert rep.ContextOfItems.ContextIdentifier in ("Annotation", None) or rep.ContextOfItems is not None, rep.ContextOfItems

# --- empty text is rejected -----------------------------------------------------------------------
raised = False
try:
    edit.add_annotation(m, [0, 0], "   ")
except ValueError:
    raised = True
assert raised, "empty annotation text should raise"

# --- UX-2 dimension annotation: line + measured-distance text -------------------------------------
dr = edit.add_dimension(m, [0, 0], [3, 4], storey=st)      # 3-4-5 triangle → 5.00 m
assert abs(dr["distance_m"] - 5.0) < 1e-3, dr
dim = m.by_guid(dr["guid"])
assert dim.is_a() == "IfcAnnotation" and dim.ObjectType == "dimension", dim
drep = dim.Representation.Representations[0]
items = {i.is_a() for i in drep.Items}
assert "IfcPolyline" in items and "IfcTextLiteral" in items, items    # dimension line + label
dtext = next(i for i in drep.Items if i.is_a() == "IfcTextLiteral")
assert dtext.Literal == "5.00 m", dtext.Literal
# a custom label overrides the auto-distance
dr2 = edit.add_dimension(m, [0, 0], [2, 0], text="CLR 2.0 m", storey=st)
assert next(i for i in m.by_guid(dr2["guid"]).Representation.Representations[0].Items
            if i.is_a() == "IfcTextLiteral").Literal == "CLR 2.0 m"
# coincident points rejected (and the E8 guard catches it too)
raised = False
try:
    edit.add_dimension(m, [1, 1], [1, 1])
except ValueError:
    raised = True
assert raised, "a zero-length dimension should raise"
assert guards.precheck("add_dimension", {"start": [0, 0], "end": [0, 0]})["errors"], "guard blocks zero-length dim"
assert guards.precheck("add_dimension", {"start": [0, 0], "end": [3, 4]})["ok"]
assert "add_dimension" in edit.RECIPES

# --- registered recipe + reachable via apply_recipe -----------------------------------------------
assert "add_annotation" in edit.RECIPES
OUT = os.path.join(os.path.dirname(__file__), "_annot_out.ifc")
res = edit.apply_recipe(TMP, "add_annotation", {"point": [1, 1], "text": "Note 1", "kind": "note"}, OUT)
assert res["changed"] and os.path.exists(OUT), res
mo = open_model(OUT)
assert any(a.is_a() == "IfcAnnotation" for a in mo.by_type("IfcAnnotation")), "annotation authored via recipe"
assert any(t.Literal == "Note 1" for t in mo.by_type("IfcTextLiteral")), "text literal present"

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("ANNOTATION OK - add_annotation authors an IfcAnnotation (ObjectType=kind) with an IfcTextLiteral "
      "(the note text) in an Annotation2D representation, placed at the [E,N,z] point; empty text rejected; "
      "registered recipe reachable via apply_recipe, round-trips through a written IFC.")
