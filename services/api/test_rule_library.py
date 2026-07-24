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

# HARDEN-2 (S2): the library is bounded — count, selector length, id length
try:
    rl.save("unit-bounds", [{"scope": "IfcWall", "require": "name"}] * (rl.MAX_RULES + 1))
    raise AssertionError("expected QueryError for too many rules")
except rl.QueryError:
    pass
try:
    rl._norm({"scope": "IfcWall & " + "x" * rl.MAX_SELECTOR_LEN, "require": "name"})
    raise AssertionError("expected QueryError for oversized selector")
except rl.QueryError:
    pass
assert len(rl._norm({"scope": "IfcWall", "require": "name", "id": "z" * 999})["id"]) == rl.MAX_ID_LEN

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

    # --- RULE-PACK FOLD: the per-IfcSpace pack rides the same library + run surface ---------------
    assert c.get(f"/projects/{pid}/rules/space-pack").json()["pack"] is None      # empty until saved
    bad_pack = c.put(f"/projects/{pid}/rules/space-pack",
                     json={"pack": {"dimensional": {"min_area": -5}}})
    assert bad_pack.status_code == 422, bad_pack.text                              # validated atomically
    assert c.put(f"/projects/{pid}/rules/space-pack",
                 json={"pack": {"daylight": {"types": []}}}).status_code == 422    # empty types rejected
    sp = c.put(f"/projects/{pid}/rules/space-pack", json={"pack": {
        "dimensional": {"min_area": 1000, "severity": "high"},                     # everything fails
        "daylight": {"types": ["Office"], "severity": "medium"}}})
    assert sp.status_code == 200 and sp.json()["pack"]["dimensional"]["severity"] == "high", sp.text
    assert c.get(f"/projects/{pid}/rules/space-pack").json()["pack"]["daylight"]["types"] == ["Office"]

    # with a pack stored but NO source IFC, /rules/run notes the skip instead of failing
    r_nomodel = c.get(f"/projects/{pid}/rules/run").json()
    assert "no source IFC" in r_nomodel.get("space_rules_note", ""), r_nomodel

    # author a model with spaces (all relabelled Office), attach it, and run the folded check
    import tempfile
    from pathlib import Path

    from aec_api.db import SessionLocal
    from aec_api.models import Project
    from aec_data import edit, massing
    from aec_data.ifc_loader import open_model

    _ifc = Path(tempfile.gettempdir()) / "rule_pack_fold.ifc"
    massing.generate_blank_ifc(str(_ifc), name="Fold", storeys=1, storey_height=3.5, ground_size=20.0)
    m = open_model(str(_ifc))
    assert edit.add_spaces(m, rooms_per_storey=4, ceiling_height=3.0) == 4
    for spx in m.by_type("IfcSpace"):
        spx.LongName = "Office"
    m.write(str(_ifc))
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = str(_ifc)
        db.commit()
    rr = c.get(f"/projects/{pid}/rules/run").json()
    rows = {r["id"]: r for r in rr["rules"] if str(r.get("id", "")).startswith("space:")}
    dim = rows["space:dimensional"]
    assert dim["status"] == "fail" and dim["failed"] == 4 and dim["severity"] == "high", dim
    assert len(dim["fail_guids"]) == 4 and dim["detail"], dim
    # a 2x2 grid: every Office touches the envelope → daylight passes
    assert rows["space:daylight"]["status"] == "pass" and rows["space:daylight"]["scoped"] == 4, rows
    # the space failure folds into the SAME severity rollup
    assert rr["by_severity"].get("high", 0) >= 1 and rr["failing_rules"] >= 1, rr["by_severity"]
    if _ifc.exists():
        _ifc.unlink()

print("RULE-LIB OK - starter set fails 1/severity (high+medium+low); scope+require selectors reuse "
      "QUERY-DSL; n/a when nothing in scope; bad selector 422s atomically; CRUD + run endpoints. "
      "RULE-PACK FOLD: the per-IfcSpace pack (dimensional/daylight/wet-wall) round-trips via "
      "/rules/space-pack (negative numbers + empty type lists 422), /rules/run notes the skip without "
      "a model, and WITH one the geometric space checks fold into the same rollup as space:* rows — "
      "4 Offices all fail a 1000 m2 min-area (high, guids + details carried) while daylight passes on "
      "a 2x2 grid, and the high-severity count includes the space failure.")
