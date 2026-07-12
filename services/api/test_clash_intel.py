"""Clash coordination intelligence — group raw clashes into tracked coordination issues, score
severity, and reconcile across runs (new / active / resolved / reappeared).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_clash_intel.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_clash_intel.db"
os.environ["STORAGE_DIR"] = "./test_storage_clash_intel"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_clash_intel.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient   # noqa: E402
from aec_api.main import app                # noqa: E402


def _clash(ag, ac, am, bg, bc, bm, vol, xyz):
    return {"a_guid": ag, "a_class": ac, "a_model": am, "b_guid": bg, "b_class": bc, "b_model": bm,
            "volume": vol, "point": {"x": xyz[0], "y": xyz[1], "z": xyz[2]}}


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Coord Tower"}).json()["id"]

    # --- RUN 1: a duct crosses 3 joists (→ ONE issue) + a pipe hits a wall (→ one issue) --------------
    run1 = [
        _clash("duct01", "IfcDuctSegment", "MEP", "joistA", "IfcBeam", "STR", 0.03, (1, 2, 3)),
        _clash("duct01", "IfcDuctSegment", "MEP", "joistB", "IfcBeam", "STR", 0.02, (2, 2, 3)),
        _clash("duct01", "IfcDuctSegment", "MEP", "joistC", "IfcBeam", "STR", 0.04, (3, 2, 3)),
        _clash("pipe01", "IfcPipeSegment", "PLU", "wall01", "IfcWall", "ARC", 0.01, (9, 9, 1)),
    ]
    # dry-run analyze: 4 raw clashes collapse to 2 issues (10:1-style reduction, here 2:1)
    an = c.post(f"/projects/{pid}/clash/analyze", json={"clashes": run1}).json()
    assert an["clash_count"] == 4 and an["group_count"] == 2, an
    assert an["reduction"] == 2.0, an["reduction"]
    duct = next(g for g in an["groups"] if g["key_guid"] == "duct01")
    assert duct["count"] == 3, duct                      # the duct group carries all 3 joist clashes
    assert duct["severity_label"] in ("High", "Critical"), duct["severity_label"]   # struct pair, multi-clash
    assert duct["severity_score"] >= 50, duct["severity_score"]

    # coordinate: writes the two issues, all NEW
    r1 = c.post(f"/projects/{pid}/clash/coordinate", json={"clashes": run1, "label": "R1"}).json()
    assert r1["new"] == 2 and r1["active"] == 0 and r1["resolved"] == 0, r1
    assert r1["group_count"] == 2, r1
    iss = c.get(f"/projects/{pid}/modules/coordination_issue").json()
    assert len(iss) == 2, iss
    assert all(i["data"].get("clash_hash") for i in iss), "issues carry a stable clash group id"

    # --- RUN 2: duct resolved (gone); pipe still clashes; a NEW column-duct clash appears -------------
    run2 = [
        _clash("pipe01", "IfcPipeSegment", "PLU", "wall01", "IfcWall", "ARC", 0.01, (9, 9, 1)),
        _clash("col01", "IfcColumn", "STR", "duct09", "IfcDuctSegment", "MEP", 0.05, (5, 5, 2)),
    ]
    r2 = c.post(f"/projects/{pid}/clash/coordinate", json={"clashes": run2, "label": "R2"}).json()
    assert r2["new"] == 1, r2                             # the column-duct issue
    assert r2["active"] == 1, r2                          # pipe-wall carried forward
    assert r2["resolved"] == 1, r2                        # the duct-joists issue auto-resolved (absent)
    # the duct issue is now resolved
    iss = {i["data"]["subject"]: i for i in c.get(f"/projects/{pid}/modules/coordination_issue").json()}
    duct_issue = next(i for s, i in iss.items() if "duct01" in str(i["data"].get("clash_hash", ""))
                      or "IfcDuctSegment" in s and "joist" not in s.lower())
    # (find the duct01-group issue by its stable hash from run 1)
    duct_hash = duct["group_hash"]
    duct_rec = next(i for i in c.get(f"/projects/{pid}/modules/coordination_issue").json()
                    if i["data"].get("clash_hash") == duct_hash)
    assert duct_rec["workflow_state"] == "resolved", duct_rec["workflow_state"]

    # --- RUN 3: the duct-joists clash REAPPEARS → the resolved issue auto-reopens ---------------------
    r3 = c.post(f"/projects/{pid}/clash/coordinate", json={"clashes": run1, "label": "R3"}).json()
    assert r3["reappeared"] == 1, r3                      # duct issue came back → reopened
    assert r3["active"] == 1, r3                          # pipe-wall still active
    assert r3["resolved"] == 1, r3                        # the column-duct issue now absent → resolved
    duct_rec = next(i for i in c.get(f"/projects/{pid}/modules/coordination_issue").json()
                    if i["data"].get("clash_hash") == duct_hash)
    assert duct_rec["workflow_state"] == "open", duct_rec["workflow_state"]   # reopened

    # --- KPIs -----------------------------------------------------------------------------------------
    m = c.get(f"/projects/{pid}/clash/metrics").json()
    assert m["total_issues"] == 3, m                      # duct, pipe, column groups ever seen
    assert m["runs"] == 3 and len(m["burn_down"]) == 3, m
    assert m["reappearance_rate"] > 0, m                  # one reappearance occurred
    assert "MEP × STR" in m["by_discipline"] or "STR × MEP" in m["by_discipline"], m["by_discipline"]

print("CLASH INTEL OK - 4 raw clashes group to 2 coordination issues (duct-3 joists = ONE issue), "
      "severity scored (structural multi-clash = High+); reconcile across runs: NEW -> auto-RESOLVED "
      "when a clash disappears -> auto-REOPENED (reappeared) when it returns; KPIs report status mix, "
      "discipline pairs, run burn-down and reappearance rate.")
