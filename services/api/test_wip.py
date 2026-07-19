"""Work-in-Progress schedule — percentage-of-completion (cost-to-cost) → earned revenue vs billed →
over/under-billing (contract liability / asset), retainage, gross profit, backlog; plus the portfolio
WIP. The accounting twin to the earned-value module.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_wip.py"""
import json
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_wip.db"
os.environ["STORAGE_DIR"] = "./test_storage_wip"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_wip.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402


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

    # --- contractor statements: POC income statement + contract position -------------------------
    st = c.get(f"/projects/{pid}/contractor-statements").json()
    inc, pos = st["income_statement"], st["contract_position"]
    assert inc["revenue_earned"] == 500000 and inc["cost_of_revenue"] == 400000, inc
    assert inc["gross_profit"] == 100000 and inc["gross_margin_pct"] == 20.0, inc
    assert pos["contract_liability_overbillings"] == 200000 and pos["contract_asset_underbillings"] == 0, pos
    # net contract WC = under-billings(0) + retainage − over-billings(200k) − AP(0)  → negative here
    assert pos["net_contract_working_capital"] == round(pos["retainage_receivable"] - 200000, 2), pos
    cp = c.get("/contractor-statements/portfolio").json()
    assert cp["job_count"] == 1 and cp["income_statement"]["revenue_earned"] == 500000, cp

    # --- GL foundation: balanced double-entry journal + trial balance -----------------------------
    coa = c.get(f"/projects/{pid}/accounting/chart-of-accounts").json()
    assert {a["code"] for a in coa["accounts"]} >= {"1200", "2000", "4000", "5000", "2300"}, coa
    je = c.get(f"/projects/{pid}/accounting/journal-entries").json()
    assert je["balanced"] and je["debit_total"] == je["credit_total"], je
    tb = c.get(f"/projects/{pid}/accounting/trial-balance").json()
    assert tb["balanced"] and tb["debit_total"] == tb["credit_total"], tb
    acc = {a["code"]: a for a in tb["accounts"]}
    assert acc["5000"]["debit"] == 400000 and acc["2000"]["credit"] == 400000, tb   # cost → AP
    assert acc["1200"]["debit"] == 700000, acc["1200"]                              # billed → AR
    assert acc["4000"]["balance"] == 500000 and acc["4000"]["balance_side"] == "credit", acc["4000"]  # revenue nets to earned
    assert acc["2300"]["credit"] == 200000, acc["2300"]                            # over-billing → contract liability

    # --- model-derived physical % complete: an independent POC signal, keyed by IFC GlobalId --------
    # Seed a 4-element model (Qto NetVolume 10/20/30/40 = 100 total), then mark install status.
    PROPS = {"project": {"name": "WIP Tower"}, "elements": [
        {"guid": "e1", "ifc_class": "IfcWall", "storey": "L1", "qtos": {"Qto_WallBaseQuantities": {"NetVolume": 10}}},
        {"guid": "e2", "ifc_class": "IfcSlab", "storey": "L1", "qtos": {"Qto_SlabBaseQuantities": {"NetVolume": 20}}},
        {"guid": "e3", "ifc_class": "IfcColumn", "storey": "L2", "qtos": {"Qto_ColumnBaseQuantities": {"NetVolume": 30}}},
        {"guid": "e4", "ifc_class": "IfcBeam", "storey": "L2", "qtos": {"Qto_BeamBaseQuantities": {"NetVolume": 40}}},
    ]}
    c.post(f"/projects/{pid}/properties/index",
           files={"file": ("props.json", json.dumps(PROPS).encode(), "application/json")})
    c.put(f"/projects/{pid}/verification/e1", json={"status": "installed"})   # NetVolume 10
    c.put(f"/projects/{pid}/verification/e2", json={"status": "verified"})    # NetVolume 20

    # count-weighted: 2 of 4 installed = 50%; quantity-weighted: (10+20) of 100 = 30%
    mp = c.get(f"/projects/{pid}/wip/model-progress").json()
    assert mp["available"] and mp["total_elements"] == 4 and mp["installed_elements"] == 2, mp
    assert mp["percent_complete_count"] == 50.0 and mp["percent_complete"] == 50.0, mp
    mpq = c.get(f"/projects/{pid}/wip/model-progress?quantity=NetVolume").json()
    assert mpq["total_quantity"] == 100 and mpq["installed_quantity"] == 30, mpq
    assert mpq["percent_complete_quantity"] == 30.0 and mpq["percent_complete"] == 30.0, mpq

    # default WIP now carries a model cross-check block: physical 50% vs cost-to-cost 50% → aligned
    wm = c.get(f"/projects/{pid}/wip").json()
    assert wm["pct_method"] == "cost-to-cost" and wm["percent_complete"] == 50.0, wm
    assert wm["model"]["model_percent_complete"] == 50.0 and wm["model"]["cost_percent_complete"] == 50.0, wm["model"]
    assert wm["model"]["divergence_pct"] == 0.0 and wm["model"]["flag"] == "aligned", wm["model"]

    # drive POC by physical model progress instead of cost: earned = 50% × 1M = 500k (units-installed)
    wu = c.get(f"/projects/{pid}/wip?method=units-installed").json()
    assert wu["pct_method"] == "units-installed" and wu["percent_complete"] == 50.0, wu
    assert wu["earned_revenue"] == 500000, wu["earned_revenue"]        # physical-progress-based revenue

    # install one more element (e3) → physical 75% > cost 50% → 'physical-ahead', earned climbs to 750k
    c.put(f"/projects/{pid}/verification/e3", json={"status": "installed"})
    wm2 = c.get(f"/projects/{pid}/wip").json()
    assert wm2["model"]["model_percent_complete"] == 75.0 and wm2["model"]["flag"] == "physical-ahead", wm2["model"]
    wu2 = c.get(f"/projects/{pid}/wip?method=units-installed").json()
    assert wu2["percent_complete"] == 75.0 and wu2["earned_revenue"] == 750000, wu2

    # no model loaded on a fresh project → model progress unavailable (graceful), WIP has no model block
    pid2 = c.post("/projects", json={"name": "No Model"}).json()["id"]
    assert c.get(f"/projects/{pid2}/wip/model-progress").json()["available"] is False
    assert "model" not in c.get(f"/projects/{pid2}/wip").json()

    # --- report PDFs ------------------------------------------------------------------------------
    for _rep in ("wip", "contractor_financials"):
        rep = c.get(f"/projects/{pid}/reports/{_rep}.pdf")
        assert rep.status_code == 200 and rep.content[:4] == b"%PDF", (_rep, rep.status_code)

    # --- PERF-4 equivalence: trade AP is now a SQL SUM with exclude_states — same answer as the ----
    # old Python loop over every sub_invoice ("not in (paid, void)"; NULL/other states kept).
    ap_pid = c.post("/projects", json={"name": "AP Equiv"}).json()["id"]
    i1 = _mk(c, ap_pid, "sub_invoice", {"vendor": "Sub A", "amount": 10000})            # submitted
    i2 = _mk(c, ap_pid, "sub_invoice", {"vendor": "Sub B", "amount": 20000})
    c.post(f"/projects/{ap_pid}/modules/sub_invoice/{i2}/transition", json={"action": "approve"})
    i3 = _mk(c, ap_pid, "sub_invoice", {"vendor": "Sub C", "amount": 5000})
    for a in ("approve", "pay"):                                                        # paid → excluded
        c.post(f"/projects/{ap_pid}/modules/sub_invoice/{i3}/transition", json={"action": a})
    ap = c.get(f"/projects/{ap_pid}/contractor-statements").json()["contract_position"]
    assert ap["accounts_payable"] == 30000, ap                     # 10k submitted + 20k approved, not the 5k paid

print("WIP OK - percentage-of-completion 50% (cost 400k / est 800k) -> earned 500k (50% of 1M contract); "
      "under-billed 200k (contract asset) at 300k billed, flips to over-billed 200k (liability) at 700k; "
      "gross profit 200k @ 20% margin, backlog 700k, retainage tracked; portfolio WIP + report PDF. "
      "Model-derived physical %: installed elements / total by GlobalId (count 50%, NetVolume-weighted 30%); "
      "WIP model block cross-checks physical vs cost POC (aligned -> physical-ahead as installs grow); "
      "method=units-installed drives earned revenue by model progress (500k -> 750k).")
