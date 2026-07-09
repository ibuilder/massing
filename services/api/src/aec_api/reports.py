"""Report Center — detailed, exportable construction reports (PDF + Excel).

A small catalog of best-practice reports (executive health, cost, EVM/S-curve, operational logs,
contracts & signatures) built from the existing engines (px.py, project_budget.py, the modules
records) into a neutral structure, then rendered to PDF (reportlab) or Excel (openpyxl via exports).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import modules as me
from . import project_budget as pb
from . import px
from .models import Project

# Report model + formatting live in reports_core; PDF/Excel rendering in reports_render. Re-exported
# here so existing callers keep using `reports.Report` / `reports.to_pdf` / `reports.to_sheets`.
from .reports_core import Report
from .reports_core import money as _money
from .reports_render import to_pdf, to_sheets  # noqa: F401  (re-exported for the router)

__all__ = ["catalog", "build", "to_pdf", "to_sheets", "Report"]

# id -> (name, group)
REPORTS: dict[str, tuple[str, str]] = {
    "executive": ("Executive Summary", "Health"),
    "risk": ("Risk Digest", "Health"),
    "cost": ("Cost Report", "Cost"),
    "evm": ("Earned Value Management", "Cost"),
    "change_orders": ("Change Order Log", "Logs"),
    "rfi": ("RFI Log", "Logs"),
    "submittals": ("Submittal Log", "Logs"),
    "daily": ("Daily Report Log", "Logs"),
    "safety": ("Safety / Incident Log", "Logs"),
    "contracts": ("Contracts & Signatures", "Contracts"),
    "financials": ("Financial Statements", "Finance"),
    "appraisal": ("Valuation (Tri-Approach Appraisal)", "Finance"),
    "market_intelligence": ("Market Intelligence & Escalation", "Finance"),
    "listing_factsheet": ("Listing Fact Sheet", "Disposition"),
    "marketing_flyer": ("Marketing Flyer", "Disposition"),
    "rent_roll": ("Rent Roll", "Operations"),
    "lease_management": ("Lease Management (renewals / escalations / CAM)", "Operations"),
    "cap_table": ("Investor Cap Table", "Capital"),
    "tm_log": ("T&M / eTicket Log", "Cost"),
    "submittal_register": ("Submittal Register", "Logs"),
    "quality": ("Quality Dashboard", "Quality"),
    "rfi_register": ("RFI Register", "Logs"),
    "field_log": ("Field-Log Rollup", "Field"),
    "safety_dashboard": ("Safety Dashboard (OSHA)", "Safety"),
    "closeout": ("Closeout Dashboard", "Closeout"),
    "project_health": ("Project Health (Executive)", "Executive"),
    "co_log": ("Change-Order Log", "Cost"),
    "action_tracker": ("Meeting Action-Item Tracker", "Logs"),
    "estimate_continuity": ("Estimate Continuity (Preconstruction)", "Preconstruction"),
    "decision_log": ("Decision Log", "Preconstruction"),
    "assumptions_register": ("Assumptions & Clarifications", "Preconstruction"),
    "precon_alignment": ("Preconstruction Alignment", "Preconstruction"),
    "spec_submittal_log": ("Spec-Driven Submittal Log", "Preconstruction"),
    "site_feasibility": ("Site Feasibility / Zoning Envelope", "Preconstruction"),
    "esg": ("ESG / Sustainability Summary", "Operations"),
    "fca": ("Facility Condition Assessment (FCI)", "Operations"),
    "resilience": ("Climate & Water Resilience (flood + stormwater)", "Operations"),
    "bim_kpi": ("BIM KPI Scorecard (ISO 19650)", "Quality"),
    "bep": ("BIM Execution Plan (BEP, ISO 19650)", "Quality"),
    "lod": ("LOD Matrix & Coverage", "Quality"),
    "naming": ("Naming Convention Compliance", "Quality"),
    "document_control": ("Document Control Health", "Quality"),
    "design_options": ("Design Options Comparison", "Design"),
    "design_standards": ("Design Standards Compliance", "Design"),
    "mep": ("MEP Equipment Schedule", "Engineering"),
    "resource_loading": ("Resource-Loaded Schedule", "Schedule"),
    "envelope": ("Envelope Code Compliance (IECC)", "Engineering"),
    "productivity": ("Field Labor Productivity", "Field"),
}


def catalog() -> list[dict[str, str]]:
    return [{"id": k, "name": n, "group": g} for k, (n, g) in REPORTS.items()]


def _records(db: Session, key: str, pid: str) -> list[dict]:
    return me.list_records(db, key, pid, limit=100000) if key in me.TABLES else []


# --- per-report builders -----------------------------------------------------
def _executive(db: Session, pid: str, name: str) -> Report:
    s = px.summary(db, pid)
    sch, bud = s["schedule"], s["budget"]
    r = Report("Executive Summary", name)
    r.kpi("Overall status", s["status"].replace("_", " ").title())
    r.kpi("SPI", sch["spi"] if sch["spi"] is not None else "—")
    r.kpi("% complete", f"{sch['pct_complete']}%")
    r.kpi("EAC", _money(bud["eac"]))
    r.kpi("Variance at completion", _money(bud["variance_at_completion"]))
    r.kpi("Committed", f"{bud['committed_pct']}%")
    r.kpi("Spent", f"{bud['spent_pct']}%")
    open_counts = []
    for key, label in [("rfi", "Open RFIs"), ("submittal", "Open submittals"), ("cor", "Open change orders")]:
        recs = _records(db, key, pid)
        open_n = sum(1 for x in recs if x["workflow_state"] not in ("closed", "executed", "approved", "rejected", "answered", "void"))
        open_counts.append([label, open_n, len(recs)])
    incidents = _records(db, "incident", pid)
    open_counts.append(["Safety incidents", len(incidents), len(incidents)])
    r.table("Open items", ["Item", "Open", "Total"], open_counts)
    al = px.alerts(db, pid)
    r.kpi("Schedule alerts", f"{al['counts']['high']} high / {al['counts']['medium']} med")
    if al["alerts"]:
        r.table("Predictive schedule alerts", ["Level", "Alert", "Detail"],
                [[a["level"].upper(), a["title"], a.get("detail", "")] for a in al["alerts"][:25]])
    return r


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
    from . import evm
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


def _log(db: Session, pid: str, name: str, key: str, title: str, cols: list[tuple[str, str]]) -> Report:
    recs = _records(db, key, pid)
    r = Report(title, name)
    r.kpi("Records", len(recs))
    rows = []
    for rec in recs:
        d = rec.get("data") or {}
        row = [rec.get("ref", "")]
        for field, _ in cols:
            v = d.get(field, "")
            row.append(_money(v) if field in ("amount", "value") else str(v))
        row.append(rec.get("workflow_state", ""))
        rows.append(row)
    r.table(title, ["Ref"] + [label for _, label in cols] + ["Status"], rows)
    return r


def _contracts(db: Session, pid: str, name: str) -> Report:
    r = Report("Contracts & Signatures", name)
    rows = []
    for key, who in [("prime_contract", "name"), ("subcontract", "vendor"), ("cor", "subject")]:
        for rec in _records(db, key, pid):
            d = rec.get("data") or {}
            sigs = d.get("signatures") or []
            rows.append([key.replace("_", " "), rec.get("ref", ""), str(d.get(who, "")),
                         _money(d.get("value") or d.get("amount")), rec.get("workflow_state", ""),
                         ", ".join(f"{s.get('party')}" for s in sigs) or "—"])
    r.kpi("Contract records", len(rows))
    r.table("Contracts", ["Type", "Ref", "Party", "Value", "Status", "Signed by"], rows)
    return r


def _risk(db: Session, pid: str, name: str) -> Report:
    dg = px.risk_digest(db, pid)
    r = Report("Risk Digest", name)
    r.kpi("Headline", dg.get("headline") or "—")
    r.kpi("Risks flagged", len(dg.get("risks", [])))
    if dg.get("risks"):
        r.table("Prioritized risks", ["Level", "Risk"],
                [[str(x.get("level", "")).upper(), x.get("text", "")] for x in dg["risks"]])
    if dg["drivers"].get("top_alerts"):
        r.table("Top schedule alerts", ["Level", "Alert", "Detail"],
                [[a["level"].upper(), a["title"], a.get("detail", "")] for a in dg["drivers"]["top_alerts"]])
    return r


def _financials(db: Session, pid: str, name: str) -> Report:
    """Income statement · balance sheet · cash flow · tax, from the project's latest proforma scenario."""
    from . import financials
    from .models import Scenario
    from .proforma.solve import solve
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
    from . import marketing
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


