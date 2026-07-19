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

# no model → every check skips, overall skip (incl. the MODEL-CI-3 ids + qto_delta adapters)
rep_none = model_ci.run(None, "unit-none", None)
assert rep_none["overall"] == "skip", rep_none
assert {c["key"] for c in rep_none["checks"]} == {"rules", "named", "clash", "ids", "qto_delta"}, rep_none

# --- MODEL-CI-3 qto-delta: pure rollup + drift maths (no IFC needed) -------------------------------
rows = [{"ifc_class": "IfcWall", "area": 10.0, "volume": 2.0},
        {"ifc_class": "IfcWall", "area": 12.0, "volume": 2.5},
        {"ifc_class": "IfcDoor", "area": None, "volume": None}]
snap = model_ci._qto_rollup(rows)
assert snap["IfcWall"] == {"count": 2, "area": 22.0, "volume": 4.5}, snap
assert snap["IfcDoor"]["count"] == 1, snap
# stable → no notes; >25% count swing, appear + vanish all flagged (one note per class)
assert model_ci._qto_delta(snap, snap) == []
moved = {"IfcWall": {"count": 5, "area": 22.0, "volume": 4.5},          # 2 → 5 = +150%
         "IfcSlab": {"count": 3, "area": 30.0, "volume": 9.0}}          # appeared; IfcDoor vanished
notes = model_ci._qto_delta(snap, moved)
assert len(notes) == 3, notes
assert any("IfcWall count" in n for n in notes), notes
assert any("IfcSlab appeared" in n for n in notes), notes
assert any("IfcDoor vanished" in n for n in notes), notes
# a swing under the threshold stays quiet
assert model_ci._qto_delta({"IfcWall": {"count": 10, "area": 100, "volume": 10}},
                           {"IfcWall": {"count": 11, "area": 110, "volume": 11}}) == []

# --- endpoints (no model loaded → skip, and it persists) ---
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "CI"}).json()["id"]
    assert c.get(f"/projects/{pid}/ci/latest").json()["overall"] == "none"   # never run
    run = c.post(f"/projects/{pid}/ci/run").json()
    assert run["overall"] == "skip" and run["total_checks"] == 5, run          # no model → skip
    assert run["created_topics"] == 0, run                                     # not asked for topics
    assert c.get(f"/projects/{pid}/ci/latest").json()["overall"] == "skip"    # persisted
    # MODEL-CI-2: the clash adapter reads the LATEST clash_detect job — no run yet → skip
    clash_chk = next(x for x in run["checks"] if x["key"] == "clash")
    assert clash_chk["status"] == "skip" and "no clash run" in clash_chk["summary"], clash_chk
    # MODEL-CI-3: no pinned IDS → skip; no source IFC → qto skips too
    assert next(x for x in run["checks"] if x["key"] == "ids")["status"] == "skip", run
    assert next(x for x in run["checks"] if x["key"] == "qto_delta")["status"] == "skip", run
    # MODEL-CI-3 BCF artifacts: failing checks become open coordination Topics on request. Force a
    # fail by making the qto adapter raise (run() reports a raising check as fail, never crashes).
    from aec_api import model_ci as _mc
    _orig = _mc.CHECKS
    _mc.CHECKS = _orig + [("boom", "Always failing", lambda d, p, i: (_ for _ in ()).throw(RuntimeError("boom")))]
    try:
        rt = c.post(f"/projects/{pid}/ci/run?create_topics=true").json()
        assert rt["overall"] == "fail" and rt["created_topics"] == 1, rt
    finally:
        _mc.CHECKS = _orig
    topics = c.get(f"/projects/{pid}/topics").json()
    ci_topics = [t for t in topics if str(t.get("title", "")).startswith("Model CI:")]
    assert len(ci_topics) == 1 and ci_topics[0]["status"] == "open", topics
    # MODEL-CI-2: the model_ci job kind (auto-enqueued on publish) round-trips on the durable queue
    import time
    job = c.post(f"/projects/{pid}/jobs", json={"kind": "model_ci", "params": {}}).json()
    for _ in range(50):
        st = c.get(f"/projects/{pid}/jobs/{job['id']}").json()
        if st["state"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert st["state"] == "done" and st["result"]["total_checks"] == 5, st

print("MODEL-CI OK - 5-check pack (rules/named/clash/ids/qto_delta) → pass/warn/fail badge; "
      "door-missing-rating fails, clean model passes, unnamed fails completeness, no-model skips all "
      "five; run persists + latest reads it. CI-3: qto rollup + >25% drift maths (appear/vanish/swing "
      "flagged, stable + sub-threshold quiet); no-pinned-IDS and no-source-IFC skip cleanly; "
      "create_topics=true turns each failing check into ONE open coordination Topic (BCF-model).")
