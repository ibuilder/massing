"""W11 F0 spine: ensure the view-keyed representation context tree (Model + Plan roots; Body/Axis/Box/
Annotation/FootPrint subcontexts) and tag elements with a LOD stage (Pset_MassingLOD.Stage). Both are the
foundation for LOD dialing + drawing generation.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_representations.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell.util.element as ue  # noqa: E402

from aec_data import edit, massing  # noqa: E402
from aec_data import representations as rep
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_rep_test.ifc")
massing.generate_blank_ifc(TMP, name="Rep Test", storeys=1, storey_height=3.5, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
w1 = edit.add_wall(m, [0, 0], [5, 0], 3.0, 0.2, st)
w2 = edit.add_wall(m, [5, 0], [5, 5], 3.0, 0.2, st)

# --- ensure_contexts: creates the Plan root + subcontexts (Model/Body already exists) ---------------
r = rep.ensure_contexts(m)
assert "Model" in r["roots"] and "Plan" in r["roots"], r
# the Plan root now exists
plan_roots = [c for c in m.by_type("IfcGeometricRepresentationContext")
              if not c.is_a("IfcGeometricRepresentationSubContext") and (c.ContextType or "") == "Plan"]
assert len(plan_roots) == 1, plan_roots
# all six expected subcontexts are present, keyed by (identifier, target_view)
subs = {(c.ContextIdentifier, c.TargetView) for c in m.by_type("IfcGeometricRepresentationSubContext")}
for ident, tview in [("Body", "MODEL_VIEW"), ("Axis", "GRAPH_VIEW"), ("Box", "MODEL_VIEW"),
                     ("Body", "PLAN_VIEW"), ("Annotation", "PLAN_VIEW"), ("FootPrint", "PLAN_VIEW")]:
    assert (ident, tview) in subs, (ident, tview, subs)

# idempotent: a second run creates nothing new
n_ctx_before = len(m.by_type("IfcGeometricRepresentationContext"))
r2 = rep.ensure_contexts(m)
assert r2["created"] == 0, r2
assert len(m.by_type("IfcGeometricRepresentationContext")) == n_ctx_before, "ensure_contexts not idempotent"

# --- LOD stage tagging ------------------------------------------------------------------------------
s0 = rep.lod_summary(m)
assert s0["counts"]["UNSET"] == s0["total"] and s0["staged"] == 0, s0

assert rep.set_lod(m, [w1], "200") == 1
assert rep.set_lod(m, [w2], "400") == 1
assert ue.get_pset(m.by_guid(w1), "Pset_MassingLOD")["Stage"] == "200"
assert ue.get_pset(m.by_guid(w2), "Pset_MassingLOD")["Stage"] == "400"

s1 = rep.lod_summary(m)
assert s1["counts"]["200"] == 1 and s1["counts"]["400"] == 1 and s1["staged"] == 2, s1
assert s1["prop"] == "Pset_MassingLOD.Stage"

# advancing LOD updates in place (no duplicate pset) — GUID-stable
assert rep.set_lod(m, [w1], "350") == 1
assert ue.get_pset(m.by_guid(w1), "Pset_MassingLOD")["Stage"] == "350"
assert sum(1 for rr in (m.by_guid(w1).IsDefinedBy or [])
           if rr.is_a("IfcRelDefinesByProperties")
           and rr.RelatingPropertyDefinition.Name == "Pset_MassingLOD") == 1, "duplicate LOD pset"

# invalid stage rejected; stale GUID skipped
try:
    rep.set_lod(m, [w1], "999")
    raised = False
except ValueError:
    raised = True
assert raised, "invalid LOD stage should raise"
assert rep.set_lod(m, [w1, "NOTAGUID000000000000000"], "300") == 1

# --- recipe path (the /edit route). NB: open_model is lru_cached, so a FRESH file is needed to prove
# ensure_contexts creates contexts via apply_recipe (re-opening TMP returns the already-ensured object).
TMP2 = os.path.join(os.path.dirname(__file__), "_rep_test2.ifc")
massing.generate_blank_ifc(TMP2, name="Rep Test 2", storeys=1, storey_height=3.5, ground_size=20.0)
OUT = os.path.join(os.path.dirname(__file__), "_rep_out.ifc")
rc = edit.apply_recipe(TMP2, "ensure_contexts", {}, OUT)
assert rc["changed"]["created"] >= 1, rc                    # Plan subcontexts newly created
m2 = open_model(TMP2)
gw = edit.add_wall(m2, [0, 0], [4, 0], 3.0, 0.2, m2.by_type("IfcBuildingStorey")[0].Name)
m2.write(OUT)
rl = edit.apply_recipe(OUT, "set_lod", {"guids": [gw], "stage": "300"}, OUT)
assert rl["changed"] == 1, rl
mo = open_model(OUT)
assert ue.get_pset(mo.by_guid(gw), "Pset_MassingLOD")["Stage"] == "300"

for f in (TMP, TMP2, OUT):
    if os.path.exists(f):
        os.remove(f)

print("REPRESENTATIONS OK - ensure_contexts builds the view-keyed context tree (Model+Plan roots; "
      "Body/Axis/Box/Annotation/FootPrint subcontexts by TargetView), idempotent; set_lod stamps "
      "Pset_MassingLOD.Stage (100-500) GUID-stable, advances in place (no dup pset), rejects bad "
      "stages, skips stale GUIDs; lod_summary counts by stage; both work via apply_recipe.")