def _lease_management(db: Session, pid: str, name: str) -> Report:
    from . import leasemgmt
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


def _rent_roll(db: Session, pid: str, name: str) -> Report:
    from . import rentroll
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


def _cap_table(db: Session, pid: str, name: str) -> Report:
    from . import capital
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
    from . import tm
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


def _submittal_register(db: Session, pid: str, name: str) -> Report:
    from . import submittals
    s = submittals.submittal_register(db, pid)
    r = Report("Submittal Register", name)
    r.kpi("Submittals", s["submittal_count"])
    r.kpi("Open", s["open_count"])
    r.kpi("Overdue", s["overdue_count"])
    r.kpi("Avg turnaround", f"{s['avg_turnaround_days']} d" if s["avg_turnaround_days"] is not None else "—")
    r.table("Register", ["Ref", "Spec", "Title", "Type", "Responsible", "Disposition", "Req. on site", "Turn (d)", "Status"],
            [[x.get("ref", ""), x.get("spec_section", ""), x.get("title", ""), x.get("type", ""),
              x.get("responsible", ""), x.get("disposition", ""), x.get("required_on_site", ""),
              x.get("turnaround_days", "") if x.get("turnaround_days") is not None else "",
              ("OVERDUE " if x["overdue"] else "") + str(x.get("status", ""))]
             for x in s["rows"]] or [["(no submittals)"] + [""] * 8])
    return r


def _quality(db: Session, pid: str, name: str) -> Report:
    from . import quality
    q = quality.quality_summary(db, pid)
    ins, ncr, df = q["inspections"], q["ncrs"], q["deficiencies"]
    r = Report("Quality Dashboard", name)
    r.kpi("Inspections", ins["total"])
    r.kpi("Pass rate", f"{ins['pass_rate']}%" if ins["pass_rate"] is not None else "—")
    r.kpi("First-pass yield", f"{ins['first_pass_yield']}%" if ins["first_pass_yield"] is not None else "—")
    r.kpi("Open NCRs", ncr["open_count"])
    r.kpi("Overdue NCRs", ncr["overdue_count"])
    r.kpi("Open deficiencies", df["open_count"])
    r.kpi("Overdue deficiencies", df["overdue_count"])
    if ins["by_result"]:
        r.chart("bar", "Inspections by result", list(ins["by_result"].keys()),
                [{"name": "Count", "values": list(ins["by_result"].values())}])
    r.table("Inspections by type", ["Type", "Count"],
            [[k, v] for k, v in ins["by_type"].items()] or [["(none)", ""]])
    r.table("NCR loop", ["Ref", "Non-conformance", "State", "Disposition", "Severity", "Due", "Corr. action"],
            [[x.get("ref", ""), x.get("subject", ""), x.get("state", ""), x.get("disposition") or "(undecided)",
              x.get("severity", ""), ("OVERDUE " if x["overdue"] else "") + str(x.get("due_date") or ""),
              "yes" if x["has_corrective_action"] else "—"] for x in ncr["rows"]] or [["(no NCRs)"] + [""] * 6])
    r.table("Deficiency ball-in-court", ["Ref", "Deficiency", "Ball in court", "Trade", "Severity", "Due"],
            [[x.get("ref", ""), x.get("description", ""), x.get("ball_in_court", ""), x.get("trade", ""),
              x.get("severity", ""), ("OVERDUE " if x["overdue"] else "") + str(x.get("due_date") or "")]
             for x in df["rows"]] or [["(no deficiencies)"] + [""] * 5])
    return r


def _rfi_register(db: Session, pid: str, name: str) -> Report:
    from . import rfi
    s = rfi.rfi_register(db, pid)
    r = Report("RFI Register", name)
    r.kpi("RFIs", s["rfi_count"])
    r.kpi("Open", s["open_count"])
    r.kpi("Overdue", s["overdue_count"])
    r.kpi("Avg response", f"{s['avg_response_days']} d" if s["avg_response_days"] is not None else "—")
    r.kpi("Cost-impacting", s["cost_impacted_count"])
    r.kpi("Schedule-impacting", s["schedule_impacted_count"])
    if s["ball_in_court"]:
        r.chart("bar", "RFI ball-in-court", list(s["ball_in_court"].keys()),
                [{"name": "Count", "values": list(s["ball_in_court"].values())}])
    r.table("Register", ["Ref", "Subject", "Discipline", "Priority", "Ball in court", "Due", "Cost", "Sched."],
            [[x.get("ref", ""), x.get("subject", ""), x.get("discipline", ""), x.get("priority", ""),
              x.get("ball_in_court", ""), ("OVERDUE " if x["overdue"] else "") + str(x.get("due_date") or ""),
              x.get("cost_impact", ""), x.get("schedule_impact", "")]
             for x in s["rows"]] or [["(no RFIs)"] + [""] * 7])
    return r


def _field_log(db: Session, pid: str, name: str) -> Report:
    from . import dailylog
    s = dailylog.field_log_summary(db, pid)
    r = Report("Field-Log Rollup", name)
    r.kpi("Daily reports", s["report_count"])
    r.kpi("Coverage", f"{s['coverage_pct']}%" if s["coverage_pct"] is not None else "—")
    r.kpi("Total manpower", s["total_manpower"])
    r.kpi("Avg/day", s["avg_manpower"] if s["avg_manpower"] is not None else "—")
    r.kpi("Peak", f"{s['peak_manpower']['count']} ({s['peak_manpower']['date'] or '—'})")
    r.kpi("Weather lost-days", s["weather_lost_days"])
    r.kpi("Delay days", s["delay_days"])
    if s["by_impact"]:
        r.chart("bar", "Weather impact", list(s["by_impact"].keys()),
                [{"name": "Days", "values": list(s["by_impact"].values())}])
    r.table("Daily reports", ["Ref", "Date", "Weather", "Temp", "Impact", "Manpower", "Delay"],
            [[x.get("ref", ""), x.get("report_date", ""), x.get("weather", ""), x.get("temp_f", ""),
              x.get("weather_impact", ""), x.get("manpower", ""), "yes" if x["has_delay"] else "—"]
             for x in s["rows"]] or [["(no daily reports)"] + [""] * 6])
    return r


