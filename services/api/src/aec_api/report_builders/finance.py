"""Report builders — finance domain (extracted from reports.py, A2)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import modules as me
from .. import project_budget as pb
from ..reports_core import Report
from ..reports_core import money as _money
from ._common import _records


def _cost(db: Session, pid: str, name: str) -> Report:
    b = pb.gmp_budget(db, pid)
    r = Report("Cost Report", name)
    t = b["totals"]
    r.kpi("GMP (computed)", _money(b["gmp"]["computed"]))
    r.kpi("Revised GMP", _money(b["gmp"]["revised"]))
    r.kpi("EAC", _money(t.get("eac", t["forecast"])))
    r.kpi("Variance", _money(t["variance"]))
    rows = [[c["name"], _money(c["budget"]), _money(c["committed"]), _money(c["actual"]),
             _money(c.get("forecast", c.get("eac"))), _money(c.get("variance"))]
            for c in b["categories"]]
    rows.append(["TOTAL", _money(t["budget"]), _money(t["committed"]), _money(t["actual"]),
                 _money(t.get("eac", t["forecast"])), _money(t["variance"])])
    r.table("Cost by category", ["Category", "Budget", "Committed", "Actual", "Forecast/EAC", "Variance"], rows)
    cats = [c for c in b["categories"] if (c.get("budget") or 0) > 0]
    if cats:
        r.chart("bar", "Budget vs committed vs actual vs EAC", [c["name"] for c in cats], [
            {"name": "Budget", "values": [round(c["budget"]) for c in cats]},
            {"name": "Committed", "values": [round(c.get("committed", 0)) for c in cats]},
            {"name": "Actual", "values": [round(c.get("actual", 0)) for c in cats]},
            {"name": "EAC", "values": [round(c.get("eac", c.get("forecast", c["budget"]))) for c in cats]},
        ])
    return r


def _evm(db: Session, pid: str, name: str) -> Report:
    from .. import evm
    snap = evm.snapshot(db, pid)
    t = snap["totals"]
    f = t["forecast"]
    es = snap.get("earned_schedule")
    r = Report("Earned Value Management", name)
    r.kpi("CPI", t["cpi"] if t["cpi"] is not None else "—")
    r.kpi("SPI", t["spi"] if t["spi"] is not None else "—")
    if es and es.get("spi_t") is not None:
        r.kpi("SPI(t)", es["spi_t"])
    r.kpi("% complete", f"{t['percent_complete']}%")
    r.kpi("EAC (working)", _money(f["eac_working"]))
    r.kpi("VAC", _money(f["vac"]))
    # performance summary
    r.table("Performance (data date " + t["data_date"] + ")",
            ["Metric", "Value"],
            [["BAC", _money(t["bac"])], ["Planned Value (PV)", _money(t["pv"])],
             ["Earned Value (EV)", _money(t["ev"])], ["Actual Cost (AC)", _money(t["ac"])],
             ["Cost Variance (CV=EV−AC)", _money(t["cv"])], ["Schedule Variance (SV=EV−PV)", _money(t["sv"])]])
    # forecast family
    r.table("Forecast at completion",
            ["Method", "Value"],
            [["EAC — BAC/CPI", _money(f["eac"]["cpi"])], ["EAC — AC+(BAC−EV)", _money(f["eac"]["at_plan"])],
             ["EAC — ÷(CPI·SPI)", _money(f["eac"]["cpi_spi"])], ["ETC (EAC−AC)", _money(f["etc"])],
             ["VAC (BAC−EAC)", _money(f["vac"])],
             ["TCPI to budget" + (" ⚠" if f["tcpi_warning"] else ""),
              f["tcpi_bac"] if f["tcpi_bac"] is not None else "—"]])
    if es and es.get("forecast_finish"):
        r.table("Earned Schedule",
                ["Metric", "Value"],
                [["Earned Schedule (periods)", es["earned_schedule_periods"]],
                 ["SPI(t)", es["spi_t"]], ["SV(t) periods", es["sv_t_periods"]],
                 ["Forecast finish", es["forecast_finish"]],
                 ["Days late", es["days_late"] if es["days_late"] is not None else "—"]])
    # control accounts
    if snap["control_accounts"]:
        r.table("Control accounts (cost code)",
                ["Cost code", "BAC", "EV", "AC", "CV", "SV", "CPI", "SPI"],
                [[c["cost_code"], _money(c["bac"]), _money(c["ev"]), _money(c["ac"]), _money(c["cv"]),
                  _money(c["sv"]), c["cpi"] if c["cpi"] is not None else "—",
                  c["spi"] if c["spi"] is not None else "—"] for c in snap["control_accounts"]])
    # PV/EV/AC S-curve
    sc = evm.scurve(db, pid, __import__("datetime").date.today())
    if sc and len(sc["pv"]) > 1:
        r.chart("line", "EVM S-curve (PV / EV / AC)", sc["labels"],
                [{"name": "PV", "values": [round(x) for x in sc["pv"]]},
                 {"name": "EV", "values": [round(x) for x in sc["ev"]]},
                 {"name": "AC", "values": [round(x) for x in sc["ac"]]}])
    # CPI/SPI performance-index trend across captured snapshots
    tr = evm.trend(db, pid)
    if tr["count"] >= 2:
        r.chart("line", "CPI / SPI trend (captured snapshots)", tr["labels"],
                [{"name": "CPI", "values": tr["cpi"]}, {"name": "SPI", "values": tr["spi"]},
                 {"name": "target 1.0", "values": [1.0] * len(tr["labels"])}])
    return r


def _financials(db: Session, pid: str, name: str) -> Report:
    """Income statement · balance sheet · cash flow · tax, from the project's latest proforma scenario."""
    from .. import financials
    from ..models import Scenario
    from ..proforma.solve import solve
    r = Report("Financial Statements", name)
    s = (db.query(Scenario).filter(Scenario.project_id == pid)
         .order_by(Scenario.created_at.desc()).first())
    if not s:
        r.kpi("Status", "No saved proforma scenario — solve & save one in Finance first.")
        return r
    f = financials.statements(s.result or solve(s.assumptions), s.assumptions)
    a = f["assumptions"]
    r.kpi("Income-tax rate", f"{a['income_tax_rate'] * 100:.0f}%")
    r.kpi("Depreciation life", f"{a['depreciation_years']:.1f} yrs")
    r.kpi("After-tax equity IRR", f"{(f['after_tax_returns']['equity_irr'] or 0) * 100:.1f}%")
    r.table("Income statement (stabilized year)", ["Line", "Amount"],
            [[ln["label"], _money(ln["amount"])] for ln in f["income_statement"]["lines"]])
    r.table("Operating summary by year",
            ["Year", "NOI", "Interest", "Depreciation", "Taxable", "Income tax", "Net income"],
            [[y["year"], _money(y["noi"]), _money(y["interest"]), _money(y["depreciation"]),
              _money(y["taxable_income"]), _money(y["income_tax"]), _money(y["net_income"])]
             for y in f["income_statement"]["by_year"]])
    by = f["income_statement"]["by_year"]
    if len(by) > 1:
        r.chart("line", "NOI vs net income by year", [f"Yr {y['year']}" for y in by], [
            {"name": "NOI", "values": [round(y["noi"]) for y in by]},
            {"name": "Net income", "values": [round(y["net_income"]) for y in by]},
        ])
    bs = f["balance_sheet"]["by_year"][-1]
    r.table(f"Balance sheet (year {bs['year']})", ["Account", "Amount"], [
        ["Land", _money(bs["assets"]["land"])],
        ["Improvements (net of depreciation)", _money(bs["assets"]["improvements_net"])],
        ["Capitalized financing", _money(bs["assets"]["capitalized_financing"])],
        ["Total assets", _money(bs["assets"]["total"])],
        ["Loan", _money(bs["liabilities"]["total"])],
        ["Paid-in capital", _money(bs["equity"]["paid_in_capital"])],
        ["Retained earnings", _money(bs["equity"]["retained_earnings"])],
        ["Total liabilities + equity", _money(bs["liabilities"]["total"] + bs["equity"]["total"])],
    ])
    cfs = f["cash_flow_statement"]
    r.table("Cash-flow statement", ["Section", "Amount"], [
        ["Operating (after-tax)", _money(cfs["operating"]["after_tax_operating_cash_flow"])],
        ["Investing", _money(cfs["investing"]["total"])],
        ["Financing", _money(cfs["financing"]["total"])],
        ["Net change in cash", _money(cfs["net_change_in_cash"])],
    ])
    st = f["tax"]["sale"]
    r.table("Tax at sale", ["Item", "Amount"], [
        ["Net sale price", _money(st["net_sale"])],
        ["Adjusted basis", _money(st["adjusted_basis"])],
        ["Total gain", _money(st["total_gain"])],
        ["Depreciation recapture tax (25%)", _money(st["recapture_tax"])],
        ["Capital-gains tax (+NIIT)", _money(st["capital_gains_tax"])],
        ["Total sale tax", _money(st["total_sale_tax"])],
    ])
    return r


