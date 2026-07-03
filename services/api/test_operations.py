"""Operations phase — CMMS (PM generation + KPIs) and energy (EUI/trend + flagged bridge).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_operations.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_operations.db"
os.environ["STORAGE_DIR"] = "./test_storage_operations"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("ENERGY_STAR_PROVIDER", None)
for _f in ("./test_operations.db",):
    if os.path.exists(_f):
        os.remove(_f)

from datetime import date, timedelta                  # noqa: E402

from fastapi.testclient import TestClient             # noqa: E402
from aec_api.main import app                          # noqa: E402


def _create(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


def _act(c, pid, key, rid, action):
    r = c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})
    assert r.status_code == 200, f"{action}: {r.text[:160]}"
    return r.json()


today = date.today()
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # --- CMMS: due PM schedule generates a preventive WO; idempotent per cycle -----------------
    sched = _create(c, pid, "pm_schedule", {"subject": "AHU-1 quarterly filter change",
        "frequency_days": 90, "next_due": (today - timedelta(days=1)).isoformat(),
        "tasks": "Replace filters; check belts."})
    fresh = _create(c, pid, "pm_schedule", {"subject": "Roof inspection",
        "frequency_days": 365, "next_due": (today + timedelta(days=200)).isoformat()})

    g1 = c.post(f"/projects/{pid}/cmms/generate-pm")
    assert g1.status_code == 200, g1.text[:160]
    assert g1.json()["generated"] == 1, g1.json()          # only the due schedule fires
    g2 = c.post(f"/projects/{pid}/cmms/generate-pm").json()
    assert g2["generated"] == 0, f"second run must be idempotent: {g2}"
    s2 = c.get(f"/projects/{pid}/modules/pm_schedule/{sched['id']}").json()
    assert s2["data"]["next_due"] == (today + timedelta(days=90)).isoformat(), s2["data"]["next_due"]

    # --- work the generated WO through the workflow, plus a corrective one ---------------------
    wos = c.get(f"/projects/{pid}/modules/work_order").json()
    pm_wo = next(w for w in wos if w["data"].get("wo_type") == "Preventive")
    _act(c, pid, "work_order", pm_wo["id"], "assign")
    _act(c, pid, "work_order", pm_wo["id"], "start")
    # complete requires completed_date
    r = c.post(f"/projects/{pid}/modules/work_order/{pm_wo['id']}/transition",
               json={"action": "complete"})
    assert r.status_code == 400, "complete without completed_date must fail"
    c.patch(f"/projects/{pid}/modules/work_order/{pm_wo['id']}",
            json={"completed_date": today.isoformat()})
    done = _act(c, pid, "work_order", pm_wo["id"], "complete")
    assert done["workflow_state"] == "completed", done["workflow_state"]

    cor = _create(c, pid, "work_order", {"subject": "Leaking valve rm 210",
        "wo_type": "Corrective", "priority": "High",
        "due_date": (today - timedelta(days=3)).isoformat()})

    k = c.get(f"/projects/{pid}/cmms/kpis").json()
    assert k["total"] == 2 and k["open"] == 1 and k["overdue"] == 1, k
    assert k["open_by_priority"].get("High") == 1, k["open_by_priority"]
    assert k["pm_compliance_pct"] == 100.0, k["pm_compliance_pct"]   # PM done on/before due

    # --- energy: meters + readings -> kBtu, monthly trend, EUI ---------------------------------
    elec = _create(c, pid, "meter", {"subject": "Main electric", "utility": "Electric",
                                     "unit": "kWh"})
    gas = _create(c, pid, "meter", {"subject": "Gas service", "utility": "Natural Gas",
                                    "unit": "therms"})
    water = _create(c, pid, "meter", {"subject": "Domestic water", "utility": "Water",
                                      "unit": "gallons"})
    for mo, kwh, thm in (("2026-01", 10000, 500), ("2026-02", 9000, 400)):
        _create(c, pid, "meter_reading", {"subject": f"elec {mo}", "meter": elec["id"],
            "reading_date": f"{mo}-28", "consumption": kwh, "cost": kwh * 0.12})
        _create(c, pid, "meter_reading", {"subject": f"gas {mo}", "meter": gas["id"],
            "reading_date": f"{mo}-28", "consumption": thm, "cost": thm * 1.1})
    _create(c, pid, "meter_reading", {"subject": "water jan", "meter": water["id"],
        "reading_date": "2026-01-28", "consumption": 25000})

    e = c.get(f"/projects/{pid}/energy/actual", params={"gfa_sf": 50000}).json()
    # 19,000 kWh * 3.412 + 900 therms * 100 = 64,828 + 90,000 = 154,828 kBtu over 2 months
    assert e["total_kbtu"] == 154828, e["total_kbtu"]
    assert e["months_covered"] == 2 and len(e["monthly"]) == 2, e["monthly"]
    assert e["water_gallons"] == 25000, e["water_gallons"]
    # EUI = 154828 / 2 * 12 / 50000 = 18.6
    assert e["eui_kbtu_sf_yr"] == 18.6, e["eui_kbtu_sf_yr"]
    assert e["by_utility"]["Electric"]["consumption"] == 19000, e["by_utility"]

    # --- ENERGY STAR bridge: flagged off -> honest status, never a fabricated score ------------
    bs = c.get("/energy/benchmark-status").json()
    assert bs["enabled"] is False and "locally" in bs["message"], bs

print("OPERATIONS OK - PM generation due-only + idempotent (next_due advanced); WO workflow gated "
      "on completed_date; KPIs total=2 open=1 overdue=1 PM-compliance=100%; energy 154,828 kBtu / "
      "EUI 18.6 with water separate; benchmark bridge honestly disabled")