def _safety(db: Session, pid: str, name: str) -> Report:
    from . import safety
    s = safety.safety_summary(db, pid)
    inc, obs, tbt, viol = s["incidents"], s["observations"], s["toolbox_talks"], s["violations"]
    r = Report("Safety Dashboard (OSHA)", name)
    r.kpi("Incidents", inc["incident_count"])
    r.kpi("Recordables", inc["recordable_count"])
    r.kpi("TRIR", inc["trir"] if inc["trir"] is not None else "—")
    r.kpi("DART", inc["dart_rate"] if inc["dart_rate"] is not None else "—")
    r.kpi("LTIFR", inc["ltifr"] if inc["ltifr"] is not None else "—")
    r.kpi("Lost days", inc["total_lost_days"])
    r.kpi("Observations", obs["observation_count"])
    r.kpi("Toolbox talks", tbt["talk_count"])
    note = f"Hours worked {int(inc['hours_worked']):,}" + (" (estimated from manpower)" if s["hours_estimated"] else "")
    r.kpi("Basis", note)
    if inc["by_classification"]:
        r.chart("bar", "Incidents by OSHA class", list(inc["by_classification"].keys()),
                [{"name": "Count", "values": list(inc["by_classification"].values())}])
    r.table("Incidents", ["Ref", "Subject", "Date", "OSHA class", "Recordable", "DART", "Lost d", "State"],
            [[x.get("ref", ""), x.get("subject", ""), x.get("date", ""), x.get("classification", ""),
              "yes" if x["recordable"] else "—", "yes" if x["dart"] else "—", x.get("lost_days", ""),
              x.get("state", "")] for x in inc["rows"]] or [["(no incidents)"] + [""] * 7])
    r.table("Observations (leading indicators)", ["Metric", "Value"],
            [["Safe", obs["safe_count"]], ["At-risk", obs["at_risk_count"]],
             ["Safe : at-risk", obs["safe_to_at_risk"] if obs["safe_to_at_risk"] is not None else "—"],
             ["Closed %", f"{obs['closed_pct']}%" if obs["closed_pct"] is not None else "—"]])
    r.table("Safety violations", ["Metric", "Value"],
            [["Total", viol["violation_count"]], ["Open", viol["open_count"]],
             ["Overdue", viol["overdue_count"]]])
    return r


def _closeout(db: Session, pid: str, name: str) -> Report:
    from . import closeout
    s = closeout.closeout_summary(db, pid)
    pu, cx, wr, om = s["punchlist"], s["commissioning"], s["warranties"], s["om_manuals"]
    r = Report("Closeout Dashboard", name)
    r.kpi("Punch items", pu["punch_count"])
    r.kpi("Punch complete", f"{pu['complete_pct']}%" if pu["complete_pct"] is not None else "—")
    r.kpi("Punch overdue", pu["overdue_count"])
    r.kpi("Open punch cost", _money(pu["open_cost"]))
    r.kpi("Cx pass rate", f"{cx['pass_rate']}%" if cx["pass_rate"] is not None else "—")
    r.kpi("Warranties expiring", wr["expiring_soon"])
    r.kpi("O&M accepted", f"{om['accepted_pct']}%" if om["accepted_pct"] is not None else "—")
    if pu["ball_in_court"]:
        r.chart("bar", "Punchlist ball-in-court", list(pu["ball_in_court"].keys()),
                [{"name": "Count", "values": list(pu["ball_in_court"].values())}])
    r.table("Punchlist", ["Ref", "Description", "Ball in court", "Trade", "Priority", "Due", "Cost"],
            [[x.get("ref", ""), x.get("description", ""), x.get("ball_in_court", ""), x.get("trade", ""),
              x.get("priority", ""), ("OVERDUE " if x["overdue"] else "") + str(x.get("due_date") or ""),
              _money(x["cost"])] for x in pu["rows"]] or [["(no punch items)"] + [""] * 6])
    r.table("Commissioning", ["Metric", "Value"],
            [["Tests", cx["cx_count"]], ["Pass", cx["passed"]], ["Fail", cx["failed"]],
             ["Conditional", cx["conditional"]], ["Accepted", cx["accepted"]]])
    r.table("Warranties", ["Metric", "Value"],
            [["Total", wr["warranty_count"]], ["Active", wr["active"]],
             ["Expiring (90d)", wr["expiring_soon"]], ["Expired", wr["expired"]]])
    return r


def _project_health(db: Session, pid: str, name: str) -> Report:
    from . import projecthealth
    h = projecthealth.project_health(db, pid)
    r = Report("Project Health (Executive)", name)
    r.kpi("Health score", f"{h['health_score']}/100" if h["health_score"] is not None else "—")
    r.kpi("Overall", h["overall_status"].upper())
    r.kpi("Open items", h["open_items_total"])
    r.kpi("Overdue items", h["overdue_items_total"])
    if h["domains"]:
        r.chart("bar", "Domain health", [d["label"] for d in h["domains"]],
                [{"name": "Score", "values": [{"green": 100, "amber": 60, "red": 20}.get(d["status"], 0)
                                              for d in h["domains"]]}])
    r.table("Domains", ["Domain", "Status", "Summary", "Open", "Overdue"],
            [[d["label"], d["status"].upper(), d["headline"], d["open_count"], d["overdue_count"]]
             for d in h["domains"]])
    r.table("Attention items (ranked)", ["Status", "Domain", "Issue"],
            [[a["status"].upper(), a["domain"], a["issue"]] for a in h["attention_items"]]
            or [["—", "—", "No red/amber items — all clear"]])
    return r


def _co_log(db: Session, pid: str, name: str) -> Report:
    from . import changeorders
    s = changeorders.co_log(db, pid)
    r = Report("Change-Order Log", name)
    r.kpi("Change orders", s["co_count"])
    r.kpi("Total value", _money(s["total_value"]))
    r.kpi("Pending", _money(s["pending_value"]))
    r.kpi("Approved", _money(s["approved_value"]))
    r.kpi("Executed", _money(s["executed_value"]))
    r.kpi("Schedule days", s["total_schedule_days"])
    r.kpi("CE ROM exposure", _money(s["change_event_rom_exposure"]))
    if s["by_reason"]:
        r.chart("bar", "COs by reason", list(s["by_reason"].keys()),
                [{"name": "Count", "values": list(s["by_reason"].values())}])
    r.table("Change orders", ["Ref", "Subject", "State", "Ball in court", "Reason", "Amount", "Sched d"],
            [[x.get("ref", ""), x.get("subject", ""), x.get("state", ""), x.get("ball_in_court", ""),
              x.get("reason", ""), _money(x["amount"]), x.get("schedule_days", "")]
             for x in s["rows"]] or [["(no change orders)"] + [""] * 6])
    return r


def _action_tracker(db: Session, pid: str, name: str) -> Report:
    from . import actions
    s = actions.action_tracker(db, pid)
    r = Report("Meeting Action-Item Tracker", name)
    r.kpi("Action items", s["action_count"])
    r.kpi("Open", s["open_count"])
    r.kpi("Overdue", s["overdue_count"])
    r.kpi("Completion", f"{s['completion_pct']}%" if s["completion_pct"] is not None else "—")
    r.kpi("Meetings", s["meeting_count"])
    r.kpi("Last meeting", s["last_meeting"] or "—")
    if s["by_assignee"]:
        r.chart("bar", "Action items by assignee", list(s["by_assignee"].keys())[:8],
                [{"name": "Count", "values": list(s["by_assignee"].values())[:8]}])
    r.table("Action items", ["Ref", "Subject", "Assignee", "Priority", "Due", "State"],
            [[x.get("ref", ""), x.get("subject", ""), x.get("assignee", ""), x.get("priority", ""),
              ("OVERDUE " if x["overdue"] else "") + str(x.get("due_date") or ""), x.get("state", "")]
             for x in s["rows"]] or [["(no action items)"] + [""] * 5])
    return r


