"""Populate a project with realistic demo records across the relation chains, so the
dashboard charts, kanban board, search, rollups and notifications look alive.

Talks to a running API over HTTP (stdlib only — no extra deps):

    python services/api/seed_demo.py                       # http://localhost:8000, new "Demo Tower"
    python services/api/seed_demo.py --url http://localhost:8000 --project <id>
    python services/api/seed_demo.py --user gc             # act as this user (X-User)

Idempotent enough for demos: re-running just adds more records.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

ARGS = argparse.ArgumentParser()
ARGS.add_argument("--url", default="http://localhost:8000")
ARGS.add_argument("--project", default=None, help="existing project id (else creates one)")
ARGS.add_argument("--user", default="gc", help="X-User to act as")
ARGS.add_argument("--force", action="store_true",
                  help="seed even if the target already has projects (guard against seeding prod)")
opts = ARGS.parse_args()


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(opts.url + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-User": opts.user})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or "{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} -> {e.code}: {e.read().decode()[:200]}")


def new(module: str, data: dict, assignee: str | None = None) -> str:
    body: dict = {"data": data}
    if assignee:
        body["assignee"] = assignee
    return call("POST", f"/projects/{pid}/modules/{module}", body)["id"]


def act(module: str, rid: str, action: str) -> None:
    call("POST", f"/projects/{pid}/modules/{module}/{rid}/transition", {"action": action})


# --- guard: never seed demo data into a populated (possibly production) instance ------------
if not opts.project and not opts.force:
    existing = call("GET", "/projects")
    if existing:
        raise SystemExit(
            f"refusing to seed: the target at {opts.url} already has {len(existing)} project(s). "
            "This guard prevents demo data landing in a real deployment. Pass --project <id> to seed "
            "into a specific project, or --force if you really mean it.")

# --- pick / create the project ----------------------------------------------
if opts.project:
    pid = opts.project
else:
    pid = call("POST", "/projects", {"name": "Demo Tower"})["id"]
print(f"seeding project {pid} as '{opts.user}'")

# --- cost chain: cost codes (by CSI division) + budget lines + buyout + actuals --------------
codes = {                                   # code: (description, division, budget)
    "03-3000": ("Cast-in-place concrete", "03", 4_800_000),
    "05-1200": ("Structural steel", "05", 6_200_000),
    "23-0000": ("HVAC", "23", 3_100_000),
    "26-0000": ("Electrical", "26", 2_700_000),
    "09-2900": ("Gypsum board", "09", 1_350_000),
    "01-5000": ("General requirements", "01", 1_200_000),   # Div 01 → General Requirements bucket
}
cost_codes = {}
for code, (desc, div, budget) in codes.items():
    cc = new("cost_code", {"code": code, "description": desc, "division": div})
    cost_codes[code] = cc
    new("budget", {"cost_code": cc, "description": desc, "revised": budget})          # GMP allocation
    if div != "01":
        com = new("commitment", {"description": f"{desc} sub", "cost_code": cc, "amount": round(budget * 0.92)})
        act("commitment", com, "execute")                                            # → committed (buyout)
        new("direct_cost", {"description": "Equipment & misc", "cost_code": cc, "amount": round(budget * 0.03)})

# GMP prime contract with markups (so the Budget destination computes a full GMP)
pc = new("prime_contract", {"name": "GMP — Demo Tower", "type": "GMP", "value": 41_000_000,
                            "overhead_pct": 5, "fee_pct": 4, "contingency_pct": 3})
for i, amt in enumerate([2_400_000, 3_100_000, 2_750_000], 1):
    new("owner_invoice", {"number": f"INV-{i:03d}", "amount": amt, "prime_contract": pc, "period": f"2026-0{i+2}-01"})

# --- project team (staffing → General Conditions) ----------------------------
for role, cat, rate in [("Project Executive", "General Conditions", 8_000),
                        ("Senior Project Manager", "General Conditions", 22_000),
                        ("Superintendent", "General Conditions", 20_000),
                        ("Safety Manager", "General Requirements", 15_000)]:
    new("staffing", {"role": role, "category": cat, "count": 1, "rate": rate,
                     "rate_period": "Month", "start": "2026-01-01", "finish": "2026-12-31"})

# --- cost-loaded schedule (drives Schedule / 4D scrub / cash-flow / CPM) ------
acts = [("Sitework", "Sitework", "2026-01-05", "2026-02-15", 1_500_000),
        ("Foundations", "Concrete", "2026-02-10", "2026-04-10", 4_800_000),
        ("Superstructure", "Steel", "2026-04-01", "2026-08-15", 6_200_000),
        ("MEP rough-in", "MEP", "2026-06-01", "2026-10-30", 5_800_000),
        ("Interiors & finishes", "Finishes", "2026-09-01", "2027-01-31", 4_200_000)]
prev = None
for i, (name, trade, s, f, bud) in enumerate(acts):
    pct = [100, 80, 40, 10, 0][i]
    a = new("schedule_activity", {"name": name, "trade": trade, "start": s, "finish": f,
                                  "budget": bud, "percent": pct, "wbs": f"01.{i+1:02d}",
                                  "predecessors": prev or ""})
    prev = f"01.{i+1:02d}"

# seed the owner Schedule of Values from the GMP budget + bill the first period
call("POST", f"/projects/{pid}/cost/sov/from-budget?replace=true")

# --- change-management chain -------------------------------------------------
rfis = []
for subj, disc, ci in [("Beam clash at grid C4", "Structural", "Yes"),
                       ("Door schedule mismatch L3", "Architectural", "Possible"),
                       ("VAV duct routing conflict", "MEP", "None")]:
    # the first RFI gets answered below; the workflow gates 'respond' on the `answer` field.
    extra = {"answer": "Revise the connection per SK-12; added steel covered by COR 001."} if not rfis else {}
    r = new("rfi", {"subject": subj, "question": "Please advise.", "discipline": disc, "cost_impact": ci, **extra}, "consultant")
    rfis.append(r)
act("rfi", rfis[0], "submit"); act("rfi", rfis[0], "respond")     # -> answered
act("rfi", rfis[1], "submit")                                     # -> open

ce = new("change_event", {"subject": "Added steel at C4", "rom": 85_000, "source_rfi": rfis[0],
                          "trades": ["Steel", "Concrete"]}, "pm")
pco = new("pco_request", {"subject": "PCO — added steel", "description": "Added WF beam + connections at C4",
                          "rough_cost": 92_500, "source_rfi": rfis[0], "change_event": ce}, "owner")
new("cor", {"subject": "COR 001 — steel", "amount": 92_500, "justification": "Owner-directed", "pco": pco})
new("proposal", {"subject": "Proposal — steel add", "amount": 92_500, "pco": pco})

# --- specifications -> submittals (spec register + spec-driven submittal log) -
# One fully-covered section and one with a gap, so the submittal log shows coverage + a miss.
new("spec_section", {"section_number": "03 30 00", "title": "Cast-in-Place Concrete",
                     "division": "03 - Concrete", "responsible": "Concrete sub",
                     "submittals_required": ("Product Data: for each mix design.\n"
                                             "Shop Drawings: placing drawings for reinforcement.\n"
                                             "Samples: each exposed architectural finish.")})
new("spec_section", {"section_number": "07 92 00", "title": "Joint Sealants",
                     "division": "07 - Thermal & Moisture", "responsible": "Caulking sub",
                     "submittals_required": ("Product Data: sealant.\n"
                                             "Samples: color.\n"
                                             "Warranty: 5-year.")})
# Log the three 03 30 00 submittals (-> that section is 100% covered); 07 92 00 stays open (a gap).
for title, styp in [("Concrete mix designs", "Product Data"),
                    ("Rebar placing drawings", "Shop Drawing"),
                    ("Architectural finish samples", "Sample")]:
    new("submittal", {"title": title, "type": styp, "spec_section": "03 30 00"}, "sub")

# --- zoning & site -> feasibility / zoning-envelope study --------------------
new("zoning", {"site": "Demo Tower parcel", "jurisdiction": "DT-3 Downtown", "use_type": "Mixed-Use",
               "site_area_sf": 20_000, "far": 6.0, "height_limit_ft": 240, "floor_to_floor_ft": 12,
               "lot_coverage_pct": 80, "efficiency_pct": 85, "avg_unit_sf": 850,
               "parking_ratio": 0.5, "open_space_pct": 10})

# --- QA / inspection chain ---------------------------------------------------
insp = new("inspection", {"subject": "Level 2 deck pour", "location": "Grid C-E", "result": "Fail", "date": "2026-06-14", "inspection_type": "In-Progress"}, "qa")
new("ncr", {"subject": "Honeycomb at column", "description": "Voids on north face", "severity": "Major", "disposition": "Rework", "inspection": insp}, "sub")
new("deficiency", {"description": "Cold joint", "location": "Grid D3", "severity": "Minor", "inspection": insp})

# --- bidding chain -----------------------------------------------------------
bp = new("bid_package", {"name": "Concrete package", "trade": "Concrete", "budget": 5_000_000})
for bidder, amt in [("ACME Concrete", 4_780_000), ("Bedrock Co", 4_950_000), ("Pour Bros", 5_120_000)]:
    new("bid_submission", {"bidder": bidder, "package": bp, "amount": amt})

# --- field / daily -----------------------------------------------------------
for d, weather, crews in [("2026-06-13", "Clear", [12, 8]), ("2026-06-14", "Rain", [6, 4])]:
    dr = new("daily_report", {"report_date": d, "weather": weather})
    for c in crews:
        new("manpower_log", {"company": "Self-perform", "date": d, "count": c, "daily_report": dr})

# --- safety ------------------------------------------------------------------
new("incident", {"subject": "Near miss — dropped tool", "description": "No injury",
                 "date": "2026-06-13", "classification": "Near Miss", "severity": "Near Miss"}, "safety")

print("seed complete — open the Construction workspace to see populated dashboard / board / search")
