"""ABSORPTION-SELLOUT + LOT-SUPPLY-INDEX — revenue-side underwriting levers: absorption-phased sell-out
schedule + the months-of-supply / Lot Supply Index.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_absorption.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_absorption.db"
os.environ["STORAGE_DIR"] = "./test_storage_absorption"
os.environ.pop("AEC_RBAC", None)

from aec_api import absorption as ab  # noqa: E402

# --- sell-out schedule -----------------------------------------------------------------------------
r = ab.sellout(units=100, absorption_per_month=10, avg_price=500_000, monthly_carry=20_000)
assert r["months_to_sellout"] == 10 and r["years_to_sellout"] == 0.83, r
assert r["total_revenue"] == 50_000_000 and r["total_carry"] == 200_000, r
assert r["avg_monthly_revenue"] == 5_000_000, r
assert len(r["schedule"]) == 10, r
assert r["schedule"][0] == {"month": 1, "units_sold": 10, "revenue": 5_000_000,
                            "cumulative_units": 10, "cumulative_revenue": 5_000_000, "remaining_units": 90}, r["schedule"][0]
assert r["schedule"][-1]["remaining_units"] == 0, r["schedule"][-1]

# a non-even last month sells the remainder
r2 = ab.sellout(units=25, absorption_per_month=10, avg_price=400_000)
assert r2["months_to_sellout"] == 3 and r2["schedule"][-1]["units_sold"] == 5, r2

# absorption 0 → can't phase a sell-out
assert ab.sellout(units=50, absorption_per_month=0, avg_price=100).get("months_to_sellout") is None

# --- Lot Supply Index ------------------------------------------------------------------------------
over = ab.lot_supply_index(vdl=1200, monthly_absorption=100)          # 12 mo supply → LSI 200
assert over["months_of_supply"] == 12.0 and over["lsi"] == 200 and over["band"] == "oversupplied", over
under = ab.lot_supply_index(vdl=300, monthly_absorption=100)          # 3 mo → LSI 50
assert under["lsi"] == 50 and under["band"] == "undersupplied", under
bal = ab.lot_supply_index(vdl=600, monthly_absorption=100)            # 6 mo → LSI 100
assert bal["lsi"] == 100 and bal["band"] == "balanced", bal
assert ab.lot_supply_index(vdl=100, monthly_absorption=0)["band"] == "unknown"

# --- routes ----------------------------------------------------------------------------------------
if os.path.exists("./test_absorption.db"):
    os.remove("./test_absorption.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    assert c.post("/projects/nope/feasibility/sellout", json={"units": 10}).status_code == 404
    pid = c.post("/projects", json={"name": "Feas"}).json()["id"]
    s = c.post(f"/projects/{pid}/feasibility/sellout",
               json={"units": 100, "absorption_per_month": 10, "avg_price": 500_000, "monthly_carry": 20_000})
    assert s.status_code == 200 and s.json()["months_to_sellout"] == 10, s.text
    l = c.post(f"/projects/{pid}/feasibility/lot-supply", json={"vdl": 1200, "monthly_absorption": 100})
    assert l.status_code == 200 and l.json()["band"] == "oversupplied", l.text

print("ABSORPTION-SELLOUT + LOT-SUPPLY-INDEX OK - 100 units at 10/month × $500k phase over a 10-month "
      "sell-out ($50M revenue, $200k carry over the window, 0.83 yr), with the last month selling the "
      "remainder on an uneven mix; absorption 0 can't be phased. The Lot Supply Index reads VDL ÷ absorption "
      "as months of supply indexed to a 6-month equilibrium: 12 mo → LSI 200 oversupplied, 3 mo → 50 "
      "undersupplied, 6 mo → 100 balanced; both /feasibility routes 404 on a missing project.")
