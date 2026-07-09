"""Earned Value Management engine (E1+E2): the unified metric set (PV/EV/AC/BAC, CV/SV/CPI/SPI) joined
by cost code, plus the EAC/ETC/VAC/TCPI forecast family and the control-account breakdown.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_evm.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_evm.db"
os.environ["STORAGE_DIR"] = "./test_storage_evm"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_evm.db",):
    if os.path.exists(_f):
        os.remove(_f)

from datetime import date, timedelta                  # noqa: E402

from fastapi.testclient import TestClient              # noqa: E402
from aec_api.main import app                           # noqa: E402


def _mk(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()["id"]


with TestClient(app) as c:
    today = date.today()
    pid = c.post("/projects", json={"name": "EVM Tower"}).json()["id"]

    cc1 = _mk(c, pid, "cost_code", {"code": "03-30", "description": "Concrete", "division": "03"})
    cc2 = _mk(c, pid, "cost_code", {"code": "04-20", "description": "Masonry", "division": "04"})

    # A1 (Concrete): budget 100k, 50% done, window today-10..today+10 -> planned 0.5 -> EV=PV=50k
    _mk(c, pid, "schedule_activity", {"name": "Place slab", "cost_code": cc1, "budget": 100000, "percent": 50,
        "start": str(today - timedelta(days=10)), "finish": str(today + timedelta(days=10))})
    # A2 (Masonry): budget 100k, 25% done, window today-30..today-10 (past finish) -> planned 1.0
    _mk(c, pid, "schedule_activity", {"name": "Lay CMU", "cost_code": cc2, "budget": 100000, "percent": 25,
        "start": str(today - timedelta(days=30)), "finish": str(today - timedelta(days=10))})
    # actual costs by cost code: concrete 60k, masonry 20k -> AC total 80k
    _mk(c, pid, "direct_cost", {"description": "Concrete invoices", "cost_code": cc1, "amount": 60000})
    _mk(c, pid, "direct_cost", {"description": "Masonry invoices", "cost_code": cc2, "amount": 20000})

    t = c.get(f"/projects/{pid}/evm").json()
    m = t["totals"]
    # measured
    assert m["bac"] == 200000 and m["ev"] == 75000 and m["pv"] == 150000 and m["ac"] == 80000, m
    # variances + indices
    assert m["cv"] == -5000 and m["sv"] == -75000, m                    # CV=EV-AC, SV=EV-PV
    assert m["cpi"] == 0.938 and m["spi"] == 0.5, (m["cpi"], m["spi"])  # 75/80, 75/150
    assert m["cpi_band"] == "concerning" and m["spi_band"] == "critical", m
    assert m["percent_complete"] == 37.5 and m["percent_spent"] == 40.0, m

    # forecast family
    f = m["forecast"]
    assert f["eac"]["cpi"] == round(200000 / 0.938, 2), f["eac"]        # BAC/CPI
    assert f["eac"]["at_plan"] == 205000, f["eac"]                      # AC+(BAC-EV) = 80k+125k
    # AC + (BAC-EV)/(CPI*SPI) = 80000 + 125000/(0.938*0.5)
    assert abs(f["eac"]["cpi_spi"] - (80000 + 125000 / (0.938 * 0.5))) < 1.0, f["eac"]
    assert f["eac_working"] == f["eac"]["cpi_spi"], f                   # working EAC = the CPI*SPI variant
    assert abs(f["etc"] - (f["eac_working"] - 80000)) < 0.01, f         # ETC = EAC-AC
    assert abs(f["vac"] - (200000 - f["eac_working"])) < 0.01, f        # VAC = BAC-EAC (negative overrun)
    assert f["tcpi_bac"] == round(125000 / 120000, 3), f["tcpi_bac"]    # (BAC-EV)/(BAC-AC)
    assert f["tcpi_warning"] is True, f                                 # TCPI(1.042) - CPI(0.938) > 0.10

    # control accounts: masonry behind schedule (SPI 0.25) but under cost (CPI 1.25); concrete over cost
    cas = {row["cost_code"].split(" · ")[0]: row for row in t["control_accounts"]}
    assert cas["03-30"]["cpi"] == round(50000 / 60000, 3) and cas["03-30"]["spi"] == 1.0, cas["03-30"]
    assert cas["04-20"]["cpi"] == 1.25 and cas["04-20"]["spi"] == 0.25, cas["04-20"]
    assert cas["03-30"]["cv"] == -10000 and cas["04-20"]["sv"] == -75000, cas

print("EVM OK - unified metrics BAC 200k / EV 75k / PV 150k / AC 80k -> CV -5k, SV -75k, CPI 0.938 "
      "(concerning), SPI 0.5 (critical); forecast family EAC(cpi/at-plan/cpi*spi) + ETC + VAC + TCPI "
      "with >1.10 warning; control accounts join schedule EV with cost AC by cost code (concrete over "
      "cost, masonry behind schedule).")
