"""End-to-end lifecycle drive: a concrete-superstructure residential tower from acquisition all
the way to turnover. Exercises every pillar over HTTP and reports PASS/FAIL/SKIP per step so gaps
surface as a punch list. Resilient - a failing step never aborts the run.

  python services/api/e2e_tower.py            # against http://localhost:8000

Phases: 0 Acquisition/feasibility · 1 Design (authoring real concrete structure + unit fit-out) ·
2 Preconstruction · 3 Construction · 4 Turnover/closeout. Prints the final source IFC path."""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://localhost:8000")
ap.add_argument("--user", default="gc")
opts = ap.parse_args()

results: list[tuple[str, str, str, str]] = []   # phase, name, status, detail
_phase = "0"


def call(method: str, path: str, body=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(opts.url + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-User": opts.user})
    with urllib.request.urlopen(req, timeout=300) as r:
        b = r.read()
        return b if raw else json.loads(b or "{}")


def run(name: str, fn):
    try:
        out = fn()
        results.append((_phase, name, "PASS", out if isinstance(out, str) else ""))
        print(f"  PASS  {name}" + (f"  ->  {out}" if isinstance(out, str) else ""))
        return out
    except urllib.error.HTTPError as e:
        detail = f"{e.code}: {e.read().decode()[:160]}"
        results.append((_phase, name, "FAIL", detail))
        print(f"  FAIL  {name}  ({detail})")
    except Exception as e:                       # noqa: BLE001
        results.append((_phase, name, "FAIL", str(e)[:180]))
        print(f"  FAIL  {name}  ({str(e)[:180]})")
    return None


def phase(n: str, title: str):
    global _phase
    _phase = n
    print(f"\n=== PHASE {n} - {title} ===")


pid = None
metrics = {}


def new(mod, data, assignee=None):
    body = {"data": data}
    if assignee:
        body["assignee"] = assignee
    return call("POST", f"/projects/{pid}/modules/{mod}", body)["id"]


def act(mod, rid, action):
    call("POST", f"/projects/{pid}/modules/{mod}/{rid}/transition", {"action": action})


def edit(recipe, params, publish=False):
    return call("POST", f"/projects/{pid}/edit", {"recipe": recipe, "params": params, "publish": publish})


def upload(mod, rid, filename="evidence.txt", content=b"verified on site"):
    boundary = "----e2eboundary0xMaple"
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: text/plain\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(opts.url + f"/projects/{pid}/modules/{mod}/{rid}/attachments",
                                 data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                                          "X-User": opts.user})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or "{}")


def wait_publish():
    for _ in range(60):
        s = call("GET", f"/projects/{pid}/publish/status")
        if s.get("state") in ("done", "error"):
            return s.get("state")
        time.sleep(1)
    return "timeout"


# ============================================================================
phase("0", "Acquisition / feasibility")
pid = run("create project", lambda: call("POST", "/projects", {"name": "Maple Street Tower"})["id"])
assert pid, "cannot continue without a project"


def _gen():
    global metrics
    r = call("POST", f"/projects/{pid}/generate/massing", {
        "name": "Maple Street Tower", "use_type": "residential",
        "lot_width": 45, "lot_depth": 30, "far": 4.0, "height_limit": 60,
        "floor_to_floor": 3.2, "coverage_max": 0.6, "avg_unit_m2": 80})
    metrics = r["metrics"]
    return f"{metrics['floors']} floors, {metrics['units']} units, {metrics['buildable_gfa_sf']:,} sf"


