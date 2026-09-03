"""Financial statements engine — the three statements + tax tie out and balance.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_financials.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_financials.db"
os.environ["STORAGE_DIR"] = "./test_storage_financials"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_financials.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import financials as fin  # noqa: E402
from aec_api.proforma.solve import solve  # noqa: E402

ASSUMPTIONS = {
    "timing": {"construction_months": 18, "leaseup_months": 6, "hold_years": 7, "start_date": "2026-01-01"},
    "cost_lines": [
        {"category": "land", "name": "Land", "amount": 4_000_000, "curve": "upfront"},
        {"category": "hard", "name": "Hard costs", "amount": 18_000_000, "curve": "scurve"},
        {"category": "soft", "name": "Soft costs", "amount": 4_000_000, "curve": "scurve"},
    ],
    "debt": {"ltc": 0.6, "rate": 0.075, "points": 0.01},
    "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
    "operations": {"potential_rent_annual": 3_600_000, "other_income_annual": 200_000,
                   "opex_annual": 1_300_000, "reserves_annual": 90_000,
                   "stabilized_occ": 0.94, "credit_loss_pct": 0.01},
    "exit": {"exit_cap": 0.055, "selling_cost_pct": 0.02},
    "waterfall": {"pref_rate": 0.08, "style": "american", "clawback": False,
                  "tiers": [{"hurdle": 0.08, "lp": 0.9, "gp": 0.1}, {"hurdle": None, "lp": 0.8, "gp": 0.2}]},
    "discount_rate": 0.10,
    "tax": {"income_tax_rate": 0.25, "depreciation_years": 27.5,
            "capital_gains_rate": 0.20, "niit_rate": 0.038, "recapture_rate": 0.25},
}

s = solve(ASSUMPTIONS)
f = fin.statements(s, ASSUMPTIONS)

# --- income statement: the NOI line equals the proforma's stabilized NOI ------
isr = {ln["label"]: ln["amount"] for ln in f["income_statement"]["lines"]}
noi_stmt = isr["Net operating income (NOI)"]
assert abs(noi_stmt - s["operations"]["stabilized_noi_annual"]) < 2.0, (noi_stmt, s["operations"])
# EGI = PGR − vacancy/credit + other; net income = pretax − tax (internal consistency)
assert abs(isr["Effective gross income"] - (isr["Potential gross rent"] + isr["Vacancy & credit loss"] + isr["Other income"])) < 1.0
assert abs(isr["Net income"] - (isr["Pre-tax income"] + isr["Income tax"])) < 1.0

# --- depreciation: straight-line on the depreciable basis (improvements only) -
basis = f["assumptions"]["depreciable_basis"]
assert basis > 0 and f["assumptions"]["land"] == 4_000_000, f["assumptions"]
assert abs(f["tax"]["depreciation_by_year"][0] - basis / 27.5) < 1.0, f["tax"]["depreciation_by_year"][0]

# --- balance sheet balances every year (assets == liabilities + equity) -------
assert f["balance_sheet"]["balanced"], [b for b in f["balance_sheet"]["by_year"] if not b["balanced"]]
for b in f["balance_sheet"]["by_year"]:
    assert abs(b["assets"]["total"] - (b["liabilities"]["total"] + b["equity"]["total"])) < 1.0, b

# --- passive-loss carryforward: tax is never negative; losses suspend + carry forward ---
yrs = f["tax"]["annual"]
assert all(y["income_tax"] >= 0 for y in yrs), [y["income_tax"] for y in yrs]   # no current benefit
assert max(y["loss_carryforward_end"] for y in yrs) > 0, yrs                     # this deal suspends losses
# a year only owes tax after exhausting the carryforward; a loss year owes nothing
for y in yrs:
    if y["taxable_income"] < 0:
        assert y["income_tax"] == 0 and y["loss_carryforward_used"] == 0, y
# the ending suspended loss is what's released at sale
assert f["after_tax_returns"]["suspended_loss_at_sale"] == yrs[-1]["loss_carryforward_end"]

# --- cash-flow statement: CFO add-back + a per-year three-section breakdown ----
cfs = f["cash_flow_statement"]
cfo_expected = round(sum(y["noi"] - y["interest"] - y["income_tax"] for y in yrs), 2)
assert abs(cfs["operating"]["after_tax_operating_cash_flow"] - cfo_expected) < 1.0, cfs["operating"]
assert len(cfs["by_year"]) == len(yrs) and all("operating" in r and "investing" in r for r in cfs["by_year"])
assert cfs["by_year"][-1]["investing"] != 0      # the sale lands in the final year's investing section

# --- tax at sale: suspended losses reduce the gain, then recapture + cap gains -
st = f["tax"]["sale"]
assert st["depreciation_recaptured"] <= sum(f["tax"]["depreciation_by_year"]) + 1.0
assert st["total_sale_tax"] == round(st["recapture_tax"] + st["capital_gains_tax"], 2)
assert abs(st["recapture_tax"] - st["depreciation_recaptured"] * 0.25) < 1.0
assert abs(st["capital_gains_tax"] - st["capital_gain"] * (0.20 + 0.038)) < 1.0
assert st["taxable_gain"] == round(st["total_gain"] - st["suspended_loss_used"], 2)
# releasing suspended losses lowers the sale tax vs ignoring them
no_loss = fin.sale_tax(st["sale_price"], st["selling_costs"], f["assumptions"]["land"],
                       f["assumptions"]["depreciable_basis"], sum(f["tax"]["depreciation_by_year"]),
                       ASSUMPTIONS["tax"], suspended_loss=0.0)
assert st["total_sale_tax"] <= no_loss["total_sale_tax"] + 1.0, (st["total_sale_tax"], no_loss["total_sale_tax"])

# --- after-tax returns are at/below pre-tax (tax drag) ------------------------
at = f["after_tax_returns"]
assert at["equity_irr"] is not None and s["returns"]["equity_irr"] is not None
assert at["equity_irr"] <= s["returns"]["equity_irr"] + 1e-9, (at["equity_irr"], s["returns"]["equity_irr"])
assert at["total_income_tax"] >= 0 and at["total_sale_tax"] >= 0

# --- two-sided budget: Uses (left) ties to Sources (right) --------------------
tb = f["two_sided_budget"]
assert tb["balanced"] and abs(tb["total_uses"] - tb["total_sources"]) < 1.0, tb
assert abs(tb["total_sources"] - (s["sources_uses"]["loan_amount"] + s["sources_uses"]["equity"])) < 2.0, tb

# --- a thin-rent deal stays in a loss → suspended losses release at sale -------
import copy  # noqa: E402

thin = copy.deepcopy(ASSUMPTIONS)
thin["operations"]["potential_rent_annual"] = 3_000_000        # NOI < interest+depr (loss) yet a sale gain
f2 = fin.statements(solve(thin), thin)
y2 = f2["tax"]["annual"]
assert all(y["income_tax"] == 0 for y in y2), [y["income_tax"] for y in y2]        # all loss years
sus = f2["after_tax_returns"]["suspended_loss_at_sale"]
assert sus > 0, sus                                            # losses never absorbed → carried to sale
s2 = f2["tax"]["sale"]
assert s2["suspended_loss_used"] > 0 and s2["taxable_gain"] < s2["total_gain"], s2
no_rel = fin.sale_tax(s2["sale_price"], s2["selling_costs"], f2["assumptions"]["land"],
                      f2["assumptions"]["depreciable_basis"], sum(f2["tax"]["depreciation_by_year"]),
                      thin["tax"], suspended_loss=0.0)
assert s2["total_sale_tax"] < no_rel["total_sale_tax"], (s2["total_sale_tax"], no_rel["total_sale_tax"])

# --- endpoints + Report Center ------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    # stateless financials
    r = c.post("/proforma/financials", json=ASSUMPTIONS)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["balance_sheet"]["balanced"] and body["two_sided_budget"]["balanced"], body.keys()
    assert "income_statement" in body and "cash_flow_statement" in body and "tax" in body

    pid = c.post("/projects", json={"name": "Tower Fund"}).json()["id"]
    # no scenario yet -> financials 404, but two-sided budget still builds from the cost budget
    assert c.get(f"/projects/{pid}/financials").status_code == 404
    assert c.get(f"/projects/{pid}/budget/two-sided").json()["balanced"] in (True, False)  # never errors

    sc = c.post("/proforma/scenarios", json={"name": "Base", "project_id": pid, "assumptions": ASSUMPTIONS})
    assert sc.status_code == 201, sc.text[:200]
    pf = c.get(f"/projects/{pid}/financials").json()
    assert pf["scenario"]["name"] == "Base" and pf["balance_sheet"]["balanced"], pf.get("scenario")
    tb2 = c.get(f"/projects/{pid}/budget/two-sided").json()
    assert tb2["balanced"] and abs(tb2["total_uses"] - tb2["total_sources"]) < 1.0, tb2

    # Report Center: financials report renders a valid PDF + Excel
    rep = c.get("/reports").json()["reports"]
    assert any(x["id"] == "financials" for x in rep), rep
    pdf = c.get(f"/projects/{pid}/reports/financials.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.content) > 1200, pdf.status_code
    xls = c.get(f"/projects/{pid}/reports/financials.xlsx")
    assert xls.status_code == 200 and xls.content[:2] == b"PK", xls.status_code

print(f"FINANCIALS OK - IS NOI ${noi_stmt:,.0f} ties to proforma; balance sheet balances all "
      f"{len(f['balance_sheet']['by_year'])} years; CFO add-back reconciles; sale tax "
      f"${st['total_sale_tax']:,.0f} (recapture ${st['recapture_tax']:,.0f} + cap gains "
      f"${st['capital_gains_tax']:,.0f}); after-tax IRR {at['equity_irr']:.1%} < pre-tax "
      f"{s['returns']['equity_irr']:.1%}; Uses=Sources ${tb['total_uses']:,.0f}")
