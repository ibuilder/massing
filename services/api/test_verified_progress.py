"""Schedule-linked verified-as-built progress (Wave 8 ③b).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_verified_progress.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_verified_progress.db"
os.environ["STORAGE_DIR"] = "./test_storage_vp"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_verified_progress.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import verified_progress as vp  # noqa: E402

# --- pure rollup: 4 elements on one activity, claimed 80% but only 2 verified in place --------------
elements = [{"guid": g, "ifc_class": "IfcColumn", "storey": "L1"} for g in ("e1", "e2", "e3", "e4")]
acts = [{"ref": "A-1", "title": "Columns L1", "element_guids": ["e1", "e2", "e3", "e4"],
         "workflow_state": "in_progress", "data": {"percent": 80, "trade": "Concrete"}}]
verifs = {"e1": {"state": "verified"}, "e2": {"state": "resolved"},   # both count as verified-in-place
          "e3": {"state": "deviated"}, "e4": {"state": "captured"}}   # deviated + pending
roll = vp.rollup(elements, acts, verifs)
assert roll["elements_total"] == 4, roll
assert roll["elements_verified"] == 2 and roll["elements_deviated"] == 1, roll
assert roll["verified_pct"] == 50.0 and roll["claimed_pct"] == 80.0, roll
assert roll["trust_gap"] == 30.0, roll["trust_gap"]                   # claiming 80, only 50 verified
row = roll["activities"][0]
assert row["ref"] == "A-1" and row["verified"] == 2 and row["trust_gap"] == 30.0, row

# untagged elements fall back to class->trade->activity (IfcColumn -> Structure trade)
roll2 = vp.rollup(elements, [{"ref": "A-9", "title": "Structure", "workflow_state": "open",
                              "data": {"percent": 0, "trade": "Structure"}}],
                  {"e1": {"state": "verified"}})
assert roll2["elements_total"] == 4 and roll2["elements_verified"] == 1, roll2

# --- from_layout_verify: in-tolerance -> verified, out-of-tolerance -> deviated -----------------------
vr = {"out_of_tolerance": [{"guid": "e3", "number": "P3"}],
      "deviations": [{"guid": "e1", "number": "P1", "ifc_class": "IfcColumn", "deviation_m": 0.004, "in_tolerance": True},
                     {"guid": "e3", "number": "P3", "ifc_class": "IfcColumn", "deviation_m": 0.10, "in_tolerance": False}]}
recs = vp.from_layout_verify(vr)
by_guid = {r["guid"]: r for r in recs}
assert by_guid["e1"]["_state"] == "verified" and by_guid["e1"]["deviation_mm"] == 4.0, by_guid["e1"]
assert by_guid["e3"]["_state"] == "deviated" and by_guid["e3"]["deviation_mm"] == 100.0, by_guid["e3"]

# --- HTTP: records -> rollup, and the module is installed --------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as tc:
    pid = tc.post("/projects", json={"name": "AsBuilt Tower"}).json()["id"]
    a = tc.post(f"/projects/{pid}/modules/schedule_activity",
                json={"data": {"name": "Columns", "trade": "Structure", "percent": 100}})
    assert a.status_code in (200, 201), a.text[:200]
    # two field-verification records (installed as the module's default 'captured' state)
    for g in ("gA", "gB"):
        rr = tc.post(f"/projects/{pid}/modules/field_verification",
                     json={"data": {"guid": g, "element": f"C-{g}", "ifc_class": "IfcColumn"}})
        assert rr.status_code in (200, 201), rr.text[:200]
    # the endpoint responds with a rollup shape (records counted) even before a published element index
    r = tc.get(f"/projects/{pid}/verified-progress")
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert "trust_gap" in body and "activities" in body and body["verification_records"] == 2, body

print("VERIFIED-PROGRESS OK - rollup: 4 elements, claimed 80% but 2 verified in place -> verified_pct 50, "
      "trust_gap +30 (over-claim); untagged elements fall back to class->trade->activity; from_layout_verify "
      "maps in-tol->verified / out-of-tol->deviated with mm deviations; HTTP endpoint returns the rollup with "
      "the field_verification records counted. The OpenSpace-style verified-as-built loop, GlobalId-anchored.")
