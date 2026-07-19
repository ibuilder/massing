"""MODEL-CI — the model check pack (rule library + data-completeness) → pass/warn/fail report + badge.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_model_ci.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_model_ci.db"
os.environ["STORAGE_DIR"] = "./test_storage_model_ci"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_model_ci.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import model_ci  # noqa: E402

# a door missing its fire rating trips the high-severity starter rule → overall fail; both are named → named passes
IDX_FAIL = {
    "g1": {"ifc_class": "IfcDoor", "name": "D1", "psets": {"Pset_DoorCommon": {"FireRating": "90"}}},
    "g2": {"ifc_class": "IfcDoor", "name": "D2", "psets": {"Pset_DoorCommon": {}}},
}
rep = model_ci.run(None, "unit-fail", IDX_FAIL)
assert rep["overall"] == "fail" and rep["badge"] == "FAIL", rep
rules = next(c for c in rep["checks"] if c["key"] == "rules")
assert rules["status"] == "fail", rules
named = next(c for c in rep["checks"] if c["key"] == "named")
assert named["status"] == "pass" and named["metrics"]["named_pct"] == 100.0, named

# latest round-trips the stored report
assert model_ci.latest("unit-fail")["overall"] == "fail"

# a clean model (all doors rated, all named) → overall pass
IDX_PASS = {
    "g1": {"ifc_class": "IfcDoor", "name": "D1", "psets": {"Pset_DoorCommon": {"FireRating": "90"}}},
    "g2": {"ifc_class": "IfcDoor", "name": "D2", "psets": {"Pset_DoorCommon": {"FireRating": "60"}}},
}
assert model_ci.run(None, "unit-pass", IDX_PASS)["overall"] == "pass"

# unnamed elements warn/fail the completeness gate (here 0% named → fail), no rules scoped either
IDX_UNNAMED = {"g1": {"ifc_class": "IfcSlab"}, "g2": {"ifc_class": "IfcSlab"}}
rep_u = model_ci.run(None, "unit-unnamed", IDX_UNNAMED)
named_u = next(c for c in rep_u["checks"] if c["key"] == "named")
assert named_u["status"] == "fail", named_u                       # 0% named

# no model → every check skips, overall skip
rep_none = model_ci.run(None, "unit-none", None)
assert rep_none["overall"] == "skip", rep_none

# --- endpoints (no model loaded → skip, and it persists) ---
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "CI"}).json()["id"]
    assert c.get(f"/projects/{pid}/ci/latest").json()["overall"] == "none"   # never run
    run = c.post(f"/projects/{pid}/ci/run").json()
    assert run["overall"] == "skip" and run["total_checks"] == 3, run          # no model → skip
    assert c.get(f"/projects/{pid}/ci/latest").json()["overall"] == "skip"    # persisted
    # MODEL-CI-2: the clash adapter reads the LATEST clash_detect job — no run yet → skip
    clash_chk = next(x for x in run["checks"] if x["key"] == "clash")
    assert clash_chk["status"] == "skip" and "no clash run" in clash_chk["summary"], clash_chk
    # MODEL-CI-2: the model_ci job kind (auto-enqueued on publish) round-trips on the durable queue
    import time
    job = c.post(f"/projects/{pid}/jobs", json={"kind": "model_ci", "params": {}}).json()
    for _ in range(50):
        st = c.get(f"/projects/{pid}/jobs/{job['id']}").json()
        if st["state"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert st["state"] == "done" and st["result"]["total_checks"] == 3, st

print("MODEL-CI OK - check pack (rules + named) → pass/warn/fail badge; door-missing-rating fails, "
      "clean model passes, unnamed fails completeness, no-model skips; run persists + latest reads it")
