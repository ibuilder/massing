"""PROD-ACTUALS — installed-rate actual vs planned + crew utilization over field actuals.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_prod_actuals.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_prod_actuals.db"
os.environ["STORAGE_DIR"] = "./test_storage_prodact"
os.environ.pop("AEC_RBAC", None)

from aec_api import prod_actuals as pa  # noqa: E402

actuals = [
    # drywall: 100 SF in 10 productive hrs + 2 idle → 10 SF/hr, util 0.833; planned 8 → +25% ahead
    {"qto_line": "install-drywall", "qty": 60, "cycle_time": 6, "idle_time": 1, "unit": "SF"},
    {"qto_line": "install-drywall", "qty": 40, "cycle_time": 4, "idle_time": 1, "unit": "SF"},
    # doors: 40 EA in 10 productive + 10 idle → 4 EA/hr, util 0.5; planned 5 → −20% behind; 40/80 done
    {"qto_line": "hang-doors", "qty": 40, "cycle_time": 10, "idle_time": 10, "unit": "EA"},
    # paint: no planned entry → status None
    {"task_id": "paint", "qty": 200, "cycle_time": 20, "idle_time": 0, "unit": "SF"},
]
planned = {
    "install-drywall": {"rate": 8},
    "hang-doors": {"rate": 5, "qty": 80},
}

r = pa.analyze(actuals, planned)
g = {x["group"]: x for x in r["groups"]}

dw = g["install-drywall"]
assert dw["installed_rate"] == 10.0, dw
assert dw["utilization"] == round(10 / 12, 4), dw
assert dw["variance_pct"] == 25.0 and dw["status"] == "ahead", dw

hd = g["hang-doors"]
assert hd["installed_rate"] == 4.0 and hd["utilization"] == 0.5, hd
assert hd["variance_pct"] == -20.0 and hd["status"] == "behind", hd
assert hd["pct_complete"] == 0.5 and hd["remaining_qty"] == 40.0 and hd["projected_hours_at_rate"] == 10.0, hd

pt = g["paint"]
assert pt["installed_rate"] == 10.0 and pt["status"] is None and pt["variance_pct"] is None, pt
assert pt["utilization"] == 1.0, pt                       # zero idle → fully utilized

assert r["ahead"] == 1 and r["behind"] == 1 and r["on_track"] == 0 and r["planned_compared"] == 2, r
assert r["overall_utilization"] == round(40 / 52, 4), r   # productive 40 / (40 prod + 12 idle)
assert r["groups"][0]["group"] == "hang-doors", r         # worst variance sorts first
assert r["worst"] == "hang-doors", r

# empty input is well-formed
e = pa.analyze([], None)
assert e["group_count"] == 0 and e["overall_utilization"] is None and e["planned_compared"] == 0, e

# --- route: 404 for a missing project, 200 + analysis for a real one -------------------------------
if os.path.exists("./test_prod_actuals.db"):
    os.remove("./test_prod_actuals.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    assert c.post("/projects/nope/progress/actuals", json={"actuals": actuals, "planned": planned}).status_code == 404
    pid = c.post("/projects", json={"name": "Prod"}).json()["id"]
    rr = c.post(f"/projects/{pid}/progress/actuals", json={"actuals": actuals, "planned": planned})
    assert rr.status_code == 200, rr.text
    j = rr.json()
    assert j["ahead"] == 1 and j["behind"] == 1 and j["worst"] == "hang-doors", j
    assert j["source"] == "request", j["source"]

    # --- persistence: with an EMPTY actuals list, the stored progress_actual records are analyzed ---
    for rec in ({"activity": "install-drywall", "qty": 60, "cycle_time": 6, "idle_time": 1, "unit": "SF"},
                {"activity": "install-drywall", "qty": 40, "cycle_time": 4, "idle_time": 1, "unit": "SF"},
                {"activity": "hang-doors", "qty": 40, "cycle_time": 10, "idle_time": 10, "unit": "EA",
                 "crew": "Doors Inc."}):
        cr = c.post(f"/projects/{pid}/modules/progress_actual", json={"data": rec})
        assert cr.status_code in (200, 201), cr.text
    stored = c.post(f"/projects/{pid}/progress/actuals", json={"actuals": [], "planned": planned})
    assert stored.status_code == 200, stored.text
    sj = stored.json()
    assert sj["source"] == "progress_actual module", sj["source"]
    sg = {x["group"]: x for x in sj["groups"]}
    assert sg["install-drywall"]["installed_rate"] == 10.0, sg["install-drywall"]
    assert sg["install-drywall"]["status"] == "ahead" and sg["hang-doors"]["status"] == "behind", sg
    # an explicit payload still wins over the stored records
    assert c.post(f"/projects/{pid}/progress/actuals",
                  json={"actuals": actuals, "planned": planned}).json()["source"] == "request"

print("PROD-ACTUALS OK - field actuals roll up per activity into installed rate (qty ÷ productive/cycle "
      "hours) + crew utilization (productive ÷ productive+idle), compared to the planned rate → drywall "
      "10 SF/hr is +25% ahead of an 8 SF/hr plan, doors 4 EA/hr is −20% behind a 5 EA/hr plan (50% complete, "
      "10 h projected to finish at rate), an unplanned activity has no status; the rollup counts 1 ahead / 1 "
      "behind, overall utilization 0.625, worst-variance first; the /progress/actuals route 404s on a "
      "missing project and returns the analysis otherwise. Persistence: with an empty actuals list the "
      "route analyzes the stored progress_actual module records (the field crew's persisted log; "
      "source='progress_actual module'), and an explicit payload still wins.")