def _estimate_continuity(db: Session, pid: str, name: str) -> Report:
    from . import precon
    s = precon.estimate_continuity(db, pid)
    r = Report("Estimate Continuity (Preconstruction)", name)
    r.kpi("Estimate sets", s["set_count"])
    r.kpi("Latest", f"{_money(s['latest_total'])} ({s['latest_milestone'] or '—'})")
    if s["latest_psf"]:
        r.kpi("$/SF", _money(s["latest_psf"]))
    r.kpi("Drift (first→latest)", f"{_money(s['total_drift'])}"
          + (f" ({s['total_drift_pct']:+.1f}%)" if s["total_drift_pct"] is not None else ""))
    r.kpi("Budget / GMP", _money(s["budget"]) if s["budget"] is not None else "—")
    if s["variance_to_budget"] is not None:
        r.kpi("Variance to budget", ("OVER " if s["over_budget"] else "under ") + _money(abs(s["variance_to_budget"])))
    if any(x["total"] for x in s["rows"]):
        r.chart("line", "Estimate by design milestone", [x["milestone"] for x in s["rows"]],
                [{"name": "Total", "values": [round(x["total"]) for x in s["rows"]]}])
    r.table("Milestone estimates", ["Milestone", "Title", "Total", "$/SF", "Δ vs prev", "Δ%", "Basis", "Date"],
            [[x["milestone"], x.get("title", ""), _money(x["total"]),
              _money(x["psf"]) if x["psf"] is not None else "—",
              _money(x["delta_total"]) if x["delta_total"] is not None else "—",
              f"{x['delta_pct']:+.1f}%" if x.get("delta_pct") is not None else "—",
              x.get("basis") or "", x.get("estimate_date") or ""]
             for x in s["rows"]] or [["(no estimate sets — create them under Preconstruction ▸ Estimate Sets)"] + [""] * 7])
    return r


def _decision_log(db: Session, pid: str, name: str) -> Report:
    from . import precon
    s = precon.decision_log(db, pid)
    r = Report("Decision Log", name)
    r.kpi("Decisions", s["decision_count"])
    r.kpi("Open", s["open_count"])
    r.kpi("Disputed", s["disputed_count"])
    r.kpi("Open cost exposure", _money(s["open_cost_exposure"]))
    r.kpi("Open schedule exposure", f"{s['open_schedule_exposure_days']} d")
    r.table("Decisions", ["Ref", "Decision", "Category", "Alignment", "State", "Cost", "Sched (d)", "Decide by"],
            [[x.get("ref", ""), x.get("subject", ""), x.get("category", ""), x.get("alignment", ""),
              x.get("state", ""), _money(x["cost_impact"]), x.get("schedule_impact_days", ""),
              x.get("due_date") or ""] for x in s["rows"]] or [["(no decisions logged)"] + [""] * 7])
    return r


def _assumptions_register(db: Session, pid: str, name: str) -> Report:
    from . import precon
    s = precon.assumptions(db, pid)
    r = Report("Assumptions & Clarifications", name)
    r.kpi("Assumptions", s["assumption_count"])
    r.kpi("Open", s["open_count"])
    r.kpi("Confirmed", s["confirmed_count"])
    r.kpi("Open allowance exposure", _money(s["open_cost_exposure"]))
    r.table("Register", ["Ref", "Assumption", "Category", "State", "Cost / allowance", "Owner"],
            [[x.get("ref", ""), x.get("subject", ""), x.get("category", ""), x.get("state", ""),
              _money(x["cost_impact"]), x.get("owner") or ""]
             for x in s["rows"]] or [["(no assumptions logged)"] + [""] * 5])
    return r


def _precon_alignment(db: Session, pid: str, name: str) -> Report:
    from . import precon
    s = precon.alignment(db, pid)
    r = Report("Preconstruction Alignment", name)
    r.kpi("Alignment score", f"{s['alignment_score']}/100" if s["alignment_score"] is not None else "—")
    r.kpi("Status", str(s["overall_status"]).upper())
    r.kpi("Latest estimate", f"{_money(s['latest_total'])} ({s['latest_milestone'] or '—'})")
    if s["variance_to_budget"] is not None:
        r.kpi("Vs budget", ("OVER " if s["variance_to_budget"] > 0 else "under ") + _money(abs(s["variance_to_budget"])))
    r.kpi("VE accepted / pipeline", f"{_money(s['ve_accepted'])} / {_money(s['ve_pipeline'])}")
    r.kpi("Open decisions / assumptions", f"{s['open_decisions']} / {s['open_assumptions']}")
    r.table("Alignment by domain", ["Domain", "Status", "Detail"],
            [[d["label"], d["status"].upper(), d["headline"]] for d in s["domains"]])
    return r


def _spec_submittal_log(db: Session, pid: str, name: str) -> Report:
    from . import specs
    s = specs.submittal_log(db, pid)
    r = Report("Spec-Driven Submittal Log", name)
    r.kpi("Spec sections", s["spec_count"])
    r.kpi("Required submittals", s["required_total"])
    r.kpi("Logged", s["logged_total"])
    r.kpi("Missing", s["missing_total"])
    r.kpi("Coverage", f"{s['coverage_pct']}%" if s["coverage_pct"] is not None else "—")
    if s["by_type"]:
        r.chart("bar", "Required submittals by type", list(s["by_type"].keys()),
                [{"name": "Count", "values": list(s["by_type"].values())}])
    r.table("By spec section", ["Section", "Title", "Division", "Required", "Logged", "Missing", "Responsible"],
            [[x.get("section_number", ""), x.get("title", ""), x.get("division", ""),
              x["required_count"], x["logged_count"],
              ("⚠ " + str(x["missing_count"])) if x["missing_count"] else "0", x.get("responsible") or ""]
             for x in s["rows"]] or [["(no spec sections — add them under Preconstruction ▸ Specifications)"] + [""] * 6])
    return r


def _site_feasibility(db: Session, pid: str, name: str) -> Report:
    from . import feasibility as feas
    f = feas.feasibility(db, pid)
    r = Report("Site Feasibility / Zoning Envelope", name)
    if f.get("error"):
        r.table("Feasibility", ["Status"], [[f"{f['error']} — add a Zoning & Site record under Preconstruction."]])
        return r
    def sf(v):
        return f"{v:,.0f} SF" if isinstance(v, (int, float)) else "—"
    r.kpi("Site area", f"{f['site_area_sf']:,.0f} SF ({f['site_area_acres']:g} ac)")
    r.kpi("Allowed GFA", sf(f.get("allowed_gfa_sf")))
    r.kpi("Binding constraint", f.get("binding_constraint") or "—")
    r.kpi("Max floors", f.get("max_floors") if f.get("max_floors") is not None else "—")
    r.kpi("Unit yield", f.get("unit_yield") if f.get("unit_yield") is not None else "—")
    r.kpi("Parking required", f.get("parking_required") if f.get("parking_required") is not None else "—")
    if f.get("constraints"):
        r.table("Envelope constraints (the minimum binds)", ["Constraint", "Limit GFA", "Basis"],
                [[c["constraint"], sf(c["limit_gfa_sf"]), c["basis"]] for c in f["constraints"]])
    m = f.get("model")
    if m:
        r.table("Model reconciliation", ["Actual GFA", "FAR used", "% of allowed", "Headroom", "Status"],
                [[sf(m["actual_gfa_sf"]), m["far_used"], f"{m['pct_of_allowed']}%",
                  sf(m["headroom_gfa_sf"]), m["status"]]])
    summary = [["Net buildable (efficiency-adjusted)", sf(f.get("net_buildable_sf"))],
               ["Buildable footprint", sf(f.get("buildable_footprint_sf"))],
               ["Required open space", sf(f.get("open_space_required_sf"))]]
    r.table("Program summary", ["Metric", "Value"], summary)
    if f.get("warnings"):
        r.table("Notes", ["Assumption / gap"], [[w] for w in f["warnings"]])
    return r


