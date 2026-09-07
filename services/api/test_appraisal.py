"""Tri-approach appraisal engine — each approach + reconciliation are correct and override-able.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_appraisal.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./_test_appraisal.db"
os.environ.setdefault("STORAGE_DIR", "./_storage_test_appraisal")

from aec_api import appraisal as ap  # noqa: E402

# --- cost approach: RCN × (1−dep) + land --------------------------------------
c = ap.cost_approach(20_000_000, land_value=4_000_000, depreciation_pct=0.0)
assert c["value"] == 24_000_000, c
c2 = ap.cost_approach(20_000_000, land_value=4_000_000, depreciation_pct=0.10)
assert c2["value"] == 22_000_000 and c2["depreciation_amount"] == 2_000_000, c2

# --- income approach: NOI / cap ----------------------------------------------
i = ap.income_approach(1_200_000, 0.06)
assert i["value"] == 20_000_000, i
assert ap.income_approach(1_200_000, 0.0)["value"] == 0   # no cap → no divide-by-zero

# --- sales comparison: median $/SF × subject SF; derive psf from price; fallback ---
comps = [{"price_psf": 300}, {"price_psf": 320}, {"price": 5_000_000}]   # 3rd derives psf from price
s = ap.sales_comparison(20_000, comps)
assert s["basis"] == "$/SF" and s["median_price_psf"] == 300.0, s   # median(300,320,250)=300
assert s["value"] == 300.0 * 20_000, s
# $/unit basis when SF absent but units present
su = ap.sales_comparison(0, [{"price": 9_000_000, "num_units": 30}, {"price": 11_000_000, "num_units": 40}],
                         subject_units=35)
assert su["basis"] == "$/unit" and su["value"] > 0, su
# raw-price fallback when neither SF nor units
sp = ap.sales_comparison(0, [{"price": 5_000_000}, {"price": 7_000_000}])
assert sp["basis"] == "median price" and sp["value"] == 6_000_000, sp
# implied cap accepts 6 or 0.06
sc = ap.sales_comparison(20_000, [{"price_psf": 300, "cap_rate": 6}, {"price_psf": 300, "cap_rate": 0.05}])
assert sc["implied_cap_rate"] and 0.04 < sc["implied_cap_rate"] < 0.07, sc

# --- reconcile: weighted, drops zero-value approaches, normalizes -------------
rec = ap.reconcile({"cost": c, "income": i, "sales_comparison": s})
assert set(rec["approaches_used"]) == {"cost", "income", "sales_comparison"}, rec
assert abs(sum(x["weight"] for x in rec["contributions"]) - 1.0) < 1e-6, rec
# default weights income .5 / sales .3 / cost .2 over values 20M / 20M / 6M
expect = 0.5 * 20_000_000 + 0.3 * 6_000_000 + 0.2 * 24_000_000
assert abs(rec["value"] - expect) < 1.0, (rec["value"], expect)
# a zero-value approach is dropped and weights renormalize
rec2 = ap.reconcile({"cost": c, "income": ap.income_approach(1_200_000, 0.0)})
assert rec2["approaches_used"] == ["cost"] and rec2["value"] == 24_000_000, rec2
# custom weights override
rec3 = ap.reconcile({"income": i, "cost": c}, weights={"income": 1.0, "cost": 0.0})
assert rec3["value"] == 20_000_000, rec3
# range/spread reported
assert rec["range"]["high"] >= rec["range"]["low"] and rec["range"]["spread_pct"] >= 0, rec["range"]

print(f"APPRAISAL OK - cost ${c['value']:,.0f} + income ${i['value']:,.0f} + sales ${s['value']:,.0f} "
      f"-> reconciled ${rec['value']:,.0f}; weights normalize; zero-value approaches dropped; overrides honored")
