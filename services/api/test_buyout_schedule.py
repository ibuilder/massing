"""BUYOUT-SCHED — time-phased buyout schedule from QTO joined to the install schedule → last-responsible
-order dates, soonest first, classified vs an as_of date.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_buyout_schedule.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_buyout_schedule.db"
os.environ["STORAGE_DIR"] = "./test_storage_buyout"
os.environ.pop("AEC_RBAC", None)

from aec_api import buyout_schedule as bs  # noqa: E402

activities = [
    {"id": "a1", "cost_code": "03-30", "trade": "Concrete", "start": "2026-09-01"},
    {"id": "a2", "cost_code": "05-12", "trade": "Steel", "start": "2026-08-15"},
]
qto = [
    {"material": "Rebar #5", "cost_code": "03-30", "qty": 100, "unit": "ea", "lead_time_days": 21},   # LRO 08-11
    {"material": "W12x26 steel", "trade": "Steel", "cost": 30000},                                    # lead 60 → LRO 06-16
    {"material": "Misc hardware", "cost_code": "99-99", "qty": 5},                                     # no activity → unscheduled
]
r = bs.schedule(qto, activities, lead_times={"steel": 60}, as_of="2026-07-01")
assert r["line_count"] == 3 and r["unscheduled"] == 1 and r["as_of"] == "2026-07-01", r
# soonest last-responsible-order first: steel (06-16, overdue) before rebar (08-11, ok); unscheduled last
e0 = r["entries"][0]
assert e0["material"] == "W12x26 steel" and e0["last_responsible_order"] == "2026-06-16", e0
assert e0["status"] == "overdue" and e0["buffer_days"] == -15 and e0["lead_time_days"] == 60, e0
rebar = next(e for e in r["entries"] if e["material"] == "Rebar #5")
assert rebar["install_start"] == "2026-09-01" and rebar["last_responsible_order"] == "2026-08-11", rebar
assert rebar["status"] == "ok" and rebar["lead_time_days"] == 21, rebar
misc = next(e for e in r["entries"] if e["material"] == "Misc hardware")
assert misc["status"] == "unscheduled" and misc["last_responsible_order"] is None, misc
assert r["entries"][-1]["material"] == "Misc hardware", r["entries"]              # unscheduled sorts last
assert r["overdue"] == 1 and r["total_value"] == 30000 and r["status_counts"]["ok"] == 1, r

# no as_of → matched lines are "scheduled", not classified
r2 = bs.schedule(qto, activities, lead_times={"steel": 60})
assert r2["as_of"] is None and next(e for e in r2["entries"] if e["material"] == "Rebar #5")["status"] == "scheduled", r2

# --- route ------------------------------------------------------------------------------------------
if os.path.exists("./test_buyout_schedule.db"):
    os.remove("./test_buyout_schedule.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Buyout"}).json()["id"]
    rr = c.post(f"/projects/{pid}/procurement/buyout-schedule",
                json={"qto_lines": qto, "activities": activities, "lead_times": {"steel": 60}, "as_of": "2026-07-01"})
    assert rr.status_code == 200, rr.text
    j = rr.json()
    assert j["overdue"] == 1 and j["entries"][0]["material"] == "W12x26 steel", j

print("BUYOUT-SCHED OK - QTO lines join to their installing activity (by id/cost-code/trade) → the "
      "last-responsible-order date (install start − lead time): a steel line with a 60-day lead installing "
      "2026-08-15 must be ordered by 2026-06-16 (overdue as of 2026-07-01, buffer −15d), rebar with a 21-day "
      "lead installing 2026-09-01 orders by 2026-08-11 (ok), and an unmatched line is 'unscheduled' and sorts "
      "last; soonest-order-first, 1 overdue, $30k in the window; the /procurement/buyout-schedule route works.")