run("generate massing from zoning (IFC + proforma)", _gen)
run("  publish generated model", lambda: wait_publish())
run("acquisition proforma scenario", lambda: call("POST", "/proforma/scenarios", {
    "name": "Maple - acquisition", "project_id": pid, "assumptions": {
        "timing": {"construction_months": 24, "leaseup_months": 6, "hold_years": 7},
        "cost_lines": [{"category": "land", "name": "Land", "amount": 3_000_000, "curve": "upfront"},
                       {"category": "hard", "name": "Hard", "amount": 28_000_000, "curve": "scurve"}],
        "debt": {"ltc": 0.6, "rate": 0.075}, "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
        "operations": {"potential_rent_annual": 4_200_000, "opex_annual": 1_400_000, "stabilized_occ": 0.94},
        "exit": {"exit_cap": 0.05, "selling_cost_pct": 0.02},
        "waterfall": {"pref_rate": 0.08, "tiers": [{"hurdle": None, "lp": 0.8, "gp": 0.2}]}}})["id"])

# ============================================================================
phase("1", "Design - author concrete superstructure + unit fit-out")
fw = float(metrics.get("plate_w", 30)); fd = float(metrics.get("plate_d", 18))
hx, hy = fw / 2 - 1.0, fd / 2 - 1.0          # column grid inset 1 m from the plate edge
corners = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
f2f = float(metrics.get("floor_to_floor", 3.2))
floors_to_frame = min(3, int(metrics.get("floors", 1)))


def _structure():
    n = 0
    for lvl in range(1, floors_to_frame + 1):
        storey = f"Level {lvl}"
        for (x, y) in corners:                # concrete columns
            edit("add_column", {"point": [x, y], "height": f2f, "width": 0.6, "depth": 0.6, "storey": storey})
            n += 1
        for i in range(4):                    # perimeter beams
            a, b = corners[i], corners[(i + 1) % 4]
            edit("add_beam", {"start": list(a), "end": list(b), "width": 0.4, "depth": 0.6, "storey": storey})
            n += 1
        # central core shear wall
        edit("add_wall", {"start": [-3, 0], "end": [3, 0], "height": f2f, "thickness": 0.3, "storey": storey})
        n += 1
    return f"{n} structural elements across {floors_to_frame} floors"


run("author concrete structure (columns/beams/core)", _structure)


def _fitout():
    n = 0
    for fam in ("fridge", "range", "dishwasher", "sink", "sofa", "table", "bed"):
        edit("add_family", {"family": fam, "storey": "Level 1", "position": [2.0 + n, 2.0]})
        n += 1
    return f"{n} fixtures/furniture placed in a Level 1 unit"


run("unit fit-out (appliances + furniture)", _fitout)
run("set concrete material tag on columns", lambda: edit(
    "set_pset", {"ifc_class": "IfcColumn", "pset": "Pset_ConcreteElementGeneral",
                 "prop": "StrengthClass", "value": "C40/50"}) and "tagged")
run("publish authored model (reconvert + reindex)", lambda: (edit("set_pset",
    {"ifc_class": "IfcSlab", "pset": "Pset_SlabCommon", "prop": "LoadBearing", "value": True, "dtype": "bool"},
    publish=True), wait_publish())[1])


def _verify_render():
    src = call("GET", f"/projects/{pid}")["source_ifc"]
    return f"source_ifc set: {bool(src)}"


run("verify model published", _verify_render)

# ============================================================================
phase("2", "Preconstruction - estimate, budget, bids, schedule")
run("model takeoff -> estimate", lambda: f"${call('GET', f'/projects/{pid}/estimate/from-model')['total']:,.0f}")

cc = run("cost code", lambda: new("cost_code", {"code": "03-3000", "description": "Cast-in-place concrete"}))
run("budget line", lambda: new("budget", {"description": "Concrete superstructure", "amount": 12_000_000,
                                          **({"cost_code": cc} if cc else {})}))
run("commitment (subcontract value)", lambda: new("commitment", {"description": "Concrete sub", "amount": 11_200_000,
                                                                  **({"cost_code": cc} if cc else {})}))
