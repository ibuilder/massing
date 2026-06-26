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

    # change-management + QA + bidding + field + safety chains
    rfis = []
    for subj, disc, ci in [("Beam clash at grid C4", "Structural", "Yes"), ("Door schedule mismatch L3", "Architectural", "Possible"), ("VAV duct routing conflict", "MEP", "None")]:
        rfis.append(mk(c, pid, "rfi", {"subject": subj, "question": "Please advise.", "discipline": disc, "cost_impact": ci}, "consultant"))
    act(c, pid, "rfi", rfis[0], "submit"); act(c, pid, "rfi", rfis[0], "respond"); act(c, pid, "rfi", rfis[1], "submit")
    ce = mk(c, pid, "change_event", {"subject": "Added steel at C4", "rom": 85000, "source_rfi": rfis[0], "trades": ["Steel", "Concrete"]}, "pm")
    pco = mk(c, pid, "pco_request", {"subject": "PCO - added steel", "description": "Added WF beam + connections at C4", "rough_cost": 92500, "source_rfi": rfis[0], "change_event": ce}, "owner")
    mk(c, pid, "cor", {"subject": "COR 001 - steel", "amount": 92500, "justification": "Owner-directed", "pco": pco})
    insp = mk(c, pid, "inspection", {"subject": "Level 2 deck pour", "location": "Grid C-E", "result": "Fail", "date": "2026-06-14"}, "qa")
    mk(c, pid, "ncr", {"subject": "Honeycomb at column", "description": "Voids on north face", "severity": "Major", "inspection": insp}, "sub")
    mk(c, pid, "submittal", {"subject": "Rebar shop drawings", "spec_section": "03 20 00", "discipline": "Structural"}, "sub")
    bp = mk(c, pid, "bid_package", {"name": "Concrete package", "trade": "Concrete", "budget": 5_000_000})
    for bidder, amt in [("ACME Concrete", 4_780_000), ("Bedrock Co", 4_950_000), ("Pour Bros", 5_120_000)]:
        mk(c, pid, "bid_submission", {"bidder": bidder, "package": bp, "amount": amt})
    for d, w, crews in [("2026-06-13", "Clear", [12, 8]), ("2026-06-14", "Rain", [6, 4])]:
        dr = mk(c, pid, "daily_report", {"report_date": d, "weather": w})
        for cnt in crews:
            mk(c, pid, "manpower_log", {"company": "Self-perform", "date": d, "count": cnt, "daily_report": dr})
    mk(c, pid, "incident", {"subject": "Near miss - dropped tool", "description": "No injury", "date": "2026-06-13", "classification": "Near Miss", "severity": "Near Miss"}, "safety")
    mk(c, pid, "punchlist", {"description": "Touch-up paint L2 corridor", "location": "L2", "trade": "Finishes"})

    # baselines so the variance endpoints return 200 (not 409)
    c.post(f"/projects/{pid}/budget/baseline")
    c.post(f"/projects/{pid}/schedule/baseline")

    # --- crawl the GET endpoints the web app calls ---
    snap["GET /projects"] = [{"id": pid, "name": "Demo Tower", "model_kind": None}]
    grab(c, "/modules"); grab(c, "/portfolio/executive"); grab(c, "/portfolio/construction"); grab(c, "/proforma/portfolio")
    P = f"/projects/{pid}"
    singles = [f"{P}/dashboard", f"{P}/members", f"{P}/budget/gmp", f"{P}/budget/cashflow", f"{P}/budget/variance",
               f"{P}/cost/summary", f"{P}/px-summary", f"{P}/schedule/cpm", f"{P}/schedule/earned-value", f"{P}/schedule/lookahead?weeks=3",
               f"{P}/schedule/milestones", f"{P}/schedule/variance", f"{P}/schedule/4d", f"{P}/safety/metrics", f"{P}/bids/leveling",
               f"{P}/compliance/expiring?within_days=30", f"{P}/enum-options", f"{P}/notifications", f"{P}/my-work", f"{P}/module-pins",
               f"{P}/5d/heatmap?by=progress", f"{P}/5d/heatmap?by=cost", f"{P}/qto/by-floor", f"{P}/estimate/from-model",
               f"{P}/dev-budget", f"{P}/dev-budget/cost-lines", f"{P}/dev-budget/gmp-reconciliation", f"{P}/loan-draws",
               f"{P}/construction-draws", f"{P}/subcontractor-billing", f"{P}/proforma/model-metrics", f"{P}/property",
               f"{P}/sources-uses", f"{P}/specialty", f"{P}/ai/risk-summary", f"{P}/lean/ppc", f"{P}/properties/meta"]
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