def _appraisal(db: Session, pid: str, name: str) -> Report:
    """Tri-approach valuation: cost + income + sales-comparison, reconciled — from the project's
    proforma, estimate inputs and recorded comparables."""
    from .. import marketing
    v = marketing.compute_appraisal(db, pid)
    rec = v["reconciliation"]
    r = Report("Valuation — Tri-Approach Appraisal", name)
    r.kpi("Opinion of value", _money(rec["value"]))
    r.kpi("Value range", f"{_money(rec['range']['low'])} – {_money(rec['range']['high'])}")
    r.kpi("Approaches used", ", ".join(rec["approaches_used"]) or "—")
    r.kpi("Comparables", v["comp_count"])
    r.table("Approaches", ["Approach", "Indicated value", "Weight"],
            [[c["approach"].replace("_", " ").title(), _money(c["value"]), f"{c['weight'] * 100:.0f}%"]
             for c in rec["contributions"]] or [["(insufficient data)", "$0", "—"]])
    co, inc, sa = v["cost"], v["income"], v["sales_comparison"]
    r.table("Cost approach", ["Item", "Amount"], [
        ["Replacement cost new", _money(co["replacement_cost_new"])],
        ["Less depreciation", f"-{_money(co['depreciation_amount'])} ({co['depreciation_pct'] * 100:.0f}%)"],
        ["Plus land value", _money(co["land_value"])],
        ["Cost-approach value", _money(co["value"])],
    ])
    r.table("Income approach (direct cap)", ["Item", "Amount"], [
        ["Stabilized NOI", _money(inc["stabilized_noi"])],
        ["Cap rate", f"{inc['cap_rate'] * 100:.2f}%"],
        ["Income-approach value", _money(inc["value"])],
    ])
    r.table("Sales-comparison approach", ["Item", "Amount"], [
        ["Comparables used", str(sa["comp_count"])],
        ["Basis", sa["basis"]],
        ["Median $/SF", _money(sa["median_price_psf"]) if sa["median_price_psf"] else "—"],
        ["Implied cap rate", f"{sa['implied_cap_rate'] * 100:.2f}%" if sa["implied_cap_rate"] else "—"],
        ["Sales-comparison value", _money(sa["value"])],
    ])
    if rec["contributions"]:
        r.chart("bar", "Indicated value by approach",
                [c["approach"].replace("_", " ").title() for c in rec["contributions"]],
                [{"name": "Value", "values": [round(c["value"]) for c in rec["contributions"]]}])
    return r