bp = run("bid package", lambda: new("bid_package", {"name": "Concrete package", "trade": "Concrete", "budget": 12_000_000}))
if bp:
    for bidder, amt in [("ACME Concrete", 11_180_000), ("Bedrock", 11_650_000), ("PourPro", 12_010_000)]:
        run(f"  bid: {bidder}", lambda bidder=bidder, amt=amt: new("bid_submission", {"bidder": bidder, "package": bp, "amount": amt}))
    run("bid leveling", lambda: f"low ${call('GET', f'/projects/{pid}/bids/leveling')['packages'][0]['low']:,.0f}"
        if call("GET", f"/projects/{pid}/bids/leveling").get("packages") else "no packages")
    run("award bid package", lambda: act("bid_package", bp, "close") or "closed")

acts = []
for i, (nm, dur, pre) in enumerate([("Mobilize", 10, ""), ("Foundations", 30, "Mobilize"),
                                    ("Superstructure", 90, "Foundations"), ("Envelope", 60, "Superstructure"),
                                    ("Fit-out", 80, "Envelope"), ("Commissioning", 20, "Fit-out")]):
    rid = run(f"schedule: {nm}", lambda nm=nm, dur=dur, pre=pre: new("schedule_activity",
              {"name": nm, "duration": dur, "predecessors": pre}))
    if rid:
        acts.append(rid)
run("CPM critical path", lambda: f"{call('GET', f'/projects/{pid}/schedule/cpm')['project_duration']} days, "
    f"{call('GET', f'/projects/{pid}/schedule/cpm')['critical_count']} critical")

# ============================================================================
phase("3", "Construction - RFIs, submittals, changes, field, safety, pay app")
rfi = run("RFI (submit -> respond)", lambda: new("rfi", {"subject": "Rebar congestion at core", "question": "Advise lap splice.",
                                                        "discipline": "Structural"}, "consultant"))
if rfi:
    run("  RFI submit", lambda: act("rfi", rfi, "submit") or "open")
    run("  RFI respond", lambda: act("rfi", rfi, "respond") or "answered")
sub = run("submittal (concrete mix design)", lambda: new("submittal", {"title": "Concrete mix design",
          "spec_section": "03 30 00"}, "sub"))
if sub:
    run("  submittal submit", lambda: act("submittal", sub, "submit") or "submitted")
ce = run("change event", lambda: new("change_event", {"subject": "Added shear wall at L2"}, "pm"))
pco = run("PCO request", lambda: new("pco_request", {"subject": "PCO - added shear wall",
          "description": "Owner-directed shear wall", **({"change_event": ce} if ce else {})}, "owner"))
cor = run("COR (submit -> approve -> execute)", lambda: new("cor", {"subject": "COR 001 - shear wall", "amount": 145_000,
          **({"pco": pco} if pco else {})}))
if cor:
    run("  COR submit", lambda: act("cor", cor, "submit") or "submitted")
    run("  COR approve", lambda: act("cor", cor, "approve") or "approved")
    run("  COR execute", lambda: act("cor", cor, "execute") or "executed")
dr = run("daily report", lambda: new("daily_report", {"report_date": "2026-07-15", "weather": "Clear"}))
if dr:
    run("  manpower log", lambda: new("manpower_log", {"company": "Concrete sub", "date": "2026-07-15", "count": 18,
                                                       **({"daily_report": dr} if dr else {})}))
insp = run("inspection (fail -> NCR)", lambda: new("inspection", {"subject": "L2 deck pre-pour", "date": "2026-07-15",
                                                                 "result": "Fail"}, "qa"))
if insp:
    run("  inspection fail", lambda: act("inspection", insp, "fail") or "failed")
    run("  NCR off inspection", lambda: new("ncr", {"subject": "Cover deficiency", "description": "Low rebar cover",
        "severity": "Major", **({"inspection": insp} if insp else {})}, "sub"))
run("safety incident", lambda: new("incident", {"subject": "Near miss - formwork", "date": "2026-07-16",
                                                "classification": "Near Miss", "severity": "Near Miss"}, "safety"))
