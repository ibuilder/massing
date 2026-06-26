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

    # developer ↔ GC tie: reconcile the proforma hard cost against the live GMP (the REVISED GMP,
    # i.e. incl. approved change orders), then sync it
    revised_gmp = b["gmp"]["revised"]
    recon = c.get(f"/projects/{pid}/dev-budget/gmp-reconciliation").json()
    assert recon["dev_hard_cost"] == 3_200_000 and recon["gc_gmp"] == revised_gmp, recon
    assert recon["delta"] == round(revised_gmp - 3_200_000, 2) and recon["in_sync"] is False, recon
    sync = c.post(f"/projects/{pid}/dev-budget/sync-gmp").json()
    assert sync["synced"] and sync["hard_cost"] == revised_gmp, sync
    recon2 = c.get(f"/projects/{pid}/dev-budget/gmp-reconciliation").json()
    assert recon2["in_sync"] is True and recon2["dev_hard_cost"] == revised_gmp, recon2
    # sync replaced hard lines (one synced line), left soft/acquisition untouched
    hard_lines = [ln for ln in sync["budget"]["lines"] if ln.get("category") == "hard"]
    assert len(hard_lines) == 1 and "GMP" in hard_lines[0]["description"], hard_lines

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

    # developer construction-draw schedule sourced from the GC cost-loaded schedule + actual billed
    draws = c.get(f"/projects/{pid}/construction-draws").json()
    assert draws["projected_total"] == 1_800_000 and draws["months"] == cf["months"], draws
    assert draws["invoice_count"] >= 0 and "pct_billed" in draws and draws["peak_month_cost"] == 400_000, draws
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

    # owner billing execution: the pay-app PDF (G702 + G703) and an owner invoice from the draw
    pdf = c.get(f"/projects/{pid}/cost/g702.pdf?app_no=1")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.content) > 1500, (pdf.status_code, len(pdf.content))
    inv = c.post(f"/projects/{pid}/cost/pay-app/invoice", json={"app_no": 1})
    assert inv.status_code == 201, inv.text
    g702 = c.get(f"/projects/{pid}/cost/g702").json()
    assert inv.json()["amount"] == round(g702["line8_current_payment_due"], 2), (inv.json(), g702["line8_current_payment_due"])
    invs = c.get(f"/projects/{pid}/modules/owner_invoice").json()
    assert len(invs) == 1 and invs[0]["data"]["number"] == "App 1", invs
    assert invs[0]["data"].get("prime_contract"), "owner invoice links the prime contract"

    # actuals loop: bill SOV work → owner invoice → developer construction draws go live
    draws0 = c.get(f"/projects/{pid}/construction-draws").json()
    assert draws0["actual_billed"] == 0 and draws0["pct_billed"] == 0, draws0   # nothing billed yet
    sov_line = c.get(f"/projects/{pid}/modules/sov").json()[0]
    c.patch(f"/projects/{pid}/modules/sov/{sov_line['id']}", json={"completed_this": 1_000_000})
    inv2 = c.post(f"/projects/{pid}/cost/pay-app/invoice", json={"app_no": 2}).json()
    assert inv2["amount"] > 0, inv2                                             # current payment due now > 0
    draws1 = c.get(f"/projects/{pid}/construction-draws").json()
    assert draws1["actual_billed"] == round(inv2["amount"], 2) and draws1["pct_billed"] > 0, draws1
    assert draws1["invoice_count"] == 2, draws1                                 # the $0 App-1 + the billed App-2

    # construction-loan draws: owner invoices funded equity-first then debt vs the sized capital stack
    ld = c.get(f"/projects/{pid}/loan-draws").json()
    assert ld["loan_amount"] > 0 and ld["equity"] > 0, ld
    assert ld["drawn_to_date"] == draws1["actual_billed"], (ld["drawn_to_date"], draws1["actual_billed"])
    assert round(ld["equity_drawn"] + ld["loan_drawn"], 2) == ld["drawn_to_date"], ld   # split sums to drawn
    assert ld["equity_drawn"] == min(ld["drawn_to_date"], ld["equity"]), ld             # equity-first
    assert ld["loan_available"] == round(ld["loan_amount"] - ld["loan_drawn"], 2), ld
    assert ld["accrued_interest"] == 0, "no loan-funded draws yet → no interest"   # $950k < equity

    # push past equity with a back-dated draw → loan balance accrues interest from its draw date
    from datetime import date as _date, timedelta as _td
    backdated = (_date.today() - _td(days=180)).isoformat()
    c.post(f"/projects/{pid}/modules/owner_invoice",
           json={"data": {"number": "App 3", "amount": 2_000_000, "period": backdated, "status": "submitted"}})
    ld2 = c.get(f"/projects/{pid}/loan-draws").json()
    assert ld2["loan_drawn"] > 0, ld2                                              # now over equity
    assert ld2["accrued_interest"] > 0 and ld2["loan_start"] == backdated, ld2     # simple interest from draw date
    # ~ loan_drawn × 7.5% × 180/365 (the $2M tranche is what crossed onto the loan)
    expect = round(ld2["loan_drawn"] * 0.075 * 180 / 365, 2)
    assert abs(ld2["accrued_interest"] - expect) < 1.0, (ld2["accrued_interest"], expect)
    assert ld2["outstanding_with_interest"] == round(ld2["loan_drawn"] + ld2["accrued_interest"], 2), ld2
    # interest re-forecast: actual accrued + projected remaining carry vs the underwritten reserve
    assert ld2["budgeted_interest_reserve"] > 0, ld2
    assert ld2["forecast_interest"] >= ld2["accrued_interest"], ld2                 # forecast ≥ what's accrued
    assert ld2["interest_variance"] == round(ld2["budgeted_interest_reserve"] - ld2["forecast_interest"], 2), ld2

    # per-cost-code draw composition — the construction draw broken out by cost code (from the SOV)
    cd = c.get(f"/projects/{pid}/construction-draws").json()
    assert cd["by_cost_code"], "draw composition by cost code"
    assert any(x["billed"] == 1_000_000 for x in cd["by_cost_code"]), cd["by_cost_code"]   # the billed concrete line

    # subcontractor billing — the GC-pays-subs mirror: pay apps roll up vs the subcontract value
    sc = mk(c, pid, "subcontract", {"vendor": "Acme Concrete", "trade": "Concrete", "value": 1_750_000,
                                     "retainage_pct": 10, "cost_code": cc_conc})
    c.post(f"/projects/{pid}/modules/subcontract/{sc['id']}/transition", json={"action": "execute"})
    si1 = mk(c, pid, "sub_invoice", {"vendor": "Acme Concrete", "subcontract": sc["id"],
                                     "amount": 400_000, "retainage_pct": 10, "cost_code": cc_conc})
    c.post(f"/projects/{pid}/modules/sub_invoice/{si1['id']}/transition", json={"action": "approve"})
    c.post(f"/projects/{pid}/modules/sub_invoice/{si1['id']}/transition", json={"action": "pay"})
    si2 = mk(c, pid, "sub_invoice", {"vendor": "Acme Concrete", "subcontract": sc["id"], "amount": 200_000, "retainage_pct": 10})
    c.post(f"/projects/{pid}/modules/sub_invoice/{si2['id']}/transition", json={"action": "approve"})
    mk(c, pid, "sub_invoice", {"vendor": "Acme Concrete", "subcontract": sc["id"], "amount": 99_999})  # submitted → not counted
    sb = c.get(f"/projects/{pid}/subcontractor-billing").json()
    assert sb["subcontract_count"] == 1 and sb["invoice_count"] == 3, sb
    row = sb["subs"][0]
    assert row["contract_value"] == 1_750_000 and row["billed"] == 600_000, row    # only approved+paid count
    assert row["retainage"] == 60_000 and row["paid"] == 360_000, row              # 10% retainage; paid = 400k net
    assert row["remaining"] == 1_150_000, row
    assert sb["totals"]["billed"] == 600_000 and sb["totals"]["paid"] == 360_000, sb["totals"]

    # PX executive summary — on-schedule + on-budget in one health view
    pxs = c.get(f"/projects/{pid}/px-summary").json()
    assert pxs["status"] in ("on_track", "at_risk", "behind"), pxs["status"]
    assert pxs["schedule"]["activities"] >= 2 and pxs["schedule"]["critical_path_days"] >= 0, pxs["schedule"]
    assert "spi" in pxs["schedule"] and isinstance(pxs["schedule"]["milestones"], dict), pxs["schedule"]
    b2 = c.get(f"/projects/{pid}/budget/gmp").json()
    assert pxs["budget"]["gmp"] == b2["totals"]["budget"], (pxs["budget"]["gmp"], b2["totals"]["budget"])
    assert "variance_at_completion" in pxs["budget"] and pxs["budget"]["committed_pct"] >= 0, pxs["budget"]
    assert pxs["budget"]["buyout"]["packages"] == 1, pxs["budget"]["buyout"]

    # cross-project executive portfolio — this project shows up with its on-schedule/on-budget status
    pf = c.get("/portfolio/executive").json()
    assert pf["project_count"] >= 1 and len(pf["projects"]) == pf["project_count"], pf
    me_row = next((r for r in pf["projects"] if r["id"] == pid), None)
    assert me_row is not None and me_row["gmp"] == b2["totals"]["budget"], me_row
    assert me_row["status"] in ("on_track", "at_risk", "behind"), me_row
    assert "equity_irr" in me_row and "equity_multiple" in me_row, me_row   # developer returns alongside GC status
    assert "blended_equity_irr" in pf["totals"], pf["totals"]
    assert sum(pf["status_tally"].values()) == pf["project_count"], pf["status_tally"]

    # 5D element click: a model element tied to a schedule activity resolves to its activity +
    # cost-code budget (BIM ↔ schedule ↔ cost). The hard-tied path needs no published model.
    act5 = mk(c, pid, "schedule_activity", {"name": "Slab L1 pour", "trade": "Concrete",
                                            "cost_code": cc_conc, "percent": 40,
                                            "start": "2026-03-01", "finish": "2026-03-20", "budget": 100_000})
    c.post(f"/projects/{pid}/modules/schedule_activity/{act5['id']}/elements",
           json={"guids": ["EL-GUID-5D"], "mode": "set"})
    e5 = c.get(f"/projects/{pid}/elements/EL-GUID-5D/5d").json()
    assert e5["schedule"] and e5["schedule"]["hard_tied"] and e5["schedule"]["percent"] == 40, e5
    assert e5["cost"] and e5["cost"]["budget"] == 2_000_000, e5   # the concrete cost-code line budget
    assert e5["cost"]["code"] == "03-3000" and e5["cost"]["committed"] >= 1_800_000, e5   # buyout rolled in
    assert e5["cost"]["actual"] == 500_000, e5                    # direct cost to date on the code
    # an untied element with no published model → no schedule match, graceful nulls
    e5b = c.get(f"/projects/{pid}/elements/UNKNOWN-GUID/5d").json()
    assert e5b["schedule"] is None and e5b["guid"] == "UNKNOWN-GUID", e5b

    # investor memo PDF carries the on-cost executive language (Construction Status vs underwriting)
    memo = c.get(f"/projects/{pid}/investment-memo.pdf")
    assert memo.status_code == 200 and memo.content[:4] == b"%PDF", memo.status_code
    import io as _mio
    import pypdf  # ships in the venv
    text = "".join(pg.extract_text() or "" for pg in pypdf.PdfReader(_mio.BytesIO(memo.content)).pages)
    assert "Construction Status" in text and "GC GMP" in text, "memo includes the construction-status section"
    assert "Underwritten hard cost" in text, text[:200]

    print(f"PROJECT BUDGET OK - GMP computed ${b['gmp']['computed']:,.0f} (cost of work ${cow:,.0f}); "
          f"direct/GC/GR + OH/fee/contingency; bid packages + staffing + proforma reconciled; "
          f"owner SOV seeded from budget ({seed['created']} lines = ${seed['scheduled_value']:,.0f}); "
          f"pay-app PDF + owner invoice (${inv.json()['amount']:,.0f}) generated")