def _esg(db: Session, pid: str, name: str) -> Report:
    """ESG / sustainability summary: metered energy (EUI), GHG Scope 1/2, water, certifications,
    and the POE actual-vs-design comparison — the asset-level sustainability scorecard."""
    from . import energy as energy_mod
    from . import esg as esg_mod
    s = esg_mod.summary(db, pid, gfa_sf=energy_mod.project_gfa_sf(db, pid))
    perf = s["performance"]
    r = Report("ESG / Sustainability Summary", name)
    r.kpi("Site energy (kBtu)", f"{perf['energy']['total_kbtu']:,.0f}")
    r.kpi("EUI (kBtu/sf/yr)", perf["energy"]["eui_kbtu_sf_yr"] if perf["energy"]["eui_kbtu_sf_yr"] is not None else "—")
    r.kpi("GHG Scope 1 (tCO2e)", perf["ghg"]["scope1_tco2e"])
    r.kpi("GHG Scope 2 (tCO2e)", perf["ghg"]["scope2_tco2e"])
    r.kpi("Water (gal)", f"{perf['water']['gallons']:,.0f}")
    r.kpi("Certification points (achieved / targeted)",
          f"{s['certifications']['points_achieved']:.0f} / {s['certifications']['points_targeted']:.0f}")
    ghg_rows = [
        ["Scope 1 — on-site fuel", f"{perf['ghg']['scope1_tco2e']:,} tCO2e"],
        ["Scope 2 — purchased energy", f"{perf['ghg']['scope2_tco2e']:,} tCO2e"],
        ["Total", f"{perf['ghg']['total_tco2e']:,} tCO2e"],
        ["Intensity", f"{perf['ghg']['intensity_kgco2e_sf']} kgCO2e/sf" if perf["ghg"]["intensity_kgco2e_sf"] is not None else "— (needs GFA)"],
        ["Grid factor", f"{perf['ghg']['grid_factor_kgco2e_kwh']} kgCO2e/kWh"],
    ]
    r.table("Operational GHG emissions", ["Metric", "Value"], ghg_rows)
    poe = s["poe"]["latest"]
    if poe:
        r.table("Post-occupancy evaluation (latest)", ["Metric", "Value"], [
            ["Evaluation", f"{poe['ref']} ({poe['level'] or '-'}) — {poe['state']}"],
            ["Occupant satisfaction (1-7)", poe["satisfaction_score"] if poe["satisfaction_score"] is not None else "—"],
            ["Design EUI", poe["design_eui"] if poe["design_eui"] is not None else "—"],
            ["Actual (metered) EUI", poe["actual_eui"] if poe["actual_eui"] is not None else "—"],
            ["Gap vs design", f"{poe['eui_gap_pct']:+}%" if poe["eui_gap_pct"] is not None else "—"],
        ])
    r.table("Data coverage", ["Metric", "Value"],
            [["Meter months", s["data_coverage"]["meter_months"]],
             ["POE evaluations (reported / total)", f"{s['poe']['reported']} / {s['poe']['count']}"]])
    return r


def _fca(db: Session, pid: str, name: str) -> Report:
    """Facility Condition Assessment: the FCI + band, the deferred/renewal split, and the condition
    backlog broken out by UNIFORMAT group and by worst element."""
    from . import energy as energy_mod
    from . import fca as fca_mod
    s = fca_mod.index(db, pid, gfa_sf=energy_mod.project_gfa_sf(db, pid))
    r = Report("Facility Condition Assessment (FCI)", name)
    r.kpi("Facility Condition Index", f"{s['fci_pct']}% ({s['band']})")
    r.kpi("Current replacement value", _money(s["crv"]))
    r.kpi("Deferred maintenance", _money(s["deferred_maintenance"]))
    r.kpi("Capital renewal due", _money(s["capital_renewal"]))
    r.kpi("Elements assessed", s["elements"])
    r.kpi("Open deficiencies", s["open_deficiencies"])
    if s["by_uniformat"]:
        r.table("Condition by UNIFORMAT group", ["Group", "Elements", "Deferred", "Renewal", "CRV", "FCI %"],
                [[u["group"], u["count"], _money(u["deferred"]), _money(u["renewal"]), _money(u["crv"]),
                  f"{u['fci_pct']}%" if u["fci_pct"] is not None else "—"] for u in s["by_uniformat"]])
    if s["worst_elements"]:
        r.table("Worst elements (by cost)", ["Ref", "Element", "Group", "Condition", "Cost"],
                [[w["ref"], w["element"], w["uniformat"], w["condition"], _money(w["cost"])]
                 for w in s["worst_elements"]])
    if s["recommended_by_year"]:
        r.chart("bar", "Recommended spend by year", [str(x["year"]) for x in s["recommended_by_year"]],
                [{"name": "Cost", "values": [x["cost"] for x in s["recommended_by_year"]]}])
    return r


def _resilience(db: Session, pid: str, name: str) -> Report:
    """Climate & water resilience: the flood Design Flood Elevation + at-risk assets, and the
    Rational-Method stormwater peak flow + detention."""
    from . import resilience as rz
    fl = rz.flood_assessment(db, pid)
    sw = rz.stormwater(db, pid)
    wx = rz.weather(db, pid)
    cr = rz.climate_risk(db, pid, flood=fl, storm=sw, exposure=wx)   # reuse — don't recompute the scans
    r = Report("Climate & Water Resilience", name)
    r.kpi("Physical climate-risk rating", cr["rating"])
    r.kpi("Design Flood Elevation (ft)", fl["design_flood_elevation_ft"] if fl["design_flood_elevation_ft"] is not None else "—")
    r.kpi("In special flood hazard area", "Yes" if fl["in_special_flood_hazard_area"] else "No")
    r.kpi("Assets below DFE (flood-proof)", fl["at_risk_count"])
    r.kpi("Stormwater peak runoff (cfs)", sw["peak_runoff_cfs"])
    r.kpi("Detention volume (cf)", f"{sw['detention_volume_cf']:,.0f}")
    r.kpi("Weather-sensitive activities", wx["sensitive_count"])
    r.kpi("Weather-delay days logged", wx["weather_delay_days"])
    if fl["assets_at_risk"]:
        r.table("Assets below the Design Flood Elevation", ["Ref", "Asset", "Elev (ft)", "Below DFE by (ft)"],
                [[a["ref"], a["asset"], a["elevation_ft"], a["below_dfe_by_ft"]] for a in fl["assets_at_risk"]])
    if sw["by_surface"]:
        r.table("Stormwater by surface", ["Surface", "Area (sf)", "Peak (cfs)"],
                [[s["surface"], f"{s['area_sf']:,.0f}", s["peak_cfs"]] for s in sw["by_surface"]])
    if wx["site_risks"]:
        r.table("Site weather-risk register", ["Ref", "Hazard", "Season", "Severity", "Status"],
                [[x["ref"], x["hazard_type"], x["season"], x["severity"], x["state"]] for x in wx["site_risks"]])
    r.table("Physical climate-risk factors", ["Driver"], [[f] for f in cr["factors"]])
    return r


def _bim_kpi(db: Session, pid: str, name: str) -> Report:
    """BIM KPI scorecard (ISO 19650): the ten information-management categories graded, plus the
    handover data-drop acceptance checklist."""
    from . import bim_kpi
    sc = bim_kpi.scorecard(db, pid)
    ha = bim_kpi.handover_acceptance(db, pid)
    r = Report("BIM KPI Scorecard (ISO 19650)", name)
    s = sc["summary"]
    r.kpi("Health", f"{s['health_pct']}%" if s["health_pct"] is not None else "—")
    r.kpi("Good / Warn / Poor", f"{s['good']} / {s['warn']} / {s['poor']}")
    r.kpi("Not scored (n/a)", s["na"])
    r.kpi("Model scored", "yes" if sc["model_scored"] else "no")
    r.kpi("Handover acceptance", "ACCEPTED" if ha["accepted"] else "not ready")
    r.table("KPI categories", ["Category", "Grade", "Headline"],
            [[c["label"], c["grade"].upper(), c["headline"]] for c in sc["categories"]])
    r.table("Handover data-drop acceptance", ["Check", "Status"],
            [[c["label"], "OK" if c["ok"] else "missing"] for c in ha["checks"]])
    return r