def _wip(db: Session, pid: str, name: str) -> Report:
    """Work-in-Progress schedule: POC → earned vs billed → over/under-billing, retainage, gross profit."""
    from .. import wip
    w = wip.schedule(db, pid)
    r = Report("Work-in-Progress Schedule", name)
    r.kpi("% complete", f"{w['percent_complete']}%")
    r.kpi("Earned revenue", _money(w["earned_revenue"]))
    r.kpi("Billed to date", _money(w["billed_to_date"]))
    lbl = {"over-billed": "Over-billing (liability)", "under-billed": "Under-billing (asset)"}.get(
        w["billing_status"], "Billing")
    r.kpi(lbl, _money(w["over_billing"] or w["under_billing"]))
    r.kpi("Gross profit", f"{_money(w['gross_profit'])} ({w['gross_margin_pct']}%)")
    r.table("Contract position",
            ["Metric", "Value"],
            [["Contract value", _money(w["contract_value"])],
             ["Total estimated cost", _money(w["estimated_cost"])],
             ["Cost to date", _money(w["cost_to_date"])],
             ["Cost to complete", _money(w["cost_to_complete"])],
             ["% complete (cost-to-cost)", f"{w['percent_complete']}%"],
             ["Earned revenue (POC)", _money(w["earned_revenue"])],
             ["Billed to date", _money(w["billed_to_date"])],
             ["Over-billing — billings in excess (liability)", _money(w["over_billing"])],
             ["Under-billing — costs in excess (asset)", _money(w["under_billing"])],
             ["Retainage held", _money(w["retainage"])],
             ["Gross profit", _money(w["gross_profit"])],
             ["Profit earned to date", _money(w["profit_to_date"])],
             ["Backlog (unbilled contract)", _money(w["backlog"])]])
    r.chart("bar", "Earned vs billed", ["Earned revenue", "Billed to date"],
            [{"name": "$", "values": [round(w["earned_revenue"]), round(w["billed_to_date"])]}])
    return r


