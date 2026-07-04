"""Capture a read-only sample dataset for the GitHub Pages (VITE_PAGES) viewer demo.

Seeds one realistic project against an in-process API (no server), crawls the GET endpoints
the web app calls, and writes apps/web/src/demo/demoData.json as { "GET <path>": <body> }.
The web client serves these in the viewer-only demo so the GC portal / Budget / Finance
panels render with real data offline. Re-run after model/seed changes:

    PYTHONPATH=src ./.venv/Scripts/python.exe build_demo_data.py
"""
from __future__ import annotations

import json
import os

os.environ["DATABASE_URL"] = "sqlite:///./_demo_capture.db"
os.environ["STORAGE_DIR"] = "./_demo_capture_storage"
os.environ.pop("AEC_RBAC", None)
for _f in ("./_demo_capture.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient   # noqa: E402
from aec_api.main import app                # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "apps", "web", "src", "demo", "demoData.json")
snap: dict[str, object] = {}


def mk(c, pid, key, data, assignee=None):
    body: dict = {"data": data}
    if assignee:
        body["assignee"] = assignee
    r = c.post(f"/projects/{pid}/modules/{key}", json=body)
    assert r.status_code in (200, 201), f"{key}: {r.status_code} {r.text[:160]}"
    return r.json()["id"]


def act(c, pid, key, rid, action):
    c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})


