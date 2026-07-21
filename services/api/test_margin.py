"""MARGIN-CBS — per-cost-code reconciliation: budget vs committed vs actual vs billed, with buyout margin
(budget − committed), variance (budget − actual), and over-committed/over-budget flags, worst-first.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_margin.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_margin.db"
os.environ["STORAGE_DIR"] = "./test_storage_margin"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_margin.db"):
    os.remove("./test_margin.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "GC job"}).json()["id"]

    def mk(key, data):
        return c.post(f"/projects/{pid}/modules/{key}", json={"data": data}).json()

    # two cost codes: 03 30 00 (bought out UNDER budget), 09 20 00 (committed OVER budget)
    cc1 = mk("cost_code", {"code": "03 30 00", "description": "Cast-in-place concrete"})["id"]
    cc2 = mk("cost_code", {"code": "09 20 00", "description": "Plaster & gypsum board"})["id"]

    mk("budget", {"cost_code": cc1, "description": "Concrete", "revised": 100000})
    mk("budget", {"cost_code": cc2, "description": "Drywall", "revised": 50000})
    mk("commitment", {"cost_code": cc1, "description": "Concrete sub", "amount": 85000})   # −15k under → +15k margin
    mk("commitment", {"cost_code": cc2, "description": "Drywall sub", "amount": 55000})    # +5k over → −5k margin
    mk("direct_cost", {"cost_code": cc1, "description": "Pour 1", "amount": 40000})
    mk("direct_cost", {"cost_code": cc2, "description": "Board 1", "amount": 20000})
    mk("sub_invoice", {"cost_code": cc1, "vendor": "Concrete sub", "amount": 35000})

    j = c.get(f"/projects/{pid}/margin/by-costcode")
    assert j.status_code == 200, j.text[:200]
    m = j.json()
    assert m["code_count"] == 2, m
    by = {r["cost_code"].split(" · ")[0]: r for r in m["rows"]}
    # CC1 — bought out under budget
    a = by["03 30 00"]
    assert a["budget"] == 100000 and a["committed"] == 85000 and a["actual"] == 40000 and a["billed"] == 35000, a
    assert a["buyout_margin"] == 15000 and a["variance"] == 60000, a
    assert a["over_committed"] is False and a["over_budget"] is False and a["pct_committed"] == 85.0, a
    # CC2 — committed over budget → negative buyout margin + over-committed flag
    b = by["09 20 00"]
    assert b["buyout_margin"] == -5000 and b["over_committed"] is True and b["over_budget"] is False, b
    # UX-ACT: the over-committed code carries a one-click "Review commitments" action filtered to its code;
    # the healthy code carries none
    assert a["actions"] == [], a["actions"]
    act = b["actions"]
    assert any(x["kind"] == "open_module" and x["module"] == "commitment" and x.get("q") == "09 20 00"
               for x in act), act
    # rows sorted worst-margin first → CC2 (−5k) before CC1 (+15k)
    assert [r["cost_code"].split(" · ")[0] for r in m["rows"]] == ["09 20 00", "03 30 00"], m["rows"]
    # totals
    assert m["total_budget"] == 150000 and m["total_committed"] == 140000, m
    assert m["total_buyout_margin"] == 10000 and m["total_variance"] == 90000, m
    assert m["over_committed_codes"] == 1 and m["over_budget_codes"] == 0, m

    # empty project → zeroed rollup, no crash; unknown project → 404
    pid2 = c.post("/projects", json={"name": "Empty"}).json()["id"]
    e = c.get(f"/projects/{pid2}/margin/by-costcode").json()
    assert e["code_count"] == 0 and e["total_buyout_margin"] == 0.0 and e["rows"] == [], e
    assert c.get("/projects/no-such/margin/by-costcode").status_code == 404

print("MARGIN-CBS OK - per-cost-code reconciliation ties budget/committed/actual/billed together: 03 30 00 "
      "bought out under budget ($100k budget, $85k committed → +$15k buyout margin, $60k variance, 85%% "
      "committed), 09 20 00 committed over budget ($50k vs $55k → −$5k margin, over-committed flag); rows "
      "sort worst-margin first; totals $150k budget / $140k committed / +$10k buyout margin / 1 over-committed "
      "code; empty project zeroes and unknown 404s.")