def _contractor(db: Session, pid: str, name: str) -> Report:
    """Contractor statements: percentage-of-completion income statement + contract-position section."""
    from .. import contractor
    s = contractor.statements(db, pid)
    inc, pos = s["income_statement"], s["contract_position"]
    r = Report("Contractor Financial Statements", name)
    r.kpi("Revenue earned", _money(inc["revenue_earned"]))
    r.kpi("Gross profit", f"{_money(inc['gross_profit'])} ({inc['gross_margin_pct']}%)")
    r.kpi("Contract asset", _money(pos["contract_asset_underbillings"]))
    r.kpi("Contract liability", _money(pos["contract_liability_overbillings"]))
    r.kpi("Backlog", _money(s["backlog"]))
    r.table("Income statement — percentage-of-completion",
            ["Line", "Amount"],
            [["Revenue earned (POC)", _money(inc["revenue_earned"])],
             ["Cost of revenue", _money(inc["cost_of_revenue"])],
             ["Gross profit", _money(inc["gross_profit"])],
             ["Gross margin", f"{inc['gross_margin_pct']}%"]])
    r.table("Contract position (balance sheet)",
            ["Account", "Amount"],
            [["Contract asset — costs in excess of billings", _money(pos["contract_asset_underbillings"])],
             ["Contract liability — billings in excess of costs", _money(pos["contract_liability_overbillings"])],
             ["Retainage receivable", _money(pos["retainage_receivable"])],
             ["Accounts payable (subs)", _money(pos["accounts_payable"])],
             ["Net contract working capital", _money(pos["net_contract_working_capital"])]])
    return r


