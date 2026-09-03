"""Schedule-acceleration ADVISORY off the CPM critical path — crash / fast-track / near-critical.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_schedule_optimize.py"""
import os
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_schedopt.db"
os.environ["STORAGE_DIR"] = "./test_storage_schedopt"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_schedopt.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

T = date.today()
def iso(days): return (T + timedelta(days=days)).isoformat()


def mk(c, pid, data):
    r = c.post(f"/projects/{pid}/modules/schedule_activity", json={"data": data})
    assert r.status_code in (200, 201), r.text[:160]
    return r.json()["id"]


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Opt"}).json()["id"]
    # a clean FS chain A -> B -> C (all on the critical path) plus a short parallel side branch D
    # with a little float (near-critical).  Durations chosen so crash/fast-track levers appear.
    mk(c, pid, {"name": "Excavation", "wbs": "A", "duration": 20, "percent": 0, "budget": 100000})
    mk(c, pid, {"name": "Foundations", "wbs": "B", "duration": 30, "percent": 0, "budget": 200000,
                "predecessors": "A"})                                   # longest critical -> top crash
    mk(c, pid, {"name": "Superstructure", "wbs": "C", "duration": 25, "percent": 0, "budget": 300000,
                "predecessors": "B"})
    mk(c, pid, {"name": "Sitework", "wbs": "D", "duration": 12, "percent": 0, "budget": 40000,
                "predecessors": "A"})                                   # parallel to B (float -> near-critical)

    o = c.get(f"/projects/{pid}/schedule/optimize").json()
    assert o["critical_count"] >= 3, o
    assert not o["has_cycle"], o
    assert isinstance(o["crash"], list) and o["crash"], o
    # the longest critical activity is the top crash lever, with a positive day estimate
    assert o["crash"][0]["name"] == "Foundations", o["crash"]
    assert o["crash"][0]["days_potential"] >= 1, o["crash"]
    # consecutive critical activities yield fast-track levers
    assert isinstance(o["fast_track"], list) and o["fast_track"], o
    assert all(s["days_potential"] >= 1 for s in o["fast_track"]), o["fast_track"]
    # advisory ceiling = the single strongest lever (savings are not additive)
    assert o["best_single_lever_days"] >= 1, o
    assert o["source"] == "rules", o          # no AI key in CI -> deterministic
    assert "headline" in o and o["headline"], o

    # completing the critical work removes it from the levers (only open work is accelerable)
    for r in c.get(f"/projects/{pid}/modules/schedule_activity").json():
        if (r.get("data") or {}).get("wbs") in ("A", "B", "C"):
            c.patch(f"/projects/{pid}/modules/schedule_activity/{r['id']}", json={"percent": 100})
    o2 = c.get(f"/projects/{pid}/schedule/optimize").json()
    assert not o2["crash"], o2          # nothing open on the critical path left to crash

print(f"SCHEDULE OPTIMIZE OK - {len(o['crash'])} crash + {len(o['fast_track'])} fast-track levers, "
      f"top crash '{o['crash'][0]['name']}' ~{o['crash'][0]['days_potential']}d; "
      f"best single lever ~{o['best_single_lever_days']}d; levers clear when work completes")
