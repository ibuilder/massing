"""GC project budget (GMP): direct trades + GC/GR + staffing + overhead/fee/contingency, relational
to cost codes, commitments, bid packages, the prime contract, and the developer proforma hard cost.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_project_budget.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_project_budget.db"
os.environ["STORAGE_DIR"] = "./test_storage_pb"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_project_budget.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402


def mk(c, pid, key, data):
    return c.post(f"/projects/{pid}/modules/{key}", json={"data": data}).json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "GMP Tower"}).json()["id"]

    # cost codes: one trade (Div 03 Concrete), one general requirement (Div 01)
    cc_conc = mk(c, pid, "cost_code", {"code": "03-3000", "description": "Concrete", "division": "03"})["id"]
    cc_gr = mk(c, pid, "cost_code", {"code": "01-5000", "description": "Temp facilities", "division": "01"})["id"]

    # budget lines per cost code (the PX's GMP allocation)
    # concrete keyed with a forecast (EAC $1.9M) below budget; temp facilities no forecast
    mk(c, pid, "budget", {"cost_code": cc_conc, "description": "Concrete", "revised": 2_000_000, "forecast": 1_900_000})
    mk(c, pid, "budget", {"cost_code": cc_gr, "description": "Temp facilities", "revised": 500_000})

    # buyout: an executed commitment + actual spend to date against concrete
    com = mk(c, pid, "commitment", {"description": "Concrete sub", "cost_code": cc_conc, "amount": 1_800_000})
    c.post(f"/projects/{pid}/modules/commitment/{com['id']}/transition", json={"action": "execute"})
    mk(c, pid, "direct_cost", {"description": "Concrete pours", "cost_code": cc_conc, "amount": 500_000})

    # staffing projections: PM under General Conditions, Safety under General Requirements
    mk(c, pid, "staffing", {"role": "Project Manager", "category": "General Conditions", "count": 1,
                            "rate": 25_000, "rate_period": "Month", "start": "2026-01-01", "finish": "2026-12-31"})
    mk(c, pid, "staffing", {"role": "Safety Manager", "category": "General Requirements", "count": 1,
                            "rate": 15_000, "rate_period": "Month", "start": "2026-01-01", "finish": "2026-12-31"})

    # prime contract = the agreed GMP + markup rates the PX set
    mk(c, pid, "prime_contract", {"name": "GMP w/ Owner", "type": "GMP", "value": 10_000_000,
                                  "overhead_pct": 5, "fee_pct": 4, "contingency_pct": 3})

    # a bid package + an awarded bid below budget → buyout savings
    bp = mk(c, pid, "bid_package", {"name": "Concrete", "trade": "Concrete", "budget": 2_000_000})
    mk(c, pid, "bid_submission", {"bidder": "Acme Concrete", "package": bp["id"],
                                  "amount": 1_750_000, "status": "Awarded"})

    # an approved change order adjusts the GMP (original + approved COs = revised)
    cor = mk(c, pid, "cor", {"subject": "Added topping slab", "cost_code": cc_conc, "amount": 75_000})
    c.post(f"/projects/{pid}/modules/cor/{cor['id']}/transition", json={"action": "submit"})
    c.post(f"/projects/{pid}/modules/cor/{cor['id']}/transition", json={"action": "approve"})

    # developer proforma hard cost (the construction line the GMP must reconcile against)
    c.put(f"/projects/{pid}/dev-budget", json={"lines": [
        {"category": "hard", "description": "Hard costs", "unit_cost": 3_200_000, "quantity": 1}]})

    b = c.get(f"/projects/{pid}/budget/gmp").json()
    cats = {c0["key"]: c0 for c0 in b["categories"]}
    assert set(cats) == {"direct", "general_requirements", "general_conditions", "overhead", "fee", "contingency"}, list(cats)

    # direct work: $2.0M budget, $1.8M committed (the executed sub), grouped under Division 03
    assert cats["direct"]["budget"] == 2_000_000 and cats["direct"]["committed"] == 1_800_000, cats["direct"]
    assert any(g["name"] == "Division 03" for g in cats["direct"]["groups"]), cats["direct"]["groups"]

    # cost-to-complete (EAC/ETC): concrete keyed at $1.9M EAC, $0.5M spent → $1.4M to go, VAC $0.1M
    conc = next(l for g in cats["direct"]["groups"] for l in g["lines"] if "Concrete" in l["name"])
    assert conc["eac"] == 1_900_000 and conc["actual"] == 500_000, conc
    assert conc["etc"] == 1_400_000 and conc["variance"] == 100_000, conc
    comp = b["completion"]
    assert comp["eac"] == b["totals"]["eac"] and comp["etc"] == round(comp["eac"] - comp["actual_to_date"], 2), comp
    assert comp["bac"] == b["totals"]["budget"] and comp["pct_spent"] > 0, comp

    # buyout savings: concrete awarded at $1.75M vs $2.0M package budget → $250k savings
    bo = b["buyout"]
    assert bo["packages"] == 1 and bo["bought_out"] == 1, bo
    assert bo["awarded"] == 1_750_000 and bo["savings"] == 250_000, bo

    # staffing rolls into the right buckets (PM→GC, Safety→GR); ~12 months each
    assert 280_000 < cats["general_conditions"]["budget"] < 320_000, cats["general_conditions"]["budget"]
    assert cats["general_requirements"]["budget"] > 500_000, cats["general_requirements"]["budget"]   # 500k temp + safety

    cow = b["gmp"]["cost_of_work"]
    assert cats["overhead"]["budget"] == round(cow * 0.05, 2), (cats["overhead"]["budget"], cow)
    assert cats["fee"]["budget"] == round((cow + cats["overhead"]["budget"]) * 0.04, 2), cats["fee"]["budget"]
    assert cats["contingency"]["budget"] == round(2_000_000 * 0.03, 2), cats["contingency"]["budget"]

    # approved change order → revised GMP (original + $75k)
    assert b["gmp"]["approved_changes"] == 75_000, b["gmp"]
    assert b["gmp"]["revised"] == round(b["gmp"]["computed"] + 75_000, 2), b["gmp"]

    # GMP reconciliation + proforma tie
    assert b["gmp"]["computed"] == b["totals"]["budget"], (b["gmp"]["computed"], b["totals"]["budget"])
    assert b["gmp"]["contract_value"] == 10_000_000 and b["gmp"]["reconciliation"] is not None
    assert b["proforma"]["hard_cost"] == 3_200_000, b["proforma"]
    assert b["proforma"]["gmp_vs_hard"] == round(b["gmp"]["computed"] - 3_200_000, 2), b["proforma"]
    assert len(b["bid_packages"]) == 1 and b["staffing"]["projected"] > 0, (b["bid_packages"], b["staffing"])

    # owner pay-app SOV seeded from the GMP — the G702/G703 draws from the same budget lines
    seed = c.post(f"/projects/{pid}/cost/sov/from-budget").json()
    assert seed["created"] > 0 and abs(seed["scheduled_value"] - b["totals"]["budget"]) < 1.0, seed
    g703 = c.get(f"/projects/{pid}/cost/g703").json()
    assert abs(g703["totals"]["scheduled"] - b["totals"]["budget"]) < 1.0, g703["totals"]   # SOV = GMP
    sov = c.get(f"/projects/{pid}/modules/sov").json()
    assert any(s["data"].get("cost_code") for s in sov), "direct SOV lines carry their cost-code link"
    # idempotent without replace; rebuilds with replace
    assert c.post(f"/projects/{pid}/cost/sov/from-budget").json()["created"] == 0
    assert c.post(f"/projects/{pid}/cost/sov/from-budget?replace=true").json()["created"] == seed["created"]

    # cost-loaded schedule → monthly cash-flow / draw curve (on-schedule × on-budget)
    mk(c, pid, "schedule_activity", {"name": "Foundations", "cost_code": cc_conc,
                                     "budget": 600_000, "start": "2026-02-01", "finish": "2026-04-30"})
    mk(c, pid, "schedule_activity", {"name": "Superstructure", "cost_code": cc_conc,
                                     "budget": 1_200_000, "start": "2026-04-01", "finish": "2026-09-30"})
    cf = c.get(f"/projects/{pid}/budget/cashflow").json()
    assert cf["loaded_activities"] == 2 and cf["total"] == 1_800_000, cf
    assert cf["months"] >= 6 and cf["series"][-1]["pct"] == 100.0, cf["series"][-1]
    cums = [m["cumulative"] for m in cf["series"]]
    assert cums == sorted(cums) and abs(cums[-1] - 1_800_000) < 1, cums          # monotonic S-curve

    # budget baseline + variance: snapshot, then grow a cost code → variance shows the movement
    assert c.get(f"/projects/{pid}/budget/variance").status_code == 409   # none set yet
    base = c.post(f"/projects/{pid}/budget/baseline").json()
    assert base["gmp_computed"] == b["totals"]["budget"], base
    var0 = c.get(f"/projects/{pid}/budget/variance").json()
    assert var0["total_delta"] == 0 and var0["lines"] == [], var0          # no drift right after baseline
    mk(c, pid, "budget", {"cost_code": cc_gr, "description": "Extra temp power", "revised": 120_000})
    var = c.get(f"/projects/{pid}/budget/variance").json()
    # the $120k line/category delta is exact; the GMP total also picks up the OH+fee markup cascade
    assert any(l["code"] == "01-5000" and l["delta"] == 120_000 for l in var["lines"]), var["lines"]
    assert any(c0["key"] == "general_requirements" and c0["delta"] == 120_000 for c0 in var["categories"]), var["categories"]
    assert var["total_delta"] >= 120_000, var["total_delta"]

    print(f"PROJECT BUDGET OK - GMP computed ${b['gmp']['computed']:,.0f} (cost of work ${cow:,.0f}); "
          f"direct/GC/GR + OH/fee/contingency; bid packages + staffing + proforma reconciled; "
          f"owner SOV seeded from budget ({seed['created']} lines = ${seed['scheduled_value']:,.0f})")
