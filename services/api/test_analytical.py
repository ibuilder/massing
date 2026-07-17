"""W10-7 structural analytical model: derive an IfcStructuralAnalysisModel (curve members + shared point
connections + a gravity load case) from the physical frame, idempotently, and read it back.
Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_analytical.py"""
import os
import sys
import tempfile

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import analytical, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(tempfile.gettempdir(), "_analytical_test.ifc")
massing.generate_blank_ifc(TMP, name="Analytical Test", storeys=1, storey_height=4.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# a portal frame: two columns + a beam tying their bases (beam 0,0->6,0 shares the two column base nodes)
edit.add_column(m, [0, 0], 4.0, 0.4, 0.4, st)
edit.add_column(m, [6, 0], 4.0, 0.4, 0.4, st)
edit.add_beam(m, [0, 0], [6, 0], 0.3, 0.5, st)

# --- derive the analytical model ---------------------------------------------------------------------
r = analytical.derive_analytical(m)
# 3 physical frame members -> 3 curve members; 4 distinct endpoints -> 4 shared point-connection nodes
assert r["curve_members"] == 3 and r["nodes"] == 4, r
assert r["load_case"] and r["load_group"], r
assert len(m.by_type("IfcStructuralAnalysisModel")) == 1, "one analysis model"
assert len(m.by_type("IfcStructuralCurveMember")) == 3, m.by_type("IfcStructuralCurveMember")
assert len(m.by_type("IfcStructuralPointConnection")) == 4, "column bases/tops + beam ends dedupe to 4"
# each curve member connects to two nodes -> 3 members x 2 = 6 member-connection rels
assert len(m.by_type("IfcRelConnectsStructuralMember")) == 6, m.by_type("IfcRelConnectsStructuralMember")
# analytical members link back to the physical elements they idealise (IfcRelAssignsToProduct)
assert len(m.by_type("IfcRelAssignsToProduct")) == 3, "analytical<->physical product links"
# no orphaned topology: one edge per curve member, one vertex per node
assert len(m.by_type("IfcEdge")) == 3 and len(m.by_type("IfcVertexPoint")) == 4, "clean topology"

# --- idempotent re-derive: a rebuild refreshes, it does not accumulate --------------------------------
analytical.derive_analytical(m)
assert len(m.by_type("IfcStructuralAnalysisModel")) == 1, "re-derive must not stack analysis models"
assert len(m.by_type("IfcStructuralCurveMember")) == 3, "re-derive must not stack curve members"
assert len(m.by_type("IfcStructuralPointConnection")) == 4, "re-derive must not stack nodes"
assert len(m.by_type("IfcEdge")) == 3, "re-derive must not orphan topology"

# --- summary reads it back (survives a serialize round-trip) ------------------------------------------
OUT = os.path.join(tempfile.gettempdir(), "_analytical_out.ifc")
m.write(OUT)
s = analytical.summary(open_model(OUT))
assert s["has_model"] and s["curve_members"] == 3 and s["point_connections"] == 4, s
assert s["analysis_models"][0]["predefined_type"] == "LOADING_3D", s["analysis_models"]
assert "Dead load (self weight)" in s["load_cases"], s["load_cases"]

# --- the recipe path (apply_recipe) authors + publishes the same analytical model --------------------
massing.generate_blank_ifc(TMP, name="Recipe Frame", storeys=1, storey_height=3.0, ground_size=10.0)
m2 = open_model(TMP)
st2 = m2.by_type("IfcBuildingStorey")[0].Name
edit.add_column(m2, [0, 0], 3.0, 0.4, 0.4, st2)
m2.write(TMP)
res = edit.apply_recipe(TMP, "derive_analytical", {"name": "Frame A"}, OUT)["changed"]
assert res["curve_members"] == 1 and res["nodes"] == 2, res
assert "derive_analytical" in edit.RECIPES
sr = analytical.summary(open_model(OUT))
assert sr["analysis_models"][0]["name"] == "Frame A", sr["analysis_models"]

# --- empty model: no frame -> a valid (empty) analytical model, no crash ------------------------------
massing.generate_blank_ifc(TMP, name="Empty", storeys=1, storey_height=3.0, ground_size=10.0)
me = open_model(TMP)
re_ = analytical.derive_analytical(me)
assert re_["curve_members"] == 0 and re_["nodes"] == 0, re_
assert len(me.by_type("IfcStructuralAnalysisModel")) == 1, "still authors the (empty) analysis model"

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("ANALYTICAL OK - derive_analytical builds an IfcStructuralAnalysisModel from the physical frame: "
      "columns/beams -> 3 IfcStructuralCurveMember (IfcEdge topology) tied at 4 shared "
      "IfcStructuralPointConnection nodes (6 member-connection rels), each linked back to its physical "
      "element (IfcRelAssignsToProduct), plus a permanent-G self-weight load case/group; re-derive is "
      "idempotent (no accumulation, no orphan topology); summary reads it back through a serialize "
      "round-trip; the derive_analytical recipe publishes it; an empty frame yields an empty-but-valid model.")
