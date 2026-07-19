"""Resource-loaded scheduling (deepened): resource_assignment ties a resource (labor/equipment/material
+ rate) to a schedule activity + cost code, producing a cost-loaded histogram, unit + cost S-curves,
over-allocation vs an availability cap, a cost_code.resource_budget rollup, a leveling advisory (smooth
work with CPM float), and the report PDF. Also checks the crew_size fallback.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_resource_loading.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_resource_loading.db"
os.environ["STORAGE_DIR"] = "./test_storage_resource_loading"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_resource_loading.db",):
    if os.path.exists(_f):
        os.remove(_f)

from datetime import date, timedelta  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import reports  # noqa: E402
from aec_api.main import app  # noqa: E402


def _mk(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()["id"]


with TestClient(app) as c:
    today = date.today()
    pid = c.post("/projects", json={"name": "Resource Tower"}).json()["id"]
    cc1 = _mk(c, pid, "cost_code", {"code": "03-30", "description": "Concrete", "division": "03"})
    cc2 = _mk(c, pid, "cost_code", {"code": "02-00", "description": "Sitework", "division": "02"})

    # A = long, critical (40d); B = short, parallel → ~30d float. They overlap the first weeks.
    a = _mk(c, pid, "schedule_activity", {"name": "Foundations", "trade": "Concrete", "cost_code": cc1,
        "start": str(today), "finish": str(today + timedelta(days=40))})
    b = _mk(c, pid, "schedule_activity", {"name": "Sitework", "trade": "Sitework", "cost_code": cc2,
        "start": str(today), "finish": str(today + timedelta(days=10))})
    _mk(c, pid, "resource_assignment", {"resource_name": "Concrete crew", "resource_type": "Labor",
        "trade": "Concrete", "activity": a, "cost_code": cc1, "units": 8, "unit": "day",
        "rate": 500, "budgeted_cost": 320000})
    _mk(c, pid, "resource_assignment", {"resource_name": "Site crew", "resource_type": "Labor",
        "trade": "Sitework", "activity": b, "cost_code": cc2, "units": 8, "unit": "day",
        "rate": 450, "budgeted_cost": 72000})

    # --- loading: cost-loaded histogram + S-curves + over-allocation vs cap=10 --------------------
    ld = c.get(f"/projects/{pid}/schedule/resource-loading?cap=10").json()
    assert ld["source"] == "resource_assignment" and ld["loads"] == 2, ld
    assert ld["peak"]["units"] == 16.0, ld["peak"]              # both crews overlap early → 8+8
    assert set(ld["trades"]) == {"Concrete", "Sitework"} and ld["types"] == ["Labor"], ld
    assert round(ld["total_cost"]) == 392000, ld["total_cost"]  # 320k + 72k
    assert ld["cost_curve"][-1]["cumulative"] == round(ld["total_cost"], 2), ld["cost_curve"][-1]
    assert ld["over_allocation"] and all(o["units"] > 10 for o in ld["over_allocation"]), ld["over_allocation"]
    cc1_rec = c.get(f"/projects/{pid}/modules/cost_code/{cc1}").json()
    assert cc1_rec["data"]["resource_budget"] == 320000, cc1_rec["data"].get("resource_budget")

    # --- leveling: only the activity with float (Sitework) is a smoothing candidate ---------------
    lv = c.get(f"/projects/{pid}/schedule/resource-leveling?cap=10").json()
    assert lv["over_weeks"] >= 1, lv
    names = {s["activity"] for s in lv["suggestions"]}
    assert "Sitework" in names and "Foundations" not in names, lv["suggestions"]
    assert all(s["total_float_days"] > 0 for s in lv["suggestions"]), lv["suggestions"]
    lv2 = c.get(f"/projects/{pid}/schedule/resource-leveling?cap=100").json()
    assert lv2["over_weeks"] == 0 and lv2["suggestions"] == [], lv2

    # --- RESOURCE-LEVEL-2 (Sprint 1): APPLY one leveling round — mutates within float only ---------
    ap = c.post(f"/projects/{pid}/schedule/resource-leveling/apply", json={"cap": 10}).json()
    assert ap["moved"] == 1 and ap["moves"][0]["activity"] == "Sitework", ap
    assert ap["moves"][0]["shifted_days"] == 7, "week-granular shift, bounded by float"
    assert ap["moves"][0]["float_remaining"] > 0, "shift stayed within the CPM float"
    # the Sitework record's dates actually moved +7d; critical Foundations untouched
    b_rec = c.get(f"/projects/{pid}/modules/schedule_activity/{b}").json()["data"]
    assert b_rec["start"] == str(today + timedelta(days=7)), b_rec["start"]
    assert b_rec["finish"] == str(today + timedelta(days=17)), b_rec["finish"]
    a_rec = c.get(f"/projects/{pid}/modules/schedule_activity/{a}").json()["data"]
    assert a_rec["start"] == str(today), "critical-path activity never shifts"
    # honest physics: a 10d task can't de-overlap a 40d critical task within this window — the peak
    # stays; the endpoint reports it truthfully rather than pretending the plan leveled.
    assert ap["peak_after"]["units"] == ap["peak_before"]["units"] == 16.0, ap
    # cap=100 → nothing over-allocated → a no-op apply
    ap2 = c.post(f"/projects/{pid}/schedule/resource-leveling/apply", json={"cap": 100}).json()
    assert ap2["moved"] == 0, ap2

    # --- report PDF renders --------------------------------------------------------------------
    assert "resource_loading" in {x["id"] for x in reports.catalog()}, "resource_loading missing"
    rep = c.get(f"/projects/{pid}/reports/resource_loading.pdf")
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF", rep.status_code

    # --- fallback: a project with crew_size activities but no assignments -------------------------
    pid2 = c.post("/projects", json={"name": "Crew fallback"}).json()["id"]
    _mk(c, pid2, "schedule_activity", {"name": "Erect steel", "trade": "Steel", "crew_size": 6,
        "start": str(today), "finish": str(today + timedelta(days=14)), "budget": 60000})
    ld2 = c.get(f"/projects/{pid2}/schedule/resource-loading").json()
    assert ld2["source"] == "schedule_activity.crew_size" and ld2["loads"] == 1, ld2
    assert ld2["peak"]["units"] == 6.0, ld2["peak"]

print("RESOURCE LOADING OK - resource_assignment cost-loads the schedule (peak 16 crew, $392k, "
      "over-allocation vs cap 10, cost_code.resource_budget rollup $320k); leveling flags the "
      "float-30 Sitework as a smoothing candidate and locks the critical Foundations; report PDF "
      "served; crew_size fallback still renders the manpower curve.")