def grab(c, path, *, as_text=False):
    r = c.get(path)
    if r.status_code != 200:
        print(f"  skip {path} -> {r.status_code}")
        return None
    snap[f"GET {path}"] = r.text if as_text else r.json()
    return r.text if as_text else r.json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Demo Tower"}).json()["id"]

    # --- cost chain (by CSI division) + buyout + actuals ---
    codes = {
        "03-3000": ("Cast-in-place concrete", "03", 4_800_000),
        "05-1200": ("Structural steel", "05", 6_200_000),
        "23-0000": ("HVAC", "23", 3_100_000),
        "26-0000": ("Electrical", "26", 2_700_000),
        "09-2900": ("Gypsum board", "09", 1_350_000),
        "01-5000": ("General requirements", "01", 1_200_000),
    }
    ccs = {}
    for code, (desc, div, bud) in codes.items():
        cc = mk(c, pid, "cost_code", {"code": code, "description": desc, "division": div})
        ccs[code] = cc
        mk(c, pid, "budget", {"cost_code": cc, "description": desc, "revised": bud})
        if div != "01":
            com = mk(c, pid, "commitment", {"description": f"{desc} sub", "cost_code": cc, "amount": round(bud * 0.92)})
            act(c, pid, "commitment", com, "execute")
            mk(c, pid, "direct_cost", {"description": "Equipment & misc", "cost_code": cc, "amount": round(bud * 0.03)})
    pc = mk(c, pid, "prime_contract", {"name": "GMP - Demo Tower", "type": "GMP", "value": 41_000_000,
                                       "overhead_pct": 5, "fee_pct": 4, "contingency_pct": 3})
    for i, amt in enumerate([2_400_000, 3_100_000, 2_750_000], 1):
        mk(c, pid, "owner_invoice", {"number": f"INV-{i:03d}", "amount": amt, "prime_contract": pc, "period": f"2026-0{i+2}-01"})
    for role, cat, rate in [("Project Executive", "General Conditions", 8000), ("Senior Project Manager", "General Conditions", 22000),
                            ("Superintendent", "General Conditions", 20000), ("Safety Manager", "General Requirements", 15000)]:
        mk(c, pid, "staffing", {"role": role, "category": cat, "count": 1, "rate": rate, "rate_period": "Month", "start": "2026-01-01", "finish": "2026-12-31"})
    acts = [("Sitework", "Sitework", "2026-01-05", "2026-02-15", 1_500_000, 100),
            ("Foundations", "Concrete", "2026-02-10", "2026-04-10", 4_800_000, 80),
            ("Superstructure", "Steel", "2026-04-01", "2026-08-15", 6_200_000, 40),
            ("MEP rough-in", "MEP", "2026-06-01", "2026-10-30", 5_800_000, 10),
            ("Interiors & finishes", "Finishes", "2026-09-01", "2027-01-31", 4_200_000, 0)]
    for i, (name, trade, s, f, bud, pct) in enumerate(acts):
        mk(c, pid, "schedule_activity", {"name": name, "trade": trade, "start": s, "finish": f, "budget": bud, "percent": pct, "wbs": f"01.{i+1:02d}"})
    c.post(f"/projects/{pid}/cost/sov/from-budget?replace=true")

    # pull-plan phase board (Last Planner) — sticky notes across trade swimlanes × weeks, with the
    # concrete->steel hand-off, a made-ready/committed/done chain, a missed task (variance), and a
    # still-constrained task, so the demo board shows readiness + PPC + a make-ready log.
    MS = "L3 slab topping-out"
    conc = mk(c, pid, "pull_plan_task", {"task": "Form & pour L3 deck", "milestone": MS, "trade": "Concrete",
        "responsible": "J. Rivera (Concrete)", "duration_days": 5, "planned_week": "2026-W28"})
    act(c, pid, "pull_plan_task", conc, "make_ready"); act(c, pid, "pull_plan_task", conc, "commit")
    act(c, pid, "pull_plan_task", conc, "complete")
    mep = mk(c, pid, "pull_plan_task", {"task": "Rough-in L3 conduit", "milestone": MS, "trade": "MEP",
        "responsible": "P. Shah (Elec)", "duration_days": 4, "planned_week": "2026-W28"})
    act(c, pid, "pull_plan_task", mep, "make_ready"); act(c, pid, "pull_plan_task", mep, "commit")
    c.patch(f"/projects/{pid}/modules/pull_plan_task/{mep}", json={"variance_reason": "Materials"})
    act(c, pid, "pull_plan_task", mep, "miss")
    mk(c, pid, "pull_plan_task", {"task": "Set L4 columns", "milestone": MS, "trade": "Steel",
        "responsible": "K. Ito (Steel)", "duration_days": 3, "planned_week": "2026-W29",
        "predecessor": conc, "constraints": ["Materials", "Prerequisite work"]})
    mk(c, pid, "pull_plan_task", {"task": "Hang L3 drywall", "milestone": MS, "trade": "Interiors",
        "responsible": "D. Cole (Interiors)", "duration_days": 6, "planned_week": "2026-W30",
        "constraints": ["Prerequisite work"]})

    # change-management + QA + bidding + field + safety chains
    rfis = []
    for subj, disc, ci in [("Beam clash at grid C4", "Structural", "Yes"), ("Door schedule mismatch L3", "Architectural", "Possible"), ("VAV duct routing conflict", "MEP", "None")]:
        # the first RFI gets answered; the workflow gates 'respond' on the `answer` field.
        extra = {"answer": "Revise the connection per SK-12; added steel covered by COR 001."} if not rfis else {}
        rfis.append(mk(c, pid, "rfi", {"subject": subj, "question": "Please advise.", "discipline": disc, "cost_impact": ci, **extra}, "consultant"))
    act(c, pid, "rfi", rfis[0], "submit"); act(c, pid, "rfi", rfis[0], "respond"); act(c, pid, "rfi", rfis[1], "submit")
    ce = mk(c, pid, "change_event", {"subject": "Added steel at C4", "rom": 85000, "source_rfi": rfis[0], "trades": ["Steel", "Concrete"]}, "pm")
    pco = mk(c, pid, "pco_request", {"subject": "PCO - added steel", "description": "Added WF beam + connections at C4", "rough_cost": 92500, "source_rfi": rfis[0], "change_event": ce}, "owner")
    mk(c, pid, "cor", {"subject": "COR 001 - steel", "amount": 92500, "justification": "Owner-directed", "pco": pco})
    insp = mk(c, pid, "inspection", {"subject": "Level 2 deck pour", "inspection_type": "Structural",
                                     "location": "Grid C-E", "result": "Fail", "date": "2026-06-14"}, "qa")
    mk(c, pid, "ncr", {"subject": "Honeycomb at column", "description": "Voids on north face", "severity": "Major",
                       "disposition": "Rework", "inspection": insp}, "sub")
    mk(c, pid, "submittal", {"title": "Rebar shop drawings", "type": "Shop Drawing", "spec_section": "03 20 00", "discipline": "Structural"}, "sub")

    # --- specifications register -> spec-driven submittal log (shows coverage + a missing-submittal gap) ---
    mk(c, pid, "spec_section", {"section_number": "03 30 00", "title": "Cast-in-Place Concrete", "division": "03 - Concrete",
                                "responsible": "Concrete sub", "submittals_required":
                                "Product Data: each manufactured material; Shop Drawings: reinforcement placing drawings; "
                                "Samples: each exposed architectural finish."})
    mk(c, pid, "spec_section", {"section_number": "07 92 00", "title": "Joint Sealants", "division": "07 - Thermal & Moisture",
                                "responsible": "Caulking sub", "submittals_required":
                                "Product Data: sealant; Samples: color; Warranty: 5-year."})
    # log a couple of submittals against 03 30 00 so the log shows partial coverage (and 07 92 00 as a gap)
    mk(c, pid, "submittal", {"title": "Concrete mix design - product data", "type": "Product Data", "spec_section": "03 30 00", "discipline": "Structural"}, "sub")
    mk(c, pid, "submittal", {"title": "Architectural finish samples", "type": "Sample", "spec_section": "03 30 00", "discipline": "Architectural"}, "sub")

    # --- zoning & site -> the feasibility / zoning-envelope study ---
    mk(c, pid, "zoning", {"site": "Demo Tower parcel", "jurisdiction": "DT-3 Downtown", "use_type": "Mixed-Use",
                          "site_area_sf": 20_000, "far": 6.0, "height_limit_ft": 240, "floor_to_floor_ft": 12,
                          "lot_coverage_pct": 80, "efficiency_pct": 85, "avg_unit_sf": 850,
                          "parking_ratio": 0.5, "open_space_pct": 10})
    bp = mk(c, pid, "bid_package", {"name": "Concrete package", "trade": "Concrete", "budget": 5_000_000})
    for bidder, amt in [("ACME Concrete", 4_780_000), ("Bedrock Co", 4_950_000), ("Pour Bros", 5_120_000)]:
        mk(c, pid, "bid_submission", {"bidder": bidder, "package": bp, "amount": amt})
    for d, w, crews in [("2026-06-13", "Clear", [12, 8]), ("2026-06-14", "Rain", [6, 4])]:
        dr = mk(c, pid, "daily_report", {"report_date": d, "weather": w})
        for cnt in crews:
            mk(c, pid, "manpower_log", {"company": "Self-perform", "date": d, "count": cnt, "daily_report": dr})
    mk(c, pid, "incident", {"subject": "Near miss - dropped tool", "description": "No injury", "date": "2026-06-13", "classification": "Near Miss", "severity": "Near Miss"}, "safety")
    mk(c, pid, "punchlist", {"description": "Touch-up paint L2 corridor", "location": "L2", "trade": "Finishes"})

    # --- pre-acquisition: due diligence + entitlements (go/no-go rollup) ---
    esa = mk(c, pid, "due_diligence", {"subject": "Phase I ESA", "category": "Phase I ESA (ASTM E1527)",
                                       "consultant": "EnviroCo", "findings": "No RECs identified."})
    act(c, pid, "due_diligence", esa, "submit_report"); act(c, pid, "due_diligence", esa, "clear")
    geo = mk(c, pid, "due_diligence", {"subject": "Geotech borings", "category": "Geotechnical",
                                       "findings": "High water table; deep foundations likely.", "risk": "High"})
    act(c, pid, "due_diligence", geo, "submit_report"); act(c, pid, "due_diligence", geo, "flag")
    mk(c, pid, "due_diligence", {"subject": "Traffic impact study", "category": "Traffic Study", "consultant": "TransPlan"})
    rez = mk(c, pid, "entitlement", {"subject": "Rezone to MU-2", "application_type": "Rezoning",
                                     "agency": "City Planning", "hearing_date": "2026-05-12",
                                     "approval_expires": "2026-11-01"})
    act(c, pid, "entitlement", rez, "submit"); act(c, pid, "entitlement", rez, "schedule_hearing"); act(c, pid, "entitlement", rez, "approve")

    # --- design-phase lifecycle spine (RIBA/AIA gates) ---
    c.post(f"/projects/{pid}/lifecycle/seed")

    # --- operations: CMMS (PM -> preventive WOs) + meters/energy ---
    mk(c, pid, "pm_schedule", {"subject": "AHU-1 quarterly filter change", "frequency_days": 90,
                               "next_due": "2026-06-30", "tasks": "Replace filters; check belts.", "est_hours": 3})
    mk(c, pid, "pm_schedule", {"subject": "Fire pump churn test", "frequency_days": 30,
                               "next_due": "2026-06-28", "tasks": "Weekly churn; log pressures.", "est_hours": 1})
    mk(c, pid, "work_order", {"subject": "Leaking valve, mechanical rm 210", "wo_type": "Corrective",
                              "priority": "High", "due_date": "2026-06-30", "location": "Level 2 / Rm 210"})
    c.post(f"/projects/{pid}/cmms/generate-pm")
    elec = mk(c, pid, "meter", {"subject": "Main electric", "utility": "Electric", "unit": "kWh", "meter_number": "E-4471"})
    gasm = mk(c, pid, "meter", {"subject": "Gas service", "utility": "Natural Gas", "unit": "therms"})
    wat = mk(c, pid, "meter", {"subject": "Domestic water", "utility": "Water", "unit": "gallons"})
    for mo, kwh, thm, gal in [("2026-01", 12400, 610, 41000), ("2026-02", 11100, 540, 39000),
                              ("2026-03", 10800, 410, 42000), ("2026-04", 9900, 280, 44000),
                              ("2026-05", 10600, 150, 47000), ("2026-06", 12100, 90, 52000)]:
        mk(c, pid, "meter_reading", {"subject": f"elec {mo}", "meter": elec, "reading_date": f"{mo}-28",
                                     "consumption": kwh, "cost": round(kwh * 0.12, 2)})
        mk(c, pid, "meter_reading", {"subject": f"gas {mo}", "meter": gasm, "reading_date": f"{mo}-28",
                                     "consumption": thm, "cost": round(thm * 1.1, 2)})
        mk(c, pid, "meter_reading", {"subject": f"water {mo}", "meter": wat, "reading_date": f"{mo}-28", "consumption": gal})

    # --- hold phase: assets w/ reserve data, CIP, leases, CAM, certification, POE ---
    mk(c, pid, "asset_register", {"name": "RTU-1 rooftop unit", "location": "Roof", "install_date": "2010-06-01",
                                  "expected_life_years": 20, "replacement_cost": 85000})
    mk(c, pid, "asset_register", {"name": "Passenger elevator", "install_date": "2012-01-01",
                                  "expected_life_years": 25, "replacement_cost": 220000})
    mk(c, pid, "capital_plan", {"subject": "Roof membrane replacement", "category": "Roof", "planned_year": 2028,
                                "cost": 250000, "priority": "Recommended (end of life)", "funding_source": "Reserves"})
    # facility condition assessment — elements w/ condition + deficiency cost feed the FCI + reserve study
    mk(c, pid, "fca_element", {"element": "Roof membrane (EPDM)", "uniformat": "B - Shell / Envelope",
                               "condition_rating": "4 - Poor", "install_date": "2009-06-01", "expected_life_years": 20,
                               "replacement_cost": 250000, "deficiency": "Blistering + ponding at NE corner",
                               "deficiency_cost": 60000, "recommended_year": 2026})
    mk(c, pid, "fca_element", {"element": "Curtain wall sealant", "uniformat": "B - Shell / Envelope",
                               "condition_rating": "3 - Fair", "replacement_cost": 180000,
                               "deficiency": "Failed sealant joints, water intrusion", "deficiency_cost": 22000, "recommended_year": 2027})
    mk(c, pid, "fca_element", {"element": "Chiller CH-1", "uniformat": "D - Services (MEP)", "condition_rating": "4 - Poor",
                               "install_date": "2006-01-01", "expected_life_years": 20, "replacement_cost": 320000,
                               "deficiency": "Past useful life, refrigerant leaks", "deficiency_cost": 40000, "recommended_year": 2026})
    mk(c, pid, "fca_element", {"element": "Lobby flooring", "uniformat": "C - Interiors", "condition_rating": "2 - Good",
                               "replacement_cost": 90000})
    mk(c, pid, "fca_element", {"element": "Parking lot paving", "uniformat": "G - Building Sitework", "condition_rating": "3 - Fair",
                               "replacement_cost": 140000, "deficiency": "Cracking + faded striping", "deficiency_cost": 18000, "recommended_year": 2028})
    mk(c, pid, "lease", {"tenant": "Acme Corp", "suite": "100", "rentable_sf": 10000, "base_rent_annual": 300000,
                         "lease_type": "NNN", "recovery_psf": 5, "start_date": "2025-01-01", "end_date": "2030-12-31"})
    mk(c, pid, "lease", {"tenant": "Beta LLC", "suite": "200", "rentable_sf": 5000, "base_rent_annual": 140000,
                         "lease_type": "NNN", "recovery_psf": 4, "start_date": "2025-06-01", "end_date": "2028-05-31"})
    mk(c, pid, "cam_expense", {"subject": "Janitorial contract", "category": "Cleaning / Janitorial", "year": 2026,
                               "budget_annual": 90000, "actual_annual": 100000, "variable": "Yes", "recoverable": "Yes"})
    mk(c, pid, "cam_expense", {"subject": "Property insurance", "category": "Insurance", "year": 2026,
                               "budget_annual": 45000, "actual_annual": 50000, "variable": "No", "recoverable": "Yes"})
    mk(c, pid, "leed_credit", {"credit": "Optimize Energy Performance", "category": "Energy",
                               "points_targeted": 10, "points_achieved": 6})
    poe = mk(c, pid, "poe", {"subject": "Year-1 POE", "level": "2 - Investigative (survey + metered data)",
                             "survey_date": "2026-06-01", "occupants_surveyed": 40, "satisfaction_score": 5.2,
                             "design_eui": 40, "findings": "Comfort acceptable; plug loads above design."})
    act(c, pid, "poe", poe, "start_fieldwork"); act(c, pid, "poe", poe, "publish_report")

    # --- standards (ISO 19650): CDE containers + information requirements ---
    eir = mk(c, pid, "info_requirement", {"title": "Project EIR", "req_type": "EIR - Exchange Information Requirements",
                                          "appointing_party": "Owner LLC", "lead_appointed_party": "GC Inc"})
    act(c, pid, "info_requirement", eir, "issue")
    bep = mk(c, pid, "info_requirement", {"title": "BIM Execution Plan", "req_type": "BEP - BIM Execution Plan",
                                          "lead_appointed_party": "GC Inc"})
    act(c, pid, "info_requirement", bep, "issue")
    mk(c, pid, "info_requirement", {"title": "Asset Information Requirements",
                                    "req_type": "AIR - Asset Information Requirements", "appointing_party": "Owner LLC"})
    ic = mk(c, pid, "information_container", {"title": "Arch GA plans", "info_type": "Drawing",
                                             "discipline": "Architectural", "originator": "AR"})
    c.patch(f"/projects/{pid}/modules/information_container/{ic}", json={"suitability_code": "S2 - Shared for information"})
    act(c, pid, "information_container", ic, "share")
    c.patch(f"/projects/{pid}/modules/information_container/{ic}",
            json={"revision": "P01", "suitability_code": "A - Published for construction"})
    act(c, pid, "information_container", ic, "publish")
    mk(c, pid, "information_container", {"title": "Struct model (WIP)", "info_type": "Model", "discipline": "Structural"})

    # --- digital twin: building systems + linked/sensored/DPP assets ---
    hv = mk(c, pid, "building_system", {"name": "HVAC-1", "system_type": "HVAC", "bms_integration": "BACnet"})
    mk(c, pid, "building_system", {"name": "FP-1", "system_type": "Fire Protection", "bms_integration": "None"})
    mk(c, pid, "asset_register", {"name": "AHU-3 (twin)", "tag": "MECH-100", "manufacturer": "Trane", "model": "T3",
                                  "expected_life_years": 20, "replacement_cost": 80000, "system": hv,
                                  "sensor_id": "BMS:AHU3:SAT", "sensor_type": "Temperature",
                                  "gs1_id": "https://id.gs1.org/01/09506000134352", "epd_reference": "EPD-9",
                                  "manufacturer_url": "https://trane.com/ahu3"})

    # --- procurement compliance: a compliant + a non-compliant vendor ---
    pa = mk(c, pid, "prequalification", {"company": "ACME Concrete", "trade": "Concrete", "status": "Approved", "expires": "2027-06-01"})
    act(c, pid, "prequalification", pa, "approve")
    ca = mk(c, pid, "coi", {"vendor": "ACME Concrete", "coverage_type": "General Liability", "carrier": "Travelers", "expires": "2027-06-01"})
    act(c, pid, "coi", ca, "approve")
    cb = mk(c, pid, "coi", {"vendor": "Bedrock Co", "coverage_type": "General Liability", "carrier": "Hartford", "expires": "2026-06-20"})
    act(c, pid, "coi", cb, "approve")
    mk(c, pid, "prequalification", {"company": "Bedrock Co", "trade": "Earthwork", "status": "Submitted"})

    # --- concept space program (adjacency graph -> massing) ---
    mk(c, pid, "space_program", {"name": "Typical unit", "space_type": "Residential Unit", "target_area_sf": 850,
                                 "quantity": 40, "adjacent_to": ["Circulation / Core", "Amenity"]})
    mk(c, pid, "space_program", {"name": "Lobby", "space_type": "Lobby", "target_area_sf": 1200, "quantity": 1,
                                 "adjacent_to": ["Retail", "Circulation / Core"]})
    mk(c, pid, "space_program", {"name": "Core", "space_type": "Circulation / Core", "target_area_sf": 400, "quantity": 5})
    mk(c, pid, "space_program", {"name": "Fitness", "space_type": "Amenity", "target_area_sf": 1500, "quantity": 1,
                                 "adjacent_to": ["Residential Unit"]})

    # baselines so the variance endpoints return 200 (not 409)
    c.post(f"/projects/{pid}/budget/baseline")
    c.post(f"/projects/{pid}/schedule/baseline")

    # --- crawl the GET endpoints the web app calls ---
    snap["GET /projects"] = [{"id": pid, "name": "Demo Tower", "model_kind": None}]
    grab(c, "/modules"); grab(c, "/portfolio/executive"); grab(c, "/portfolio/construction"); grab(c, "/proforma/portfolio")
    grab(c, "/benchmarks/costs?min_samples=3"); grab(c, "/benchmarks/response-rates")
    grab(c, "/ids/templates"); grab(c, "/energy/benchmark-status"); grab(c, "/reports")
    grab(c, "/estimate/conceptual/catalog"); grab(c, "/mcp/tools")
    P = f"/projects/{pid}"
    singles = [f"{P}/dashboard", f"{P}/members", f"{P}/budget/gmp", f"{P}/budget/cashflow", f"{P}/budget/variance",
               f"{P}/cost/summary", f"{P}/px-summary", f"{P}/schedule/cpm", f"{P}/schedule/earned-value", f"{P}/schedule/lookahead?weeks=3",
               f"{P}/schedule/milestones", f"{P}/schedule/variance", f"{P}/schedule/4d", f"{P}/safety/metrics", f"{P}/bids/leveling",
               f"{P}/compliance/expiring?within_days=30", f"{P}/enum-options", f"{P}/notifications", f"{P}/my-work", f"{P}/module-pins",
               f"{P}/5d/heatmap?by=progress", f"{P}/5d/heatmap?by=cost", f"{P}/qto/by-floor", f"{P}/estimate/from-model",
               f"{P}/dev-budget", f"{P}/dev-budget/cost-lines", f"{P}/dev-budget/gmp-reconciliation", f"{P}/loan-draws",
               f"{P}/construction-draws", f"{P}/subcontractor-billing", f"{P}/proforma/model-metrics", f"{P}/property",
               f"{P}/sources-uses", f"{P}/specialty", f"{P}/ai/risk-summary", f"{P}/lean/ppc", f"{P}/properties/meta",
               f"{P}/specs/submittal-log", f"{P}/feasibility",
               # lifecycle panels (v0.3.49+): design gates, turnover, diligence, operations, asset mgmt, ESG
               f"{P}/lifecycle", f"{P}/turnover/readiness", f"{P}/turnover/status",
               f"{P}/diligence/readiness", f"{P}/cmms/kpis", f"{P}/energy/actual", f"{P}/fca/index", "/fca/portfolio",
               f"{P}/reserves/study?horizon_years=25&inflation_pct=3",   # the Asset Mgmt tab's default query
               f"{P}/cam/reconciliation", f"{P}/esg",
               # risk & cost / compliance panels
               f"{P}/prequal/scores", f"{P}/prequal/coi-expiry?soon_days=30", f"{P}/payapp/lien-exposure",
               f"{P}/carbon", f"{P}/procurement/three-way-match", f"{P}/due-feed?days=7",
               # dashboard extras + hold-phase finance tabs (found via [demo] console misses)
               f"{P}/views/alerts", f"{P}/health", f"{P}/pricing/reconcile",
               f"{P}/appraisal", f"{P}/rent-roll", f"{P}/leases/management", f"{P}/cap-table",
               # standards + AI + twin + program panels (v0.3.61+)
               f"{P}/cde/status", f"{P}/info-requirements/register", f"{P}/bim-kpi/scorecard",
               f"{P}/handover/acceptance", f"{P}/standards/check?standard=iso19650",
               f"{P}/standards/check?standard=cobie", f"{P}/standards/check?standard=ids",
               f"{P}/standards/check?standard=uniclass", f"{P}/twin/readiness",
               f"{P}/procurement/compliance-feed", f"{P}/program/summary",
               f"{P}/pull-plan/board", f"{P}/pull-plan/metrics", "/benchmarks/pull-planning?min_committed=1"]
    for s in singles:
        grab(c, s)
    for kind in ("gantt", "lob"):
        grab(c, f"{P}/schedule/{kind}.svg", as_text=True)
    # override /me -> read-only viewer, landing in the GC persona (hides write controls)
    snap[f"GET {P}/me"] = {"user": "demo", "role": "viewer", "party_role": "GC", "rbac": True}
    # per-module: list + board + views + per-record detail/related
    keys = [m["key"] for m in snap["GET /modules"]]   # type: ignore[union-attr]
    for key in keys:
        recs = grab(c, f"{P}/modules/{key}") or []
        grab(c, f"{P}/modules/{key}/board"); grab(c, f"{P}/modules/{key}/views")
        for r in recs:                                # type: ignore[union-attr]
            rid = r.get("id")
            if rid:
                grab(c, f"{P}/modules/{key}/{rid}"); grab(c, f"{P}/modules/{key}/{rid}/related")

    # the proforma overview is solved server-side (POST); capture the default deal so the demo's
    # Finance > Proforma tab populates (mirrors DEFAULT in apps/web/src/proforma/proforma.ts).
    default_assumptions = {
        "timing": {"construction_months": 18, "leaseup_months": 12, "hold_years": 5, "start_date": "2026-01-01"},
        "cost_lines": [
            {"category": "land", "name": "Land", "amount": 4_000_000, "curve": "upfront", "start_month": 0, "end_month": 0},
            {"category": "hard", "name": "Construction", "amount": 20_000_000, "curve": "scurve", "start_month": 1, "end_month": 17},
            {"category": "soft", "name": "Soft costs", "amount": 3_000_000, "curve": "linear", "start_month": 0, "end_month": 17},
            {"category": "contingency", "name": "Contingency", "amount": 1_000_000, "curve": "scurve", "start_month": 1, "end_month": 17},
        ],
        "debt": {"ltc": 0.65, "rate": 0.085, "points": 0.01, "funding": "equity_first", "max_ltv": None, "min_dscr": None},
        "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
        "operations": {"potential_rent_annual": 3_600_000, "other_income_annual": 120_000, "opex_annual": 1_300_000,
                       "reserves_annual": 0, "stabilized_occ": 0.94, "credit_loss_pct": 0.02},
        "exit": {"exit_cap": 0.055, "selling_cost_pct": 0.02},
        "waterfall": {"pref_rate": 0.08, "style": "american", "clawback": False,
                      "tiers": [{"hurdle": 0.12, "lp": 0.8, "gp": 0.2}, {"hurdle": 0.18, "lp": 0.7, "gp": 0.3}, {"hurdle": None, "lp": 0.6, "gp": 0.4}]},
        "discount_rate": 0.1,
    }
    sr = c.post("/proforma/solve", json=default_assumptions)
    if sr.status_code == 200:
        snap["POST /proforma/solve"] = sr.json()
    else:
        print(f"  skip POST /proforma/solve -> {sr.status_code}")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
    json.dump(snap, fh, separators=(",", ":"), ensure_ascii=False)
print(f"\nwrote {len(snap)} fixtures -> demoData.json ({os.path.getsize(OUT)/1024:.0f} KB); project={pid}")
