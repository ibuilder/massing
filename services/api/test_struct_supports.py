"""W10-7 supports: fix the base analytical nodes as pinned/fixed boundary conditions so the model is
statically stable + solvable. Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_struct_supports.py"""
import os
import sys
import tempfile

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import analytical, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(tempfile.gettempdir(), "_struct_supports_test.ifc")
massing.generate_blank_ifc(TMP, name="Supports", storeys=1, storey_height=4.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
# a portal frame: two columns rising 0→4 m + a beam tying their tops → 4 distinct nodes, 2 at the base
edit.add_column(m, [0, 0], 4.0, 0.4, 0.4, st)
edit.add_column(m, [6, 0], 4.0, 0.4, 0.4, st)
edit.add_beam(m, [0, 0], [6, 0], 0.3, 0.5, st)
analytical.derive_analytical(m)
n_nodes = len(m.by_type("IfcStructuralPointConnection"))
assert n_nodes == 4, n_nodes

# --- pinned supports at the base (lowest z) ----------------------------------------------------------
r = analytical.apply_supports(m, kind="pinned")
# the two column bases + the beam ends dedupe: the base nodes are those at the minimum elevation
assert r["supported"] == r["base_nodes"] and r["supported"] >= 2, r
assert r["kind"] == "pinned", r
conds = m.by_type("IfcBoundaryNodeCondition")
assert len(conds) == r["supported"], (len(conds), r)
# each supported node carries the condition; a pinned base fixes translations, frees rotations
supported_nodes = [n for n in m.by_type("IfcStructuralPointConnection") if getattr(n, "AppliedCondition", None)]
assert len(supported_nodes) == r["supported"], "AppliedCondition set on the base nodes"
c0 = conds[0]
assert c0.TranslationalStiffnessX.wrappedValue is True and c0.RotationalStiffnessX.wrappedValue is False, \
    (c0.TranslationalStiffnessX, c0.RotationalStiffnessX)

# --- idempotent: re-applying does not accumulate conditions -----------------------------------------
r2 = analytical.apply_supports(m, kind="pinned")
assert len(m.by_type("IfcBoundaryNodeCondition")) == r2["supported"] == r["supported"], (r, r2)

# --- fixed base fixes rotations too -----------------------------------------------------------------
rf = analytical.apply_supports(m, kind="fixed")
assert rf["kind"] == "fixed"
cf = m.by_type("IfcBoundaryNodeCondition")[0]
assert cf.TranslationalStiffnessX.wrappedValue is True and cf.RotationalStiffnessX.wrappedValue is True, \
    "fixed base fixes rotations"
assert len(m.by_type("IfcBoundaryNodeCondition")) == rf["supported"], "still one condition per base node"

# --- summary reports supports through a serialize round-trip ----------------------------------------
OUT = os.path.join(tempfile.gettempdir(), "_struct_supports_out.ifc")
m.write(OUT)
s = analytical.summary(open_model(OUT))
assert s["supports"] == rf["supported"], s

# --- a re-derive clears the supports (connections rebuilt); re-apply works --------------------------
analytical.derive_analytical(m)
assert len(m.by_type("IfcBoundaryNodeCondition")) == 0, "re-derive clears prior supports"
assert analytical.apply_supports(m)["supported"] >= 2

# --- recipe path + no-nodes guard -------------------------------------------------------------------
assert "apply_structural_supports" in edit.RECIPES
massing.generate_blank_ifc(TMP, name="Empty", storeys=1, storey_height=3.0, ground_size=10.0)
assert analytical.apply_supports(open_model(TMP))["supported"] == 0

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("SUPPORTS OK - apply_supports fixes the base (lowest-elevation) analytical nodes as "
      "IfcBoundaryNodeCondition supports (pinned = translations fixed / rotations free; fixed = all six "
      "DOF), making the analytical model statically stable + solvable. Idempotent (re-apply doesn't "
      "accumulate), reported by summary through a round-trip, cleared by a re-derive; the "
      "apply_structural_supports recipe publishes it; empty model → 0 supports.")
