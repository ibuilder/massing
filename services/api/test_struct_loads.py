"""STRUCT-LOADS-IFC: write per-member gravity load actions onto the analytical model so it is a loaded,
solver-ready IFC (IfcStructuralLinearAction + IfcStructuralLoadLinearForce, grouped) — idempotent, and
cleaned by a re-derive. Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_struct_loads.py"""
import os
import sys
import tempfile

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import analytical, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(tempfile.gettempdir(), "_struct_loads_test.ifc")
massing.generate_blank_ifc(TMP, name="Loads", storeys=1, storey_height=4.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_column(m, [0, 0], 4.0, 0.4, 0.4, st)
edit.add_column(m, [6, 0], 4.0, 0.4, 0.4, st)
edit.add_beam(m, [0, 0], [6, 0], 0.3, 0.5, st)
analytical.derive_analytical(m)
n_members = len(m.by_type("IfcStructuralCurveMember"))
assert n_members == 3, n_members

# --- apply loads: one linear action per curve member ------------------------------------------------
r = analytical.apply_member_loads(m, dead_klf=1.0, live_klf=0.5)
assert r["applied"] == 3 and r["members"] == 3, r
# 1.5 kip/ft × 14593.9 N/m per kip/ft = 21890.86 N/m, applied downward (−Z)
assert abs(r["line_load_N_per_m"] - 21890.9) < 0.5, r["line_load_N_per_m"]
acts = m.by_type("IfcStructuralLinearAction")
assert len(acts) == 3, len(acts)
assert len(m.by_type("IfcStructuralLoadLinearForce")) == 3, "one applied load per action"
assert len(m.by_type("IfcRelConnectsStructuralActivity")) == 3, "each action connects to its member"
for a in acts:
    assert a.AppliedLoad.is_a("IfcStructuralLoadLinearForce")
    assert a.AppliedLoad.LinearForceZ < 0, "gravity acts in global −Z"
    assert abs(a.AppliedLoad.LinearForceZ + 21890.9) < 0.5, a.AppliedLoad.LinearForceZ
# actions are grouped under a load group
grp_rels = [rel for rel in m.by_type("IfcRelAssignsToGroup")
            if getattr(rel, "RelatingGroup", None) and rel.RelatingGroup.is_a("IfcStructuralLoadGroup")]
assert grp_rels, "actions assigned to a load group"

# --- idempotent: re-applying refreshes, does not accumulate -----------------------------------------
before = {t: len(m.by_type(t)) for t in ("IfcStructuralLinearAction", "IfcStructuralLoadLinearForce",
                                         "IfcRelConnectsStructuralActivity")}
analytical.apply_member_loads(m, dead_klf=2.0, live_klf=1.0)     # different load
after = {t: len(m.by_type(t)) for t in before}
assert after == before, {"before": before, "after": after}      # counts unchanged (no accumulation)
# the refreshed value reflects the new 3.0 kip/ft
assert abs(m.by_type("IfcStructuralLinearAction")[0].AppliedLoad.LinearForceZ + 3.0 * 14593.9) < 1.0

# summary reports the loaded state (survives a serialize round-trip)
OUT = os.path.join(tempfile.gettempdir(), "_struct_loads_out.ifc")
m.write(OUT)
s = analytical.summary(open_model(OUT))
assert s["load_actions"] == 3, s["load_actions"]

# --- a re-derive PURGES the actions (no orphans), then loads can be re-applied ----------------------
analytical.derive_analytical(m)
assert len(m.by_type("IfcStructuralLinearAction")) == 0, "re-derive clears prior load actions"
assert len(m.by_type("IfcStructuralLoadLinearForce")) == 0, "no orphaned applied loads"
r2 = analytical.apply_member_loads(m)
assert r2["applied"] == 3, r2

# --- the recipe path (apply_recipe) authors + publishes the loaded model ----------------------------
edit.add_column(open_model(TMP), [0, 0], 4.0, 0.4, 0.4, st)     # ensure TMP has a frame member
mm = open_model(TMP)
edit.add_column(mm, [0, 0], 4.0, 0.4, 0.4, st)
mm.write(TMP)
edit.apply_recipe(TMP, "derive_analytical", {}, OUT)
res = edit.apply_recipe(OUT, "apply_structural_loads", {"dead_klf": 1.2, "live_klf": 0.4}, OUT)["changed"]
assert res["applied"] >= 1 and "apply_structural_loads" in edit.RECIPES, res

# --- no analytical members -> a clean message, no crash ---------------------------------------------
massing.generate_blank_ifc(TMP, name="Empty", storeys=1, storey_height=3.0, ground_size=10.0)
me = open_model(TMP)
assert analytical.apply_member_loads(me)["applied"] == 0

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("STRUCT-LOADS-IFC OK - apply_member_loads writes one IfcStructuralLinearAction per analytical curve "
      "member (applied IfcStructuralLoadLinearForce, global −Z at (D+L)×14593.9 N/m), each connected to its "
      "member and grouped under the load group — a loaded, solver-ready analytical IFC. Idempotent "
      "(re-apply refreshes the value, counts unchanged); summary reports load_actions through a round-trip; "
      "a re-derive purges the actions with no orphans; the apply_structural_loads recipe publishes it; an "
      "empty model returns applied=0.")
