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

# --- D8: the COMcheck/A117.1 layer -----------------------------------------------------------------
# the base model: one 8×3 m external wall (24 m²), one 0.9 m door, no windows → WWR 0 % passes,
# envelope carries no U-values → the COMcheck-ready check FAILS, the ≥32 in door → accessible entrance
d8 = {c["check"]: c for c in a["checks"]}
wwr = d8["Window-wall ratio (prescriptive)"]
assert wwr["status"] == "pass" and "0%" in wwr["detail"], wwr
uval = d8["Envelope U-values present (COMcheck-ready)"]
assert uval["status"] == "fail" and uval["guids"], uval
acc = d8["Accessible entrance (≥ 1 door at 32 in clear)"]
assert acc["status"] == "pass" and "A117.1 404" in acc["citation"], acc

# a big window pushes WWR over 30 % → info (trade-off path), and a U-value on everything → pass.
# NB: open_model is lru-cached, so this is the SAME model object — envelope now w (24 m²) + rw
# (18 m²) + w3 (24 m²) = 66 m²; a 7.5 × 2.8 m window = 21 m² → WWR ≈ 32 %
m3 = open_model(TMP)
st3 = m3.by_type("IfcBuildingStorey")[0].Name
w3 = edit.add_wall(m3, [0, 8], [8, 8], 3.0, 0.2, st3)
edit.add_opening(m3, w3, width=7.5, height=2.8, kind="window")
a4 = cc.approvability(m3)
wwr4 = next(c for c in a4["checks"] if c["check"].startswith("Window-wall"))
assert wwr4["status"] == "info" and "trade-off" in wwr4["detail"], wwr4
for el in (*m3.by_type("IfcWall"), *m3.by_type("IfcWindow")):
    if not el.is_a("IfcElementType"):
        edit.set_element_pset(m3, el.GlobalId, "Pset_Massing_Thermal", "ThermalTransmittance", 0.35, "float")
a5 = cc.approvability(m3)
uval5 = next(c for c in a5["checks"] if c["check"].startswith("Envelope U-values"))
assert uval5["status"] == "pass", uval5

# --- D8: failed checks promote to BCF topics (route) ------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

os.environ["DATABASE_URL"] = "sqlite:///./test_approvability.db"
os.environ["STORAGE_DIR"] = "./test_storage_appr"
os.environ["AEC_TRUST_XUSER"] = "1"
if os.path.exists("./test_approvability.db"):
    os.remove("./test_approvability.db")
from aec_api.main import app  # noqa: E402

H = {"X-User": "editor"}
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Approve"}, headers=H).json()["id"]
    g = c.post(f"/projects/{pid}/generate/massing",
               json={"lot_width": 30, "lot_depth": 20, "far": 1.0, "use_type": "commercial",
                     "envelope": True, "wwr": 0.35}, headers=H)
    assert g.status_code == 200 and g.json()["source_ifc"], g.text[:200]
    r = c.post(f"/projects/{pid}/codecheck/approvability/bcf", headers=H)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    # the generated envelope carries no U-values → at least the COMcheck-ready check fails
    assert body["created"] >= 1 and body["summary"], body
    topics = c.get(f"/projects/{pid}/topics", headers=H).json()
    appr = [t for t in topics if t.get("type") == "approvability"]
    assert len(appr) == body["created"], (len(appr), body["created"])
    assert any("U-values" in t["title"] and t["priority"] == "high" for t in appr), \
        [t["title"] for t in appr]
    assert all("approvability" in (t.get("labels") or []) for t in appr)
    # idempotent: re-running replaces (never piles up)
    r2 = c.post(f"/projects/{pid}/codecheck/approvability/bcf", headers=H)
    topics2 = [t for t in c.get(f"/projects/{pid}/topics", headers=H).json()
               if t.get("type") == "approvability"]
    assert len(topics2) == r2.json()["created"], (len(topics2), r2.json())

if os.path.exists(TMP):
    os.remove(TMP)

print("APPROVABILITY OK - the pre-flight runs egress capacity + door clear-width + two-exit + occupancy "
      "classification + fire-rated-assembly substantiation checks (each cited), an undocumented 2HR wall "
      "FAILS and a UL-classified one PASSES, with a readiness score + not-a-certified-review disclaimer. "
      "D8: WWR 0% passes and ~32% flips to info (trade-off path); missing envelope U-values FAIL the "
      "COMcheck-ready check and stamping ThermalTransmittance flips it to pass; >=1 door at 32 in "
      "satisfies the accessible entrance; POST /codecheck/approvability/bcf promotes failed/info checks "
      "to labeled, prioritized BCF topics idempotently.")