def _market_intelligence(db: Session, pid: str, name: str) -> Report:
    """Regional escalation / labour / location table + the warm-cold sector board, and this project's
    escalation to its construction midpoint (from its market_assumption record if one exists)."""
    from .. import market_intelligence as mi
    snap = mi.snapshot()
    a = {}
    try:
        recs = me.list_records(db, "market_assumption", pid, limit=1000)
        if recs:
            a = (([r for r in recs if r.get("workflow_state") == "adopted"] or recs)[-1].get("data") or {})
    except Exception:                             # noqa: BLE001
        a = {}

    def _int(v):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None
    ctx = mi.project_context(a.get("region"), a.get("sector"),
                             start_year=_int(a.get("construction_start_year")),
                             duration_months=_int(a.get("duration_months")))
    r = Report("Market Intelligence & Escalation", name)
    r.kpi("Region", ctx["region"]["label"])
    r.kpi("Annual escalation", f"{ctx['region']['escalation_pct']}%")
    r.kpi("Labour (US$/hr)", ctx["region"]["labour_usd_hr"])
    r.kpi("Escalation to midpoint", f"{ctx['escalation_factor']}×")
    r.kpi("Sector", f"{ctx['sector']['sector']} ({ctx['sector']['temperature']})")
    r.table("Regions", ["Region", "Escalation %/yr", "Labour US$/hr", "Location index"],
            [[x["label"], x["escalation_pct"], x["labour_usd_hr"], x["location_index"]]
             for x in snap["regions"]])
    sig = snap["market_signal"]
    r.table("Warm / cold market", ["Temperature", "Sectors"],
            [["Hot", ", ".join(sig["hot"])],
             ["Cold", ", ".join(sig["cold"])]])
    return r


def _cap_table(db: Session, pid: str, name: str) -> Report:
    from .. import capital
    ct = capital.cap_table(me.list_records(db, "investor", pid, limit=100000) if "investor" in me.TABLES else [])
    r = Report("Investor Cap Table", name)
    r.kpi("Investors", ct["investor_count"])
    r.kpi("Total commitment", _money(ct["total_commitment"]))
    r.kpi("Contributed", _money(ct["total_contributed"]))
    r.kpi("Distributed", _money(ct["total_distributed"]))
    r.kpi("Unreturned capital", _money(ct["total_unreturned"]))
    r.table("Cap table", ["Investor", "Class", "Commitment", "Ownership %", "Contributed", "Distributed", "Unreturned"],
            [[x["investor"], x["investor_class"], _money(x["commitment"]), f"{x['ownership_pct']:.2f}%",
              _money(x["contributed"]), _money(x["distributed"]), _money(x["unreturned"])]
             for x in ct["rows"]] or [["(no investors)"] + [""] * 6])
    if ct["by_class"]:
        r.table("By class", ["Class", "Commitment"], [[k, _money(v)] for k, v in ct["by_class"].items()])
    return r


def _tm_log(db: Session, pid: str, name: str) -> Report:
    from .. import tm
    s = tm.tm_summary(db, pid)
    r = Report("T&M / eTicket Log", name)
    r.kpi("Tickets", s["ticket_count"])
    r.kpi("Labor", _money(s["labor_total"]))
    r.kpi("Material", _money(s["material_total"]))
    r.kpi("Equipment", _money(s["equipment_total"]))
    r.kpi("Grand total", _money(s["grand_total"]))
    r.kpi("Unbilled", _money(s["unbilled_total"]))
    r.table("Tickets", ["Ref", "Subject", "Date", "Labor", "Material", "Equip.", "Total", "Status"],
            [[x.get("ref", ""), x.get("subject", ""), x.get("work_date", ""), _money(x["labor"]),
              _money(x["material"]), _money(x["equipment"]), _money(x["total"]), x.get("status", "")]
             for x in s["rows"]] or [["(no T&M tickets)"] + [""] * 7])
    if s["by_status"]:
        r.chart("bar", "T&M by status", list(s["by_status"].keys()),
                [{"name": "Total", "values": [round(v) for v in s["by_status"].values()]}])
    bce = tm.by_change_event(db, pid)
    if bce["groups"]:
        r.table("T&M by change event", ["Change event", "Subject", "Tickets", "Total"],
                [[g.get("ref") or "—", g.get("subject") or "", g["ticket_count"], _money(g["total"])]
                 for g in bce["groups"]])
    return r


