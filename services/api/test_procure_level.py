"""PROCURE-LEVEL — QTO → buyout packages (with RFQ scope) + score returned quotes on price + coverage +
lead time. Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_procure_level.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_procure_level.db"
os.environ["STORAGE_DIR"] = "./test_storage_proclvl"
os.environ.pop("AEC_RBAC", None)

from aec_api import procurement as pr  # noqa: E402

# --- buyout packaging: QTO lines grouped by trade, each with an RFQ scope --------------------------
qto = [
    {"item": "rebar #5", "qty": 100, "unit": "kg", "trade": "Concrete", "cost": 5000},
    {"item": "3000psi concrete", "qty": 50, "unit": "cy", "trade": "Concrete", "unit_price": 150},  # 7500
    {"item": "MC duct", "qty": 200, "unit": "lf", "trade": "HVAC", "cost": 4000},
]
bp = pr.buyout_packages(qto, by="trade")
assert bp["package_count"] == 2 and bp["grouped_by"] == "trade", bp
assert bp["packages"][0]["package"] == "Concrete", bp                 # highest est_cost first
assert bp["packages"][0]["est_cost"] == 12500.0, bp                   # 5000 + 50×150
assert bp["total_est_cost"] == 16500.0, bp
assert len(bp["packages"][0]["rfq_scope"]) == 2, bp                   # two scope lines to send out
assert {s["item"] for s in bp["packages"][0]["rfq_scope"]} == {"rebar #5", "3000psi concrete"}, bp

# --- quote scoring for one package: price + coverage + lead time -----------------------------------
scope = [{"item": "rebar", "qty": 100, "unit": "kg"},
         {"item": "concrete", "qty": 50, "unit": "cy"},
         {"item": "formwork", "qty": 200, "unit": "sf"}]
quotes = [
    {"supplier": "Ace", "lead_time_days": 10, "lines": [       # full coverage, cheaper, faster
        {"item": "rebar", "unit_price": 2}, {"item": "concrete", "unit_price": 100},
        {"item": "formwork", "unit_price": 5}]},
    {"supplier": "BuildCo", "lead_time_days": 20, "lines": [   # misses formwork, pricier, slower
        {"item": "rebar", "unit_price": 3}, {"item": "concrete", "unit_price": 90}]},
]
r = pr.score_quotes(scope, quotes)
assert r["scope_lines"] == 3 and r["supplier_count"] == 2, r
assert r["best_value_supplier"] == "Ace", r
ace, bc = r["suppliers"][0], r["suppliers"][1]
assert ace["supplier"] == "Ace" and ace["coverage_pct"] == 1.0, ace
assert ace["covered_ext"] == 6200.0 and ace["score"] == 1.0, ace     # 100×2 + 50×100 + 200×5
assert bc["coverage_pct"] == round(2 / 3, 4) and bc["scope_gaps"] == ["formwork"], bc
assert bc["score"] < ace["score"], (ace, bc)                          # penalized on coverage + price + lead
# per-item low prices across suppliers
low = {it["item"]: it["low_supplier"] for it in r["items"]}
assert low["rebar"] == "Ace" and low["concrete"] == "BuildCo" and low["formwork"] == "Ace", r["items"]

# no lead times → lead weight folds into price + coverage (scores still rank the cheaper/fuller bid first)
r2 = pr.score_quotes(scope, [{"supplier": "X", "lines": q["lines"]} for q in quotes])
assert r2["weights"]["lead_time"] == 0.0 and r2["best_value_supplier"] == "X", r2

# --- routes ----------------------------------------------------------------------------------------
if os.path.exists("./test_procure_level.db"):
    os.remove("./test_procure_level.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Buyout"}).json()["id"]
    b = c.post(f"/projects/{pid}/procurement/buyout-packages", json={"qto_lines": qto, "by": "trade"})
    assert b.status_code == 200 and b.json()["package_count"] == 2, b.text
    lv = c.post(f"/projects/{pid}/procurement/level", json={"scope": scope, "quotes": quotes})
    assert lv.status_code == 200, lv.text
    assert lv.json()["best_value_supplier"] == "Ace", lv.json()

print("PROCURE-LEVEL OK - QTO line items group into buyout packages (Concrete $12.5k > HVAC $4k, each with "
      "an RFQ scope of item/qty/unit to send out); returned quotes for a package are scored against the RFQ "
      "scope on price (extended over scope qty), coverage completeness, and lead time → Ace (full coverage, "
      "cheaper, faster) beats BuildCo (misses formwork), with per-item low prices surfaced and lead-time "
      "weight folding into price+coverage when no lead times are given; both routes return 200.")
