"""Work-in-Progress schedule — percentage-of-completion (cost-to-cost) → earned revenue vs billed →
over/under-billing (contract liability / asset), retainage, gross profit, backlog; plus the portfolio
WIP. The accounting twin to the earned-value module.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_wip.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_wip.db"
os.environ["STORAGE_DIR"] = "./test_storage_wip"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_wip.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient                # noqa: E402
from aec_api.main import app                             # noqa: E402


def _mk(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()["id"]


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "WIP Tower"}).json()["id"]
    cc = _mk(c, pid, "cost_code", {"code": "03-30", "description": "Concrete", "division": "03"})
    _mk(c, pid, "budget", {"cost_code": cc, "description": "Concrete", "revised": 800000})
    c.post(f"/projects/{pid}/cost/sov/from-budget?replace=true")        # SOV scheduled 800k
    _mk(c, pid, "prime_contract", {"name": "GMP", "type": "GMP", "value": 1000000})
    _mk(c, pid, "direct_cost", {"description": "Concrete cost", "cost_code": cc, "amount": 400000})  # 50% of 800k
    _mk(c, pid, "owner_invoice", {"number": "INV-1", "amount": 300000, "period": "2026-06"})         # billed 300k

    # --- under-billed: earned 500k (50% × 1M) > billed 300k → 200k contract asset ----------------
    w = c.get(f"/projects/{pid}/wip").json()
    assert w["estimated_cost"] == 800000 and w["cost_to_date"] == 400000, w
    assert w["percent_complete"] == 50.0, w["percent_complete"]        # cost-to-cost
    assert w["contract_value"] == 1000000, w["contract_value"]
    assert w["earned_revenue"] == 500000, w["earned_revenue"]          # 50% × 1M
    assert w["billed_to_date"] == 300000, w["billed_to_date"]
    assert w["under_billing"] == 200000 and w["over_billing"] == 0, w  # earned − billed (asset)
    assert w["billing_status"] == "under-billed", w["billing_status"]
    assert w["gross_profit"] == 200000 and w["gross_margin_pct"] == 20.0, w  # 1M − 800k
    assert w["profit_to_date"] == 100000, w["profit_to_date"]          # earned − cost
    assert w["backlog"] == 700000, w["backlog"]                        # 1M − 300k billed
    assert w["retainage"] > 0, w["retainage"]

    # --- flip to over-billed: bill another 400k → billed 700k > earned 500k → 200k liability ------
    _mk(c, pid, "owner_invoice", {"number": "INV-2", "amount": 400000, "period": "2026-07"})
    w2 = c.get(f"/projects/{pid}/wip").json()
    assert w2["billed_to_date"] == 700000, w2["billed_to_date"]
    assert w2["over_billing"] == 200000 and w2["under_billing"] == 0, w2   # billed − earned (liability)
    assert w2["billing_status"] == "over-billed", w2["billing_status"]

    # --- portfolio WIP: one row, totals aggregate -------------------------------------------------
    pf = c.get("/wip/portfolio").json()
    assert pf["project_count"] == 1 and pf["projects"][0]["over_billing"] == 200000, pf
    assert pf["totals"]["contract_value"] == 1000000, pf["totals"]

    # --- WIP report PDF ---------------------------------------------------------------------------
    rep = c.get(f"/projects/{pid}/reports/wip.pdf")
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF", (rep.status_code, rep.content[:8])

print("WIP OK - percentage-of-completion 50% (cost 400k / est 800k) -> earned 500k (50% of 1M contract); "
      "under-billed 200k (contract asset) at 300k billed, flips to over-billed 200k (liability) at 700k; "
      "gross profit 200k @ 20% margin, backlog 700k, retainage tracked; portfolio WIP + report PDF.")