def _rent_roll(db: Session, pid: str, name: str) -> Report:
    from .. import rentroll
    rr = rentroll.rent_roll(db, pid)
    r = Report("Rent Roll", name)
    r.kpi("Occupancy", f"{rr['occupancy_pct']}%")
    r.kpi("Leases", rr["lease_count"])
    r.kpi("Occupied SF", f"{rr['occupied_sf']:,}")
    r.kpi("Base rent / yr", _money(rr["base_rent_annual"]))
    r.kpi("In-place income", _money(rr["in_place_gross_income"]))
    r.kpi("WALT", f"{rr['walt_years']} yrs")
    r.table("Leases", ["Suite", "Tenant", "Rentable SF", "Base rent/yr", "$/SF", "Type", "Expires", "Status"],
            [[x.get("suite", ""), x.get("tenant", ""), f"{x['rentable_sf']:,}", _money(x["base_rent_annual"]),
              _money(x["rent_psf"]), x.get("lease_type", ""), x.get("end_date", ""), x.get("status", "")]
             for x in rr["rows"]] or [["(no active leases)"] + [""] * 7])
    exp = rr["expirations_by_year"]
    if exp:
        r.table("Lease expirations by year", ["Year", "Leases", "SF", "Expiring rent"],
                [[y, e["count"], f"{e['sf']:,}", _money(e["rent"])] for y, e in exp.items()])
        r.chart("bar", "Expiring rent by year", list(exp.keys()),
                [{"name": "Expiring rent", "values": [round(e["rent"]) for e in exp.values()]}])
    return r


def _lease_management(db: Session, pid: str, name: str) -> Report:
    from .. import leasemgmt
    s = leasemgmt.lease_management(db, pid)
    ren, esc, cam = s["renewals"], s["escalations"], s["cam"]
    r = Report("Lease Management", name)
    r.kpi("Leases", s["lease_count"])
    r.kpi("Holdover", ren["holdover_count"])
    r.kpi("Expiring <=365d rent", _money(ren["at_risk_rent"]))
    r.kpi("Options outstanding", ren["options_outstanding"])
    r.kpi(f"Base rent (yr {esc['years']})", _money(esc["projected_base_rent"]))
    r.kpi("Recoverable income", _money(cam["recoverable_income"]))
    yrs = list(range(esc["years"] + 1))
    if any(esc["portfolio_by_year"]):
        r.chart("line", "Portfolio base rent (escalated)", [f"Y{y}" for y in yrs],
                [{"name": "Base rent", "values": [round(v) for v in esc["portfolio_by_year"]]}])
    r.table("Renewal / expiration pipeline", ["Ref", "Tenant", "Suite", "End", "Rent", "Status", "Options"],
            [[x.get("ref", ""), x.get("tenant", ""), x.get("suite", ""), x.get("end_date", ""),
              _money(x["base_rent_annual"]), x.get("status", ""), "yes" if x["has_option"] else "—"]
             for x in ren["rows"]] or [["(no expiring/holdover leases)"] + [""] * 6])
    r.table("CAM / expense recovery", ["Ref", "Tenant", "Type", "Rentable SF", "$/SF", "Recoverable"],
            [[x.get("ref", ""), x.get("tenant", ""), x.get("lease_type", ""), x.get("rentable_sf", ""),
              _money(x["recovery_psf"]), _money(x["recoverable_income"])]
             for x in cam["rows"]] or [["(no recovery leases)"] + [""] * 5])
    return r


def _latest_listing(db: Session, pid: str) -> dict | None:
    recs = _records(db, "listing", pid)
    if not recs:
        return None
    # prefer an active/under-contract listing, else the most recent
    for st in ("active", "under_contract", "coming_soon"):
        for x in recs:
            if x.get("workflow_state") == st:
                return x
    return recs[-1]