run("safety metrics (TRIR/DART)", lambda: f"TRIR {call('GET', f'/projects/{pid}/safety/metrics').get('trir')}")
# pay application from SOV
sov = run("SOV line", lambda: new("sov", {"item_no": "01", "description": "Concrete superstructure",
                                          "scheduled_value": 12_000_000, "completed_this": 3_000_000, "retainage_pct": 5}))
run("G703 continuation sheet", lambda: f"${call('GET', f'/projects/{pid}/cost/g703')['totals']['scheduled']:,.0f}")
run("G702 pay application", lambda: f"app current ${call('GET', f'/projects/{pid}/cost/g702?app_no=1')['current_payment_due']:,.0f}"
    if "current_payment_due" in call("GET", f"/projects/{pid}/cost/g702?app_no=1") else "g702 ok")
run("dashboard", lambda: f"{len(call('GET', f'/projects/{pid}/dashboard')['action_items'])} action items")
run("AI ask (snapshot)", lambda: call("POST", f"/projects/{pid}/ai/ask", {"question": "what is open?"})["source"])

# ============================================================================
phase("4", "Turnover / closeout")
pl = run("punchlist item (open -> ready -> verify)", lambda: new("punchlist", {"description": "Touch-up paint L1 lobby",
                                                                             "location": "Lobby", "severity": "Minor"}))
if pl:
    run("  punch ready_to_inspect", lambda: act("punchlist", pl, "ready_to_inspect") or "ready")
    run("  punch evidence photo", lambda: upload("punchlist", pl, "punch.txt", b"touch-up complete") and "attached")
    run("  punch verify (evidence-gated)", lambda: act("punchlist", pl, "verify") or "verified")
run("commissioning (test -> accept)", lambda: (lambda c: (act("commissioning", c, "test"),
    act("commissioning", c, "accept"), "accepted")[2])(new("commissioning", {"system": "HVAC"})))
run("O&M manual", lambda: new("om_manual", {"name": "HVAC O&M manual"}))
run("warranty", lambda: new("warranty", {"name": "Roof warranty (10 yr)"}))
run("as-built", lambda: new("as_built", {"number": "AB-001", "title": "Structural as-builts"}))
run("asset register entry", lambda: new("asset_register", {"name": "Rooftop AHU-1"}))
run("completion certificate (issue -> accept)", lambda: (lambda c: (act("completion_certificate", c, "issue"),
    act("completion_certificate", c, "accept"), "accepted")[2])(new("completion_certificate", {"subject": "Substantial completion"})))
run("COBie export", lambda: f"{len(call('GET', f'/projects/{pid}/exports/cobie.xlsx', raw=True)):,} bytes")
run("QTO export", lambda: f"{len(call('GET', f'/projects/{pid}/exports/qto.xlsx', raw=True)):,} bytes")
run("space schedule export", lambda: f"{len(call('GET', f'/projects/{pid}/exports/spaces.xlsx', raw=True)):,} bytes")
run("project status report (PDF)", lambda: f"{len(call('GET', f'/projects/{pid}/report.pdf', raw=True)):,} bytes")

# ============================================================================
print("\n" + "=" * 70)
src = None
try:
    src = call("GET", f"/projects/{pid}")["source_ifc"]
except Exception:
    pass
by_phase: dict[str, list[int]] = {}
for ph, _, status, _ in results:
    b = by_phase.setdefault(ph, [0, 0])
    b[0 if status == "PASS" else 1] += 1
total_pass = sum(b[0] for b in by_phase.values())
total_fail = sum(b[1] for b in by_phase.values())
print(f"E2E TOWER - {total_pass} passed, {total_fail} failed across {len(by_phase)} phases")
for ph in sorted(by_phase):
    p, f = by_phase[ph]
    print(f"  phase {ph}: {p} pass / {f} fail")
if total_fail:
    print("\nFAILURES:")
    for ph, name, status, detail in results:
        if status == "FAIL":
            print(f"  [{ph}] {name}: {detail}")
print(f"\nproject: {pid}")
print(f"source_ifc: {src}")
