"""RULE-LIB — user-authored parametric rule checks (scope selector + require selector + severity).
Unit-tests the engine over a synthetic index, then the /rules CRUD + run endpoints.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_rule_library.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_rule_library.db"
os.environ["STORAGE_DIR"] = "./test_storage_rule_library"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_rule_library.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import rule_library as rl  # noqa: E402

IDX = {
    "d1": {"ifc_class": "IfcDoor", "storey": "L1", "psets": {"Pset_DoorCommon": {"FireRating": "90"}}},
    "d2": {"ifc_class": "IfcDoor", "storey": "L1", "psets": {"Pset_DoorCommon": {}}},              # no rating → fail
    "w1": {"ifc_class": "IfcWall", "psets": {"Pset_WallCommon": {"IsExternal": "true", "FireRating": "2HR", "LoadBearing": "true"}}},
    "w2": {"ifc_class": "IfcWall", "psets": {"Pset_WallCommon": {"IsExternal": "true"}}},           # ext, no rating, no load-bearing
}

# the starter library: each rule fails exactly one element here (one per severity)
res = rl.run(IDX, rl.STARTER_RULES)
assert res["model_scored"] and res["total_rules"] == 3, res
assert res["failing_rules"] == 3 and res["total_violations"] == 3, res
assert res["by_severity"] == {"high": 1, "medium": 1, "low": 1}, res["by_severity"]
door = next(r for r in res["rules"] if r["id"] == "fire-door-rating")
assert door["scoped"] == 2 and door["failed"] == 1 and door["fail_guids"] == ["d2"], door

# a custom rule with a value comparison in `require`
custom = rl._norm({"scope": "IfcWall", "require": "Pset_WallCommon.FireRating=2HR", "severity": "high"})
ev = rl.evaluate(IDX, custom)
assert ev["scoped"] == 2 and ev["fail_guids"] == ["w2"], ev            # w1 is 2HR, w2 has none

# a rule that matches nothing in scope is n/a, not a failure
na = rl.evaluate(IDX, rl._norm({"scope": "IfcSlab", "require": "Pset_SlabCommon.Thickness>100"}))
assert na["status"] == "n/a" and na["scoped"] == 0, na

# validation rejects a missing/garbage selector
for bad in ({"scope": "", "require": "IfcWall"}, {"scope": "IfcWall", "require": ""}, {"scope": "&", "require": "IfcWall"}):
    try:
        rl._norm(bad)
        raise AssertionError(f"expected QueryError for {bad!r}")
    except rl.QueryError:
        pass

# no model loaded → not scored
assert rl.run(None, rl.STARTER_RULES)["model_scored"] is False

# --- endpoints ---
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Rules"}).json()["id"]
    g = c.get(f"/projects/{pid}/rules").json()
    assert g["seeded"] is True and len(g["rules"]) == 3, g              # starter set until saved
    saved = c.put(f"/projects/{pid}/rules", json={"rules": [
        {"name": "L1 doors need a rating", "scope": "IfcDoor & storey=L1",
         "require": "Pset_DoorCommon.FireRating", "severity": "high"}]})
    assert saved.status_code == 200 and saved.json()["saved"] == 1, saved.text
    g2 = c.get(f"/projects/{pid}/rules").json()
    assert g2["seeded"] is False and g2["rules"][0]["id"], g2           # id auto-assigned
    # a bad selector rejects the whole save
    bad = c.put(f"/projects/{pid}/rules", json={"rules": [{"scope": "", "require": "IfcWall"}]})
    assert bad.status_code == 422, bad.text
    # library unchanged after the rejected save
    assert len(c.get(f"/projects/{pid}/rules").json()["rules"]) == 1
    # run with no model loaded → not scored
    assert c.get(f"/projects/{pid}/rules/run").json()["model_scored"] is False

print("RULE-LIB OK - starter set fails 1/severity (high+medium+low); scope+require selectors reuse "
      "QUERY-DSL; n/a when nothing in scope; bad selector 422s atomically; CRUD + run endpoints")