def _listing_factsheet(db: Session, pid: str, name: str) -> Report:
    """Marketing fact sheet generated from the project's listing record (auto-filled from the model
    + proforma). The off-plan marketing kit: key facts, highlights, location."""
    rec = _latest_listing(db, pid)
    r = Report("Listing Fact Sheet", name)
    if not rec:
        r.kpi("Status", "No listing yet — create one in Finance ▸ Listings (Auto-fill from project).")
        return r
    d = rec.get("data") or {}
    r.kpi("Price", _money(d.get("list_price")))
    if d.get("price_psf"):
        r.kpi("$/SF", _money(d.get("price_psf")))
    if d.get("cap_rate"):
        r.kpi("Cap rate", f"{d.get('cap_rate')}%")
    if d.get("noi"):
        r.kpi("Stabilized NOI", _money(d.get("noi")))
    r.kpi("Status", str(rec.get("workflow_state", "")).replace("_", " ").title())
    facts = [
        ["Address", d.get("address", "")],
        ["Asset type", d.get("asset_type", "")],
        ["Location", " ".join(str(d.get(k, "")) for k in ("city", "state", "zip_code")).strip()],
        ["Beds / Baths", f"{d.get('beds', '—')} / {d.get('baths', '—')}"],
        ["Living / rentable SF", str(d.get("sqft", "—"))],
        ["Units", str(d.get("num_units", "—"))],
        ["Unit mix", d.get("unit_mix", "—")],
        ["Year built / completion", str(d.get("year_built", "—"))],
        ["Lot SF", str(d.get("lot_sqft", "—"))],
    ]
    r.table("Key facts", ["Item", "Detail"], [[a, b] for a, b in facts if b not in ("", None)])
    if d.get("public_description"):
        r.table("Description", ["", ""], [["", d["public_description"]]])
    if d.get("highlights"):
        r.table("Highlights", ["", ""], [["", d["highlights"]]])
    if d.get("virtual_tour_url"):
        r.table("3D tour", ["", ""], [["Link", d["virtual_tour_url"]]])
    return r


def _marketing_flyer(db: Session, pid: str, name: str) -> Report:
    """Buyer-facing one-page flyer from the listing — headline price, highlights, description, tour.
    Leads with the marketing narrative (the off-plan kit) rather than the full fact table."""
    rec = _latest_listing(db, pid)
    r = Report("Marketing Flyer", name)
    if not rec:
        r.kpi("Status", "No listing yet — create one in Finance ▸ Listings (Auto-fill from project).")
        return r
    d = rec.get("data") or {}
    headline = d.get("address") or name
    r.kpi("For sale / lease", headline)
    r.kpi("Price", _money(d.get("list_price")))
    if d.get("price_psf"):
        r.kpi("$/SF", _money(d.get("price_psf")))
    if d.get("cap_rate"):
        r.kpi("Cap rate", f"{d.get('cap_rate')}%")
    if d.get("public_description"):
        r.table("About this property", ["", ""], [["", d["public_description"]]])
    if d.get("highlights"):
        r.table("Highlights", ["", ""], [["", d["highlights"]]])
    quick = [
        ["Asset type", d.get("asset_type", "")],
        ["Location", " ".join(str(d.get(k, "")) for k in ("city", "state", "zip_code")).strip()],
        ["Size", f"{d.get('sqft', '—')} SF" + (f" · {d.get('num_units')} units" if d.get("num_units") else "")],
        ["Beds / Baths", f"{d.get('beds', '—')} / {d.get('baths', '—')}"],
        ["Year built / completion", str(d.get("year_built", "—"))],
    ]
    r.table("At a glance", ["", ""], [[a, b] for a, b in quick if b not in ("", None, "—")])
    if d.get("virtual_tour_url"):
        r.table("Take the 3D tour", ["", ""], [["Link", d["virtual_tour_url"]]])
    return r
