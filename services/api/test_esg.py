"""ESG rollup + POE (RIBA Stage 7 feedback loop) — GHG scopes, certifications, EUI gap, report.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_esg.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_esg.db"
os.environ["STORAGE_DIR"] = "./test_storage_esg"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("AEC_GRID_KGCO2E_PER_KWH", None)
for _f in ("./test_esg.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient              # noqa: E402
from aec_api.main import app                           # noqa: E402


def _create(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # meters + a year of monthly-ish readings (2 months is enough to annualize)
    elec = _create(c, pid, "meter", {"subject": "Main electric", "utility": "Electric", "unit": "kWh"})
    gas = _create(c, pid, "meter", {"subject": "Gas", "utility": "Natural Gas", "unit": "therms"})
    for mo, kwh, thm in (("2026-01", 10000, 500), ("2026-02", 10000, 500)):
        _create(c, pid, "meter_reading", {"subject": f"e {mo}", "meter": elec["id"],
                                          "reading_date": f"{mo}-28", "consumption": kwh})
        _create(c, pid, "meter_reading", {"subject": f"g {mo}", "meter": gas["id"],
                                          "reading_date": f"{mo}-28", "consumption": thm})
    # certification tracking + a reported POE with a design EUI
    _create(c, pid, "leed_credit", {"credit": "Optimize Energy Performance", "category": "Energy",
                                    "points_targeted": 10, "points_achieved": 6})
    p1 = _create(c, pid, "poe", {"subject": "Year-1 POE", "survey_date": "2026-06-01",
        "level": "2 - Investigative (survey + metered data)", "occupants_surveyed": 40,
        "satisfaction_score": 5.2, "design_eui": 40})
    c.post(f"/projects/{pid}/modules/poe/{p1['id']}/transition", json={"action": "start_fieldwork"})
    r = c.post(f"/projects/{pid}/modules/poe/{p1['id']}/transition", json={"action": "publish_report"})
    assert r.status_code == 400, "publish without findings must fail"
    c.patch(f"/projects/{pid}/modules/poe/{p1['id']}", json={"findings": "Comfort OK; EUI above design."})
    r = c.post(f"/projects/{pid}/modules/poe/{p1['id']}/transition", json={"action": "publish_report"})
    assert r.status_code == 200, r.text[:160]

    e = c.get(f"/projects/{pid}/esg", params={"gfa_sf": 20000}).json()
    ghg = e["performance"]["ghg"]
    # Scope 1: 1000 therms * 5.30 = 5.3 t; Scope 2: 20,000 kWh * 0.386 = 7.72 t
    assert ghg["scope1_tco2e"] == 5.3 and ghg["scope2_tco2e"] == 7.7, ghg
    assert ghg["total_tco2e"] == 13.0, ghg["total_tco2e"]
    # EUI: (20,000*3.412 + 1000*100) = 168,240 kBtu over 2 months -> *6 / 20,000 sf = 50.5
    assert e["performance"]["energy"]["eui_kbtu_sf_yr"] == 50.5, e["performance"]["energy"]
    assert e["certifications"]["points_targeted"] == 10 and e["certifications"]["points_achieved"] == 6
    poe = e["poe"]["latest"]
    assert e["poe"]["reported"] == 1 and poe["design_eui"] == 40, e["poe"]
    assert poe["eui_gap_pct"] == 26.2, poe["eui_gap_pct"]   # (50.5-40)/40, rounded 0.1

    # grid-factor override changes Scope 2 (deployment-local eGRID factor)
    os.environ["AEC_GRID_KGCO2E_PER_KWH"] = "0.2"
    e2 = c.get(f"/projects/{pid}/esg", params={"gfa_sf": 20000}).json()
    assert e2["performance"]["ghg"]["scope2_tco2e"] == 4.0, e2["performance"]["ghg"]
    os.environ.pop("AEC_GRID_KGCO2E_PER_KWH", None)

    # Report Center entry renders (PDF)
    cat = c.get("/reports").json()["reports"]
    assert any(x["id"] == "esg" for x in cat), "esg missing from report catalog"
    r = c.get(f"/projects/{pid}/reports/esg.pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF", (r.status_code, r.content[:8])

print("ESG OK - GHG Scope1 5.3t + Scope2 7.7t (0.2-factor override -> 4.0t), EUI 50.4 vs design 40 "
      "(+26% gap) via reported POE (findings-gated), 6/10 LEED points, esg report PDF served")