def _bep(db: Session, pid: str, name: str) -> Report:
    """ISO 19650 BIM Execution Plan — a produced governance document, assembled from the CDE, the
    information-requirements register, the discipline vocabulary and the delivery (drawing-set)
    register. Answers WHO does WHAT, to WHAT level, WHEN, and HOW information is managed."""
    from . import cde, classification
    cde_st = cde.status(db, pid)
    reqs = cde.requirements(db, pid)
    disc = classification.disciplines()
    sets = _records(db, "drawing_set", pid)
    core = reqs["core_coverage"]

    r = Report("BIM Execution Plan (BEP)", name)
    r.kpi("Disciplines", len(disc))
    r.kpi("Information requirements", reqs["total"])
    r.kpi("Core coverage (EIR/BEP/AIR)",
          "complete" if core["complete"] else "missing " + ", ".join(core["missing"]))
    r.kpi("CDE containers", cde_st["total"])
    r.kpi("Published", cde_st["discipline"]["published"])
    r.kpi("Delivery sets", len(sets))
    r.kpi("Metadata completeness", f"{cde_st['discipline']['metadata_completeness_pct']}%")

    # 1. Information-requirements register (OIR / PIR / AIR / EIR / BEP / MIDP / TIDP)
    r.table("Information requirements register", ["Type", "Total", "Issued", "Draft", "Superseded"],
            [[code, b["total"], b["issued"], b["draft"], b["superseded"]]
             for code, b in reqs["by_type"].items()] or [["(none logged)", "", "", "", ""]])

    # 2. Roles, responsibilities & authorities (ISO 19650 appointment roles + discipline leads)
    roles = [["Appointing Party (Owner)", "Sets the EIR; approves deliverables; owns the asset information."],
             ["Lead Appointed Party (BIM Manager)", "Owns this BEP and the CDE; coordinates the federated model; QA."],
             ["Information Manager", "Runs the CDE workflow (WIP -> Shared -> Published -> Archived) and naming/standards."]]
    roles += [[f"{d['code']} — {d['name']} lead (Appointed Party)",
               f"Authors and coordinates the {d['name']} model; delivers MasterFormat "
               + ", ".join(d["divisions"]) + " content."] for d in disc]
    r.table("Roles, responsibilities & authorities", ["Role", "Responsibility"], roles)

    # 3. Level of Information Need (target LOD per delivery stage; A2 refines to per-element)
    r.table("Level of Information Need (target by stage)", ["Stage", "Target LOD", "Information focus"],
            [["Concept / SD (RIBA 2)", "LOD 200", "Generalized geometry, approximate quantities, orientation"],
             ["Design Development (RIBA 3)", "LOD 300", "Exact dimensions, materials, discipline coordination"],
             ["Construction Docs (RIBA 4)", "LOD 350", "System interfaces, clash coordination, connections"],
             ["Construction (RIBA 5)", "LOD 400", "Fabrication and installation detail, shop drawings"],
             ["Handover / As-built (RIBA 6)", "LOD 500", "Verified as-built condition and asset / O&M data"]])

    # 4. Information delivery / exchange schedule (MIDP / TIDP -> delivery sets)
    def _d2(x):
        return x.get("data") or x
    r.table("Information delivery schedule", ["Delivery set", "Discipline", "Issued", "Purpose", "State"],
            [[str(_d2(s).get("name") or _d2(s).get("title") or s.get("id", ""))[:60],
              _d2(s).get("discipline", ""),
              str(_d2(s).get("issued_date") or _d2(s).get("issue_date") or ""),
              _d2(s).get("purpose", ""), s.get("workflow_state", "")]
             for s in sets] or [["(no delivery sets registered)", "", "", "", ""]])

    # 5. Information standards & naming conventions
    r.table("Information standards & naming", ["Item", "Convention"],
            [["Sheet identification", "US NCS: discipline designator + sheet-type digit + sequence "
              "(e.g. A-101 = Architectural / Plans / 01)."],
             ["Container / file naming", "Type_Discipline_Description_Revision_Date; revision-controlled, "
              "approved files never overwritten."],
             ["Classification", "CSI MasterFormat divisions + Uniformat II elements, tagged via "
              "IfcClassificationReference and keyed to GlobalId."],
             ["Discipline designators", ", ".join(f"{d['code']}={d['name']}" for d in disc)]])

    # 6. CDE & information management (ISO 19650 states)
    st = cde_st["by_state"]
    r.table("CDE workflow (ISO 19650)", ["State", "Metric"],
            [["WIP", st.get("wip", 0)], ["Shared", st.get("shared", 0)],
             ["Published", st.get("published", 0)], ["Archived", st.get("archived", 0)],
             ["Revision control", f"{cde_st['discipline']['revision_control_pct']}%"],
             ["Approval-status coverage", f"{cde_st['discipline']['approval_status_pct']}%"]])

    # 7. Model coordination & quality assurance
    missing = core["missing"]
    r.table("Model coordination & QA", ["Process", "Definition"],
            [["Federation", "Discipline models federated on shared GlobalIds; each authored in its own container."],
             ["Clash detection", "Cross-discipline clash run each coordination cycle; issues round-tripped via BCF."],
             ["Model quality", "IDS validation + LOIN + metadata completeness scored in the openBIM quality "
              "scorecard and the BIM-KPI report."],
             ["Requirement coverage",
              "Compliant." if not missing else "Missing core requirement(s): " + ", ".join(missing)]])
    return r


def _lod(db: Session, pid: str, name: str) -> Report:
    """LOD matrix + achieved-LOD coverage of the loaded model (inferred from LOIN facets)."""
    from . import lod
    from .routers.properties import _INDEX, _ensure_loaded
    try:
        _ensure_loaded(pid)
    except Exception:                     # noqa: BLE001 — targets-only when no model is loaded
        pass
    a = lod.assess(db, pid, _INDEX.get(pid))
    r = Report("LOD Matrix & Coverage", name)
    r.kpi("Model scored", "yes" if a["model_scored"] else "no")
    r.kpi("Elements", a["elements"])
    r.kpi("Targets", len(a["targets"]) if a["targets"] else f"{len(a['default'])} (stage defaults)")
    if a["model_scored"] and a["elements"]:
        r.kpi("Most common LOD", max(a["distribution"].items(), key=lambda kv: kv[1])[0])
    tgt = a["targets"] or [{"phase": t["phase"], "discipline": "(all)", "element_category": "(all)",
                            "target_lod": t["target_lod"]} for t in a["default"]]
    r.table("Target LOD matrix", ["Stage", "Discipline", "Element / category", "Target LOD"],
            [[t.get("phase", ""), t.get("discipline", ""), t.get("element_category", ""),
              t.get("target_lod", "")] for t in tgt])
    if a["model_scored"]:
        r.table("Achieved LOD — distribution", ["LOD band", "Elements"],
                [[k, v] for k, v in a["distribution"].items()])
        r.table("Achieved LOD — by discipline", ["Discipline", "Elements", "Avg achieved LOD"],
                [[d["discipline"], d["elements"], d["avg_lod"]] for d in a["by_discipline"]]
                or [["(none)", "", ""]])
        r.chart("bar", "Achieved LOD distribution", list(a["distribution"].keys()),
                [{"name": "Elements", "values": list(a["distribution"].values())}])
    return r


