"""W11 D8 approvability pre-flight: a plan-reviewer checklist over the model (egress, door widths,
occupancy classification, substantiated fire-rated assemblies) with a readiness score.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_approvability.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import codecheck as cc  # noqa: E402
from aec_data import detailing, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_appr_test.ifc")
massing.generate_blank_ifc(TMP, name="Approvability Test", storeys=1, storey_height=3.0, ground_size=30.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_spaces(m, rooms_per_storey=3, ceiling_height=3.0)
w = edit.add_wall(m, [0, 0], [8, 0], 3.0, 0.2, st)
edit.add_opening(m, w, width=0.9, height=2.1, kind="door")     # ≥32in → passes width check

a = cc.approvability(m)
checks = {c["check"]: c for c in a["checks"]}
assert "Egress capacity" in checks and "Egress door clear width (≥32 in)" in checks, list(checks)
assert checks["Egress door clear width (≥32 in)"]["status"] in ("pass", "na"), checks["Egress door clear width (≥32 in)"]
# every check carries a citation + a status in the allowed set
assert all(c["citation"] and c["status"] in ("pass", "fail", "na", "info") for c in a["checks"]), a["checks"]
assert "summary" in a and "ready" in a["summary"] and a["disclaimer"], a

# --- fire-rated assembly substantiation: a rated wall with NO reference FAILS; with a classification PASSES
m2 = open_model(TMP)
st2 = m2.by_type("IfcBuildingStorey")[0].Name
rw = edit.add_wall(m2, [0, 0], [6, 0], 3.0, 0.2, st2)
edit.set_element_pset(m2, rw, "Pset_WallCommon", "FireRating", "2HR")   # rated, but undocumented
a2 = cc.approvability(m2)
fire = next(c for c in a2["checks"] if c["check"].startswith("Fire-rated"))
assert fire["status"] == "fail" and rw in fire["guids"], fire
# now attach a UL classification → substantiated → passes
detailing.classify(m2, [rw], "UL", "U419", "Rated Wall Assembly")
a3 = cc.approvability(m2)
fire3 = next(c for c in a3["checks"] if c["check"].startswith("Fire-rated"))
assert fire3["status"] == "pass", fire3

# --- occupancy check must gate on a real OccupancyType, NOT the free-text LongName that add_spaces sets
occ_check = next(c for c in a["checks"] if c["check"].startswith("Occupancy classification"))
assert occ_check["status"] == "fail", occ_check   # 3 add_spaces rooms have LongName but no OccupancyType
# stamp a real occupancy type on every space (spaces are spatial, not IfcElement) → the check passes
import ifcopenshell.api  # noqa: E402

for sp in m.by_type("IfcSpace"):
    ps = ifcopenshell.api.run("pset.add_pset", m, product=sp, name="Pset_SpaceOccupancyRequirements")
    ifcopenshell.api.run("pset.edit_pset", m, pset=ps, properties={"OccupancyType": "Business"})
a_occ = cc.approvability(m)
occ2 = next(c for c in a_occ["checks"] if c["check"].startswith("Occupancy classification"))
assert occ2["status"] == "pass", occ2

# score is passed/gating
s = a3["summary"]
assert s["gating"] >= 1 and (s["score_pct"] is None or 0 <= s["score_pct"] <= 100), s

if os.path.exists(TMP):
    os.remove(TMP)

print("APPROVABILITY OK - the pre-flight runs egress capacity + door clear-width + two-exit + occupancy "
      "classification + fire-rated-assembly substantiation checks (each cited), an undocumented 2HR wall "
      "FAILS and a UL-classified one PASSES, with a readiness score + not-a-certified-review disclaimer.")
