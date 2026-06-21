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


# --- pick / create the project ----------------------------------------------
if opts.project:
    pid = opts.project
else:
    pid = call("POST", "/projects", {"name": "Demo Tower"})["id"]
print(f"seeding project {pid} as '{opts.user}'")

# --- cost chain --------------------------------------------------------------
codes = {
    "03-3000": ("Cast-in-place concrete", 4_800_000),
    "05-1200": ("Structural steel", 6_200_000),
    "09-2900": ("Gypsum board", 1_350_000),
}
cost_codes = {}
for code, (desc, budget) in codes.items():
    cc = new("cost_code", {"code": code, "description": desc})
    cost_codes[code] = cc
    new("commitment", {"description": f"{desc} sub", "cost_code": cc, "amount": round(budget * 0.92)})
    new("direct_cost", {"description": "Equipment & misc", "cost_code": cc, "amount": round(budget * 0.03)})

pc = new("prime_contract", {"name": "GMP — Demo Tower", "value": 41_000_000})
for i, amt in enumerate([2_400_000, 3_100_000, 2_750_000], 1):
    new("owner_invoice", {"number": f"INV-{i:03d}", "amount": amt, "prime_contract": pc})

# --- change-management chain -------------------------------------------------
rfis = []
for subj, disc, ci in [("Beam clash at grid C4", "Structural", "Yes"),
                       ("Door schedule mismatch L3", "Architectural", "Possible"),
                       ("VAV duct routing conflict", "MEP", "None")]:
    r = new("rfi", {"subject": subj, "question": "Please advise.", "discipline": disc, "cost_impact": ci}, "consultant")
    rfis.append(r)
act("rfi", rfis[0], "submit"); act("rfi", rfis[0], "respond")     # -> answered
act("rfi", rfis[1], "submit")                                     # -> open

ce = new("change_event", {"subject": "Added steel at C4", "rom": 85_000, "source_rfi": rfis[0],
                          "trades": ["Steel", "Concrete"]}, "pm")
pco = new("pco_request", {"subject": "PCO — added steel", "description": "Added WF beam + connections at C4",
                          "rough_cost": 92_500, "source_rfi": rfis[0], "change_event": ce}, "owner")
new("cor", {"subject": "COR 001 — steel", "amount": 92_500, "justification": "Owner-directed", "pco": pco})
new("proposal", {"subject": "Proposal — steel add", "amount": 92_500, "pco": pco})

# --- QA / inspection chain ---------------------------------------------------
insp = new("inspection", {"subject": "Level 2 deck pour", "location": "Grid C-E", "result": "Fail", "date": "2026-06-14"}, "qa")
new("ncr", {"subject": "Honeycomb at column", "description": "Voids on north face", "severity": "Major", "inspection": insp}, "sub")
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