def _naming(db: Session, pid: str, name: str) -> Report:
    """Naming-convention compliance across the CDE containers + drawing register."""
    from . import naming
    a = naming.audit(db, pid)
    conv = a["conventions"]
    cc, ss = a["containers"], a["sheets"]
    r = Report("Naming Convention Compliance", name)
    r.kpi("Container documents", cc["total"])
    r.kpi("Container compliance", f"{cc['compliance_pct']}%" if cc["compliance_pct"] is not None else "—")
    r.kpi("Drawing sheets", ss["total"])
    r.kpi("Sheet-ID compliance", f"{ss['compliance_pct']}%" if ss["compliance_pct"] is not None else "—")
    r.table("Conventions", ["Kind", "Pattern", "Example / note"],
            [["Container / document", conv["container"]["pattern"], conv["container"]["note"]],
             ["Drawing sheet", conv["sheet"]["pattern"], conv["sheet"]["note"]]])
    r.table("Container naming violations", ["Name", "Issues"],
            [[v["name"], "; ".join(v["issues"])] for v in cc["violations"]] or [["(all compliant)", ""]])
    r.table("Sheet-ID violations", ["Sheet", "Issues"],
            [[v["name"], "; ".join(v["issues"])] for v in ss["violations"]] or [["(all compliant)", ""]])
    return r


def _market_intelligence(db: Session, pid: str, name: str) -> Report:
    """Regional escalation / labour / location table + the warm-cold sector board, and this project's
    escalation to its construction midpoint (from its market_assumption record if one exists)."""
    from . import market_intelligence as mi
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


def _document_control(db: Session, pid: str, name: str) -> Report:
    """Document-control health over the standard folder taxonomy: naming, required-folder coverage,
    revision control, CDE-state spread and required-doc gaps."""
    from . import docmanager
    h = docmanager.health(pid)
    t = docmanager.tree(pid)

    def _p(v):
        return f"{v}%" if v is not None else "—"
    r = Report("Document Control Health", name)
    r.kpi("Documents on file", h["total_files"])
    r.kpi("Naming compliance", _p(h["naming_compliance_pct"]))
    r.kpi("Required-folder coverage", _p(h["required_coverage_pct"]))
    r.kpi("Revision control", _p(h["revision_control_pct"]))
    if h["by_cde_state"]:
        r.chart("bar", "Documents by CDE state", list(h["by_cde_state"].keys()),
                [{"name": "Files", "data": list(h["by_cde_state"].values())}])
    r.table("Required documents still missing", ["Folder"],
            [[p] for p in h["required_missing"]] or [["(all required folders populated)"]])
    r.table("Folders (file counts + owner)", ["Folder", "Owner", "Files"],
            [[n["path"], n.get("owner_role") or "", n["count"]]
             for n in t["nodes"] if n["depth"] == 0])
    return r


def _design_options(db: Session, pid: str, name: str) -> Report:
    """Design options / variants compared on program + economics, best-in-class per metric."""
    from . import design_options
    a = design_options.compare(db, pid)
    r = Report("Design Options Comparison", name)
    r.kpi("Options", a["count"])
    r.kpi("Selected", a["selected"] or "—")
    for ldr in a["leaders"].values():
        if ldr["option"]:
            r.kpi(ldr["label"], ldr["option"])
    r.table("Options", ["Option", "State", "Area (sf)", "Units", "Eff %", "Hard cost", "$/sf", "EUI", "IRR %"],
            [[o["name"], o["state"], o["gross_area_sf"], o["unit_count"], o["efficiency_pct"],
              _money(o["hard_cost"]) if o["hard_cost"] is not None else "", o["cost_per_sf"],
              o["energy_eui"], o["irr_pct"]] for o in a["options"]] or [["(no options)"] + [""] * 8])
    if any(o["irr_pct"] is not None for o in a["options"]):
        r.chart("bar", "Levered IRR by option", [o["name"] for o in a["options"]],
                [{"name": "IRR %", "values": [o["irr_pct"] or 0 for o in a["options"]]}])
    return r


def _design_standards(db: Session, pid: str, name: str) -> Report:
    """Design-standards ruleset + model compliance (prohibited / non-approved type + material use)."""
    from . import design_standards
    from .routers.properties import _INDEX, _ensure_loaded
    try:
        _ensure_loaded(pid)
    except Exception:                     # noqa: BLE001 — ruleset-only when no model is loaded
        pass
    a = design_standards.check(db, pid, _INDEX.get(pid))
    rs = a["ruleset"]
    r = Report("Design Standards Compliance", name)
    r.kpi("Standards", rs["count"])
    r.kpi("Approved / preferred", len(rs["by_status"]["approved"]) + len(rs["by_status"]["preferred"]))
    r.kpi("Prohibited", len(rs["by_status"]["prohibited"]))
    r.kpi("Model scored", "yes" if a["model_scored"] else "no")
    if a["model_scored"]:
        r.kpi("Prohibited hits", a["prohibited_hits"])
        r.kpi("Unapproved", a["unapproved"])
    r.table("Ruleset", ["Item", "Category", "Status", "Discipline", "Match keyword"],
            [[i["name"], i["category"], i["status"], i["discipline"], i["match_keyword"]]
             for i in rs["items"]] or [["(none defined)"] + [""] * 4])
    if a["model_scored"]:
        r.table("Model violations", ["Element", "Type", "Issue"],
                [[v["guid"][:22], v["type"], v["issue"]] for v in a["violations"]] or [["(none)", "", ""]])
    return r


def _mep(db: Session, pid: str, name: str) -> Report:
    """MEP equipment schedule + per-system rollup + first-pass duct/pipe sizing reference tables."""
    from . import mep
    s = mep.schedule(db, pid)
    r = Report("MEP Equipment Schedule", name)
    r.kpi("Equipment items", s["count"])
    r.kpi("Systems", len(s["by_system"]))
    r.table("Equipment schedule", ["Tag", "Type", "System", "Capacity", "Unit", "Flow", "Size", "State"],
            [[i["tag"], i["type"], i["system"], i["capacity"], i["capacity_unit"], i["flow"],
              i["size"], i["state"]] for i in s["items"]] or [["(none)"] + [""] * 7])
    r.table("System rollup", ["System", "Items", "Total capacity"],
            [[b["system"], b["count"],
              ", ".join(f"{v} {u}" for u, v in b["capacity_by_unit"].items()) or "—"]
             for b in s["by_system"]] or [["(none)", "", ""]])
    # model-derived MEP counts (complements the register when a model is loaded)
    try:
        from .routers.properties import _INDEX, _ensure_loaded
        _ensure_loaded(pid)
        mx = mep.extract_from_model(_INDEX.get(pid))
    except Exception:                     # noqa: BLE001 — targets-only when no model is loaded
        mx = {"model_scored": False, "mep_elements": 0, "by_class": []}
    if mx.get("model_scored"):
        r.kpi("MEP elements (model)", mx["mep_elements"])
        r.table("MEP elements off the model", ["IFC class", "Type", "Count"],
                [[x["ifc_class"], x["label"], x["count"]] for x in mx["by_class"]] or [["(none)", "", ""]])
    r.table("Duct sizing reference (equal-velocity @ 1000 fpm)", ["CFM", "Round diameter (in)"],
            [[q, mep.size_duct(q)["round_diameter_in"]] for q in (500, 1000, 2000, 4000, 8000)])
    r.table("Pipe sizing reference (velocity @ 6 fps)", ["GPM", "Nominal size (in)"],
            [[q, mep.size_pipe(q)["nominal_pipe_size_in"]] for q in (20, 50, 100, 200, 400)])
    return r


