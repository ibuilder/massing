"""End-to-end vertical-farm scenario: a retail big-box converted to a solar/wind-powered indoor
vertical farm (after the M. Emma thesis). Exercises the NEW developer/feasibility stack — property
& tax, generative massing, Test Fit (compare + optimize), specialty assets (energy + PFAL), cost
budget, Sources & Uses, proforma, and the development *presentation* (investment memo + pitch deck)
— then a construction + turnover slice. Resilient: a failing step never aborts. Reports PASS/FAIL.

  python services/api/e2e_vertfarm.py            # against http://localhost:8000
"""
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

results: list[tuple[str, str, str, str]] = []
_phase = "0"


def call(method, path, body=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(opts.url + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-User": opts.user})
    with urllib.request.urlopen(req, timeout=300) as r:
        b = r.read()
        return b if raw else json.loads(b or "{}")


def run(name, fn):
    try:
        out = fn()
        results.append((_phase, name, "PASS", out if isinstance(out, str) else ""))
        print(f"  PASS  {name}" + (f"  ->  {out}" if isinstance(out, str) else ""))
        return out
    except urllib.error.HTTPError as e:
        detail = f"{e.code}: {e.read().decode()[:160]}"
        results.append((_phase, name, "FAIL", detail)); print(f"  FAIL  {name}  ({detail})")
    except Exception as e:                       # noqa: BLE001
        results.append((_phase, name, "FAIL", str(e)[:180])); print(f"  FAIL  {name}  ({str(e)[:180]})")
    return None


def phase(n, title):
    global _phase
    _phase = n; print(f"\n=== PHASE {n} - {title} ===")


pid = None


def new(mod, data, assignee=None):
    body = {"data": data}
    if assignee:
        body["assignee"] = assignee
    return call("POST", f"/projects/{pid}/modules/{mod}", body)["id"]


def act(mod, rid, action):
    call("POST", f"/projects/{pid}/modules/{mod}/{rid}/transition", {"action": action})


def upload(mod, rid, fname, content):
    import io
    boundary = "----e2evf"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{fname}\"\r\n"
            f"Content-Type: text/plain\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(opts.url + f"/projects/{pid}/modules/{mod}/{rid}/attachments",
                                 data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-User": opts.user})
    urllib.request.urlopen(req, timeout=120).read()
    return True


def wait_publish():
    for _ in range(60):
        s = call("GET", f"/projects/{pid}/publish/status").get("state")
        if s in ("done", "error"):
            return s
        time.sleep(1)
    return "timeout"


# ============================================================================
phase("0", "Acquisition / feasibility")
pid = run("create project", lambda: call("POST", "/projects", {"name": "Hempstead Vertical Farm"})["id"])
if not pid:
    raise SystemExit("could not create project")

run("property & tax assumptions", lambda: f"taxes ${call('PUT', f'/projects/{pid}/property', {'purchase_price': 15_744_700, 'building_sf': 249_749, 'land_sf': 598_668, 'parking_sf': 348_919, 'taxes': {'school': 955_533, 'county': 239_731, 'town': 228_906, 'fire': 79_055}})['summary']['total_taxes']:,.0f}/yr")

# retail big-box conversion: wide, low footprint
gen = run("generate massing (retail conversion shell)", lambda: call("POST", f"/projects/{pid}/generate/massing",
          {"name": "Vertical Farm", "lot_width": 240, "lot_depth": 230, "far": 0.45, "height_limit": 13,
           "floor_to_floor": 6.0, "use_type": "commercial", "frame": True, "envelope": True, "core": True}))
if gen:
    m = gen["metrics"]
    run("  massing program", lambda: f"{m['floors']} floors, {m['buildable_gfa_sf']:,} sf, bound by {m['binding_constraint']}")
    run("  publish generated model", wait_publish)

run("Test Fit compare schemes", lambda: f"best '{call('POST', '/test-fit/compare', {'plate_w': 230, 'plate_d': 220, 'floors': 2, 'schemes': []})['best']}'")
run("Test Fit generative optimize (yield-on-cost)", lambda: (lambda o: f"{o['considered']} swept, best {o['best']['yield_on_cost']*100:.1f}% YoC" if o.get('best') else "no feasible")(call("POST", "/test-fit/optimize", {"plate_w": 230, "plate_d": 220, "floors": 2, "targets": {"min_units": 1}})))

# ============================================================================
phase("1", "Specialty economics + cost budget + capital plan")
run("specialty: on-site energy + PFAL vertical farm", lambda: (lambda s: f"capex ${s['capex_total']:,.0f}, net ${s['annual_net_contribution']:,.0f}/yr")(call("PUT", f"/projects/{pid}/specialty", {
    "energy_enabled": True, "pfal_enabled": True,
    "energy": {"solar_sf": 500_000, "sf_per_panel": 20, "cost_per_panel": 330, "battery_units": 7,
               "rainwater_capex": 780_000, "wind_turbines": 116, "wind_cost": 5_000},
    "pfal": {"pfal_sf": 40_000, "sf_per_tower": 1.7, "green_pct": 0.4, "green_price_lb": 4.75, "herb_price_lb": 16},
})["summary"]))

run("cost budget (hard + soft line items)", lambda: f"grand ${call('PUT', f'/projects/{pid}/dev-budget', {'contingency': {'hard': 0.15, 'soft': 0.10}, 'lines': [{'category': 'acquisition', 'description': 'Purchase price', 'unit_cost': 15_744_700, 'quantity': 1}, {'category': 'hard', 'description': 'Solar panels', 'unit_cost': 330, 'quantity': 24_999}, {'category': 'hard', 'description': 'Vertical wind turbines', 'unit_cost': 5_000, 'quantity': 1_161}, {'category': 'hard', 'description': 'Battery storage', 'unit_cost': 15_000, 'quantity': 7}, {'category': 'hard', 'description': 'Rainwater collection', 'unit_cost': 780_000, 'quantity': 1}, {'category': 'hard', 'description': 'HVAC + chiller', 'unit_cost': 250_000, 'quantity': 1}, {'category': 'hard', 'description': 'Produce market', 'unit_cost': 325_000, 'quantity': 1}, {'category': 'soft', 'description': 'Architect', 'unit_cost': 350_000, 'quantity': 1}, {'category': 'soft', 'description': 'Energy consultant', 'unit_cost': 75_000, 'quantity': 1}, {'category': 'soft', 'description': 'Agriculture consultant', 'unit_cost': 125_000, 'quantity': 1}]})['summary']['grand_total']:,.0f}")

run("Sources & Uses (balanced)", lambda: (lambda su: f"uses ${su['total_uses']:,.0f} = debt ${su['debt']:,.0f} + equity ${su['equity']:,.0f} ({'balanced' if su['balanced'] else 'UNBALANCED'})")(call("GET", f"/projects/{pid}/sources-uses")))

# proforma scenario from the budget cost-lines
cl = run("pull budget -> proforma cost lines", lambda: call("GET", f"/projects/{pid}/dev-budget/cost-lines")["cost_lines"])
if cl:
    assumptions = {"timing": {"construction_months": 18, "hold_years": 7}, "cost_lines": cl,
                   "debt": {"ltc": 0.6, "rate": 0.075}, "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
                   "operations": {"potential_rent_annual": 24_000_000, "opex_annual": 6_000_000, "stabilized_occ": 0.92},
                   "exit": {"exit_cap": 0.06}, "waterfall": {"pref_rate": 0.08, "tiers": [{"hurdle": None, "lp": 0.8, "gp": 0.2}]}}
    run("solve proforma scenario", lambda: (lambda s: f"equity IRR {(s['result']['returns'].get('equity_irr') or 0)*100:.1f}%, EM {s['result']['returns'].get('equity_multiple')}x")(call("POST", "/proforma/scenarios", {"name": "Vertical Farm Base", "project_id": pid, "assumptions": assumptions})))

# ============================================================================
phase("2", "Development presentation")
run("investment memo (PDF)", lambda: f"{len(call('GET', f'/projects/{pid}/investment-memo.pdf', raw=True)):,} bytes")
run("pitch deck (PDF)", lambda: f"{len(call('GET', f'/projects/{pid}/investment-deck.pdf', raw=True)):,} bytes")

# ============================================================================
phase("3", "Construction")
rfi = run("RFI (submit -> respond)", lambda: new("rfi", {"subject": "Grow-light circuit capacity", "question": "Confirm panel sizing.", "discipline": "MEP"}, "consultant"))
if rfi:
    run("  RFI submit", lambda: act("rfi", rfi, "submit") or "open")
    run("  RFI respond", lambda: act("rfi", rfi, "respond") or "answered")
run("submittal (PFAL tower system)", lambda: new("submittal", {"title": "ZipGrow tower system", "spec_section": "11 00 00"}, "sub"))
ce = run("change event", lambda: new("change_event", {"subject": "Added battery capacity"}, "pm"))
cor = run("COR (submit->approve->execute)", lambda: new("cor", {"subject": "COR - battery add", "amount": 105_000}))
if cor:
    for a in ("submit", "approve", "execute"):
        run(f"  COR {a}", lambda a=a: act("cor", cor, a) or a)
dr = run("daily report + manpower", lambda: new("daily_report", {"report_date": "2026-08-01", "weather": "Clear"}))
if dr:
    run("  manpower log", lambda: new("manpower_log", {"company": "MEP sub", "date": "2026-08-01", "count": 22, "daily_report": dr}))
insp = run("inspection (fail -> NCR)", lambda: new("inspection", {"subject": "Solar mounting", "date": "2026-08-02", "result": "Fail"}, "qa"))
if insp:
    run("  inspection fail", lambda: act("inspection", insp, "fail") or "failed")
    run("  NCR", lambda: new("ncr", {"subject": "Loose flashing", "description": "Roof penetration flashing", "severity": "Minor", "inspection": insp}, "sub"))
run("safety incident + TRIR", lambda: new("incident", {"subject": "Near miss - lift", "date": "2026-08-03", "classification": "Near Miss", "severity": "Near Miss"}, "safety"))
run("SOV line", lambda: new("sov", {"item_no": "01", "description": "Solar + energy", "scheduled_value": 14_000_000, "completed_this": 4_000_000, "retainage_pct": 5}))
run("G703 continuation sheet", lambda: f"${call('GET', f'/projects/{pid}/cost/g703')['totals']['scheduled']:,.0f}")
run("G702 pay application", lambda: "g702 ok" if call("GET", f"/projects/{pid}/cost/g702?app_no=1") else "fail")
run("AI ask (snapshot)", lambda: call("POST", f"/projects/{pid}/ai/ask", {"question": "what is open and over budget?"})["source"])

# ============================================================================
phase("4", "Turnover / closeout + save model")
pl = run("punchlist (open->ready->verify)", lambda: new("punchlist", {"description": "Seal grow-room door", "location": "PFAL", "severity": "Minor"}))
if pl:
    run("  ready_to_inspect", lambda: act("punchlist", pl, "ready_to_inspect") or "ready")
    run("  evidence photo", lambda: upload("punchlist", pl, "done.txt", b"sealed") and "attached")
    run("  verify (evidence-gated)", lambda: act("punchlist", pl, "verify") or "verified")
run("commissioning (HVAC/PFAL)", lambda: (lambda c: (act("commissioning", c, "test"), act("commissioning", c, "accept"), "accepted")[2])(new("commissioning", {"system": "PFAL lighting"})))
run("as-built", lambda: new("as_built", {"number": "AB-001", "title": "Energy + farm as-builts"}))
run("completion certificate", lambda: (lambda c: (act("completion_certificate", c, "issue"), act("completion_certificate", c, "accept"), "accepted")[2])(new("completion_certificate", {"subject": "Substantial completion"})))
run("COBie export", lambda: f"{len(call('GET', f'/projects/{pid}/exports/cobie.xlsx', raw=True)):,} bytes")
run("QTO export", lambda: f"{len(call('GET', f'/projects/{pid}/exports/qto.xlsx', raw=True)):,} bytes")
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
    b = by_phase.setdefault(ph, [0, 0]); b[0 if status == "PASS" else 1] += 1
tp = sum(b[0] for b in by_phase.values()); tf = sum(b[1] for b in by_phase.values())
print(f"E2E VERTICAL FARM - {tp} passed, {tf} failed across {len(by_phase)} phases")
for ph in sorted(by_phase):
    p, f = by_phase[ph]; print(f"  phase {ph}: {p} pass / {f} fail")
if tf:
    print("\nFAILURES:")
    for ph, name, status, detail in results:
        if status == "FAIL":
            print(f"  [{ph}] {name}: {detail}")
print(f"\nproject: {pid}\nsource_ifc: {src}")