def _productivity(db: Session, pid: str, name: str) -> Report:
    """Field labor productivity — per-entry units/man-hour + a by-trade rollup."""
    from . import productivity
    s = productivity.summary(db, pid)
    r = Report("Field Labor Productivity", name)
    r.kpi("Entries", s["count"])
    r.kpi("Total man-hours", s["total_man_hours"])
    r.kpi("Overall units/man-hr", s["overall_units_per_manhour"] if s["overall_units_per_manhour"] is not None else "—")
    r.table("By trade", ["Trade", "Quantity", "Man-hours", "Units/man-hr"],
            [[t["trade"], t["quantity"], t["man_hours"], t["units_per_manhour"]]
             for t in s["by_trade"]] or [["(none)", "", "", ""]])
    r.table("Entries", ["Date", "Trade", "Activity", "Qty", "Unit", "Man-hrs", "Units/man-hr"],
            [[e["date"], e["trade"], e["activity"], e["quantity"], e["unit"], e["man_hours"],
              e["units_per_manhour"]] for e in s["entries"]] or [["(no entries)"] + [""] * 6])
    if s["by_trade"]:
        r.chart("bar", "Productivity by trade (units/man-hr)", [t["trade"] for t in s["by_trade"]],
                [{"name": "Units/man-hr", "values": [t["units_per_manhour"] or 0 for t in s["by_trade"]]}])
    return r


def _envelope(db: Session, pid: str, name: str) -> Report:
    """Envelope assemblies checked against IECC 2021 climate-zone minimums."""
    from . import envelope
    a = envelope.audit(db, pid)
    r = Report("Envelope Code Compliance (IECC 2021)", name)
    r.kpi("Assemblies", a["total"])
    r.kpi("Checked", a["checked"])
    r.kpi("Compliant", a["compliant"])
    r.kpi("Compliance", f"{a['compliance_pct']}%" if a["compliance_pct"] is not None else "—")
    r.table("Envelope compliance", ["Assembly", "Type", "Zone", "Provided", "Required", "Result"],
            [[x.get("name", ""), x.get("element_type", ""), x.get("climate_zone", ""),
              (f"R{x['provided_r']}" if x.get("provided_r") is not None else
               (f"U{x['provided_u']}" if x.get("provided_u") is not None else "—")),
              (f"R≥{x['required_min_r']}" if "required_min_r" in x else
               (f"U≤{x['required_max_u']}" if "required_max_u" in x else "—")),
              ("PASS" if x["compliant"] else "FAIL") if x.get("compliant") is not None
              else x.get("issue", "—")]
             for x in a["results"]] or [["(no assemblies)"] + [""] * 5])
    return r


def _resource_loading(db: Session, pid: str, name: str) -> Report:
    """Resource histogram + S-curve + peak manpower from the crew-loaded schedule."""
    from . import resource_loading
    a = resource_loading.loading(db, pid)
    r = Report("Resource-Loaded Schedule", name)
    r.kpi("Loaded activities", a["activities_loaded"])
    r.kpi("Weeks", a["weeks_span"])
    r.kpi("Trades", len(a["trades"]))
    r.kpi("Peak crew", f"{a['peak']['crew']} ({a['peak']['week']})" if a["peak"]["week"] else "—")
    r.table("Weekly resource histogram", ["Week", "Total crew"] + a["trades"],
            [[w["week"], w["total"]] + [w["by_trade"].get(t, 0) for t in a["trades"]]
             for w in a["histogram"]] or [["(no crew-loaded activities)"] + [""] * (len(a["trades"]) + 1)])
    if a["histogram"]:
        r.chart("bar", "Crew histogram (peak manpower/week)", [w["week"] for w in a["histogram"]],
                [{"name": "Crew", "values": [w["total"] for w in a["histogram"]]}])
        r.chart("line", "Cumulative man-weeks (S-curve)", [p["week"] for p in a["scurve"]],
                [{"name": "Cumulative", "values": [p["cumulative"] for p in a["scurve"]]}])
    return r


def build(db: Session, pid: str, report: str) -> Report:
    p = db.get(Project, pid)
    name = (p.name if p else pid)
    if report == "bep":
        return _bep(db, pid, name)
    if report == "design_options":
        return _design_options(db, pid, name)
    if report == "design_standards":
        return _design_standards(db, pid, name)
    if report == "mep":
        return _mep(db, pid, name)
    if report == "resource_loading":
        return _resource_loading(db, pid, name)
    if report == "envelope":
        return _envelope(db, pid, name)
    if report == "productivity":
        return _productivity(db, pid, name)
    if report == "lod":
        return _lod(db, pid, name)
    if report == "document_control":
        return _document_control(db, pid, name)
    if report == "market_intelligence":
        return _market_intelligence(db, pid, name)
    if report == "naming":
        return _naming(db, pid, name)
    if report == "appraisal":
        return _appraisal(db, pid, name)
    if report == "rent_roll":
        return _rent_roll(db, pid, name)
    if report == "lease_management":
        return _lease_management(db, pid, name)
    if report == "cap_table":
        return _cap_table(db, pid, name)
    if report == "tm_log":
        return _tm_log(db, pid, name)
    if report == "submittal_register":
        return _submittal_register(db, pid, name)
    if report == "quality":
        return _quality(db, pid, name)
    if report == "rfi_register":
        return _rfi_register(db, pid, name)
    if report == "field_log":
        return _field_log(db, pid, name)
    if report == "safety_dashboard":
        return _safety(db, pid, name)
    if report == "closeout":
        return _closeout(db, pid, name)
    if report == "project_health":
        return _project_health(db, pid, name)
    if report == "co_log":
        return _co_log(db, pid, name)
    if report == "action_tracker":
        return _action_tracker(db, pid, name)
    if report == "estimate_continuity":
        return _estimate_continuity(db, pid, name)
    if report == "decision_log":
        return _decision_log(db, pid, name)
    if report == "assumptions_register":
        return _assumptions_register(db, pid, name)
    if report == "precon_alignment":
        return _precon_alignment(db, pid, name)
    if report == "spec_submittal_log":
        return _spec_submittal_log(db, pid, name)
    if report == "site_feasibility":
        return _site_feasibility(db, pid, name)
    if report == "esg":
        return _esg(db, pid, name)
    if report == "fca":
        return _fca(db, pid, name)
    if report == "resilience":
        return _resilience(db, pid, name)
    if report == "bim_kpi":
        return _bim_kpi(db, pid, name)
    if report == "listing_factsheet":
        return _listing_factsheet(db, pid, name)
    if report == "marketing_flyer":
        return _marketing_flyer(db, pid, name)
    if report == "executive":
        return _executive(db, pid, name)
    if report == "risk":
        return _risk(db, pid, name)
    if report == "cost":
        return _cost(db, pid, name)
    if report == "evm":
        return _evm(db, pid, name)
    if report == "contracts":
        return _contracts(db, pid, name)
    if report == "financials":
        return _financials(db, pid, name)
    logs = {
        "change_orders": ("cor", "Change Order Log", [("subject", "Subject"), ("amount", "Amount"), ("reason", "Reason")]),
        "rfi": ("rfi", "RFI Log", [("subject", "Subject"), ("discipline", "Discipline"), ("cost_impact", "Cost impact")]),
        "submittals": ("submittal", "Submittal Log", [("title", "Title"), ("spec_section", "Spec"), ("type", "Type")]),
        "daily": ("daily_report", "Daily Report Log", [("report_date", "Date"), ("weather", "Weather")]),
        "safety": ("incident", "Safety / Incident Log", [("subject", "Subject"), ("classification", "Class"), ("severity", "Severity")]),
    }
    if report in logs:
        key, title, cols = logs[report]
        return _log(db, pid, name, key, title, cols)
    raise ValueError(f"unknown report {report!r}")


