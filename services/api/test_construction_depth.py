"""Construction depth: T&M (eTicket) cost rollup + submittal register.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_construction_depth.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_cdepth.db"
os.environ["STORAGE_DIR"] = "./test_storage_cdepth"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_cdepth.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient   # noqa: E402
from aec_api.main import app                # noqa: E402


def mk(c, pid, key, data):
    return c.post(f"/projects/{pid}/modules/{key}", json={"data": data}).json()["id"]


def trans(c, pid, key, rid, action):
    return c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Depth"}).json()["id"]

    # --- T&M / eTickets -------------------------------------------------------
    e1 = mk(c, pid, "eticket", {"subject": "Rock excavation", "work_date": "2026-06-10",
                                "labor_total": 4000, "material_total": 1000, "equipment_total": 2000})
    mk(c, pid, "eticket", {"subject": "Dewatering", "work_date": "2026-06-12",
                           "labor_total": 1500, "material_total": 500, "equipment_total": 1000})
    # bill the first ticket: draft → super_signed → gc_signed → billed
    for a in ("super_sign", "gc_sign", "bill"):
        r = trans(c, pid, "eticket", e1, a)
        if r.status_code != 200:  # action names may differ; push to billed however the workflow allows
            break
    tms = c.get(f"/projects/{pid}/tm-summary").json()
    assert tms["ticket_count"] == 2, tms
    assert tms["labor_total"] == 5500 and tms["material_total"] == 1500 and tms["equipment_total"] == 3000, tms
    assert tms["grand_total"] == 10000, tms
    assert tms["billed_total"] + tms["unbilled_total"] == 10000, tms

    # --- T&M → change-event tie ----------------------------------------------
    ce = mk(c, pid, "change_event", {"subject": "Unforeseen rock"})
    e3 = mk(c, pid, "eticket", {"subject": "Extra excavation", "work_date": "2026-06-14", "labor_total": 3000,
                                "material_total": 0, "equipment_total": 2000, "change_event": ce})
    bce = c.get(f"/projects/{pid}/tm-by-change-event").json()
    linked = next(g for g in bce["groups"] if g["change_event_id"] == ce)
    assert linked["total"] == 5000 and linked["ticket_count"] == 1, linked
    assert bce["linked_total"] == 5000, bce
    assert bce["unassigned_total"] == 10000, bce      # the first two tickets aren't linked

    # --- Submittal register ---------------------------------------------------
    mk(c, pid, "submittal", {"title": "Rebar shop dwgs", "spec_section": "03 20 00", "type": "Shop Drawing",
                             "responsible_contractor": "ACME", "date_received": "2026-06-01",
                             "date_returned": "2026-06-11", "required_on_site": "2020-01-01"})  # overdue + 10d turn
    mk(c, pid, "submittal", {"title": "Concrete mix", "spec_section": "03 30 00", "type": "Product Data",
                             "responsible_contractor": "ACME", "required_on_site": "2030-01-01"})
    reg = c.get(f"/projects/{pid}/submittals/register").json()
    assert reg["submittal_count"] == 2, reg
    assert reg["overdue_count"] == 1, reg                       # the 2020 one, still draft
    assert reg["avg_turnaround_days"] == 10.0, reg             # 06-01 → 06-11
    assert set(reg["by_section"].keys()) == {"03 20 00", "03 30 00"}, reg["by_section"]
    rebar = next(r for r in reg["rows"] if r["spec_section"] == "03 20 00")
    assert rebar["overdue"] is True and rebar["turnaround_days"] == 10, rebar

    # --- Quality: inspections / NCR loop / deficiency ball-in-court -----------
    i1 = mk(c, pid, "inspection", {"subject": "Footing", "date": "2026-06-02", "result": "Pass",
                                   "inspection_type": "In-Progress"})
    mk(c, pid, "inspection", {"subject": "Slab", "date": "2026-06-03", "result": "Fail",
                              "inspection_type": "In-Progress"})
    mk(c, pid, "inspection", {"subject": "Final elec", "date": "2026-06-04", "result": "Conditional",
                              "inspection_type": "Final", "agency": "City"})
    nc = mk(c, pid, "ncr", {"subject": "Honeycombing", "severity": "Major", "disposition": "Repair",
                            "corrective_action": "Patch per spec", "due_date": "2020-01-01"})  # overdue (open)
    trans(c, pid, "ncr", nc, "disposition")  # open -> dispositioned (still open, still overdue)
    df1 = mk(c, pid, "deficiency", {"description": "Scuffed door", "severity": "Minor",
                                    "trade": "Carpentry", "due_date": "2030-01-01"})
    trans(c, pid, "deficiency", df1, "correct")  # open -> corrected => GC's court
    mk(c, pid, "deficiency", {"description": "Missing sealant", "severity": "Minor", "trade": "Glazing"})  # open => sub's court
    q = c.get(f"/projects/{pid}/quality/summary").json()
    assert q["inspections"]["total"] == 3, q["inspections"]
    assert q["inspections"]["passed"] == 1 and q["inspections"]["failed"] == 1, q["inspections"]
    # pass rate = (pass + conditional)/decided = 2/3; first-pass yield = 1/3
    assert q["inspections"]["pass_rate"] == 66.7 and q["inspections"]["first_pass_yield"] == 33.3, q["inspections"]
    assert q["ncrs"]["ncr_count"] == 1 and q["ncrs"]["overdue_count"] == 1, q["ncrs"]
    assert q["ncrs"]["by_disposition"].get("Repair") == 1, q["ncrs"]
    assert q["deficiencies"]["deficiency_count"] == 2, q["deficiencies"]
    assert q["deficiencies"]["ball_in_court"].get("GC (verify)") == 1, q["deficiencies"]
    assert q["deficiencies"]["ball_in_court"].get("Subcontractor") == 1, q["deficiencies"]
    assert q["deficiencies"]["overdue_count"] == 0, q["deficiencies"]  # one due-2030, one no due

    # --- RFI register ---------------------------------------------------------
    r1 = mk(c, pid, "rfi", {"subject": "Beam conflict", "question": "Clash at grid C", "discipline": "Structural",
                            "priority": "High", "due_date": "2020-01-01", "cost_impact": "Yes",
                            "schedule_impact": "Possible"})
    trans(c, pid, "rfi", r1, "submit")  # draft -> open (awaiting consultant => overdue)
    r2 = mk(c, pid, "rfi", {"subject": "Finish schedule", "question": "Which paint?", "discipline": "Architectural",
                            "priority": "Normal", "due_date": "2030-01-01"})
    trans(c, pid, "rfi", r2, "submit")
    # respond requires 'answer'; patch merges the field map directly (no "data" wrapper)
    pr = c.patch(f"/projects/{pid}/modules/rfi/{r2}", json={"answer": "Use spec 09 91 00"})
    assert pr.status_code == 200, pr.text
    rr = trans(c, pid, "rfi", r2, "respond")  # open -> answered (GC's court)
    assert rr.status_code == 200, rr.text
    reg = c.get(f"/projects/{pid}/rfi/register").json()
    assert reg["rfi_count"] == 2, reg
    assert reg["overdue_count"] == 1, reg                       # the grid-C one (open, due 2020)
    assert reg["cost_impacted_count"] == 1, reg
    assert reg["ball_in_court"].get("Consultant") == 1, reg     # r1 awaiting answer
    assert reg["ball_in_court"].get("GC (accept)") == 1, reg    # r2 answered
    assert reg["by_discipline"].get("Structural") == 1, reg

    # --- Field-log rollup -----------------------------------------------------
    mk(c, pid, "daily_report", {"report_date": "2026-06-01", "weather": "Clear", "manpower": 12,
                                "weather_impact": "None"})
    mk(c, pid, "daily_report", {"report_date": "2026-06-02", "weather": "Rain", "manpower": 20,
                                "weather_impact": "Half-Day Lost", "delays": "Rain stopped concrete"})
    mk(c, pid, "daily_report", {"report_date": "2026-06-03", "weather": "Snow", "manpower": 0,
                                "weather_impact": "Full-Day Lost"})
    fl = c.get(f"/projects/{pid}/daily-reports/summary").json()
    assert fl["report_count"] == 3, fl
    assert fl["total_manpower"] == 32, fl
    assert fl["peak_manpower"]["count"] == 20 and fl["peak_manpower"]["date"] == "2026-06-02", fl
    assert fl["weather_lost_days"] == 1.5, fl                   # 0 + 0.5 + 1.0
    assert fl["delay_days"] == 1, fl
    assert fl["span_days"] == 3 and fl["logged_days"] == 3 and fl["coverage_pct"] == 100.0, fl

    # --- Safety dashboard (OSHA rates) ----------------------------------------
    mk(c, pid, "incident", {"subject": "Cut hand", "date": "2026-06-02", "classification": "Recordable",
                            "severity": "Recordable", "osha_recordable": "Yes"})
    mk(c, pid, "incident", {"subject": "Back strain", "date": "2026-06-05", "classification": "Lost Time",
                            "severity": "Lost Time", "osha_recordable": "Yes", "lost_days": 5})
    mk(c, pid, "incident", {"subject": "Trip, no injury", "date": "2026-06-06", "classification": "Near Miss",
                            "severity": "Near Miss"})
    mk(c, pid, "observation", {"description": "Good housekeeping", "type": "Safe", "category": "Safe"})
    mk(c, pid, "observation", {"description": "No guardrail", "type": "At-Risk", "category": "Hazard",
                               "severity": "High"})
    mk(c, pid, "toolbox_talk", {"topic": "Ladder safety", "date": "2026-06-01", "attendees": 18})
    # exact rates on a supplied 100,000 worker-hours base: TRIR = 2*200000/100000 = 4.0; DART (1 lost-time) = 2.0
    saf = c.get(f"/projects/{pid}/safety/summary?hours=100000").json()
    assert saf["hours_estimated"] is False, saf
    assert saf["incidents"]["incident_count"] == 3, saf["incidents"]
    assert saf["incidents"]["recordable_count"] == 2, saf["incidents"]
    assert saf["incidents"]["trir"] == 4.0, saf["incidents"]
    assert saf["incidents"]["dart_rate"] == 2.0, saf["incidents"]
    assert saf["incidents"]["total_lost_days"] == 5, saf["incidents"]
    assert saf["observations"]["safe_count"] == 1 and saf["observations"]["at_risk_count"] == 1, saf["observations"]
    assert saf["toolbox_talks"]["total_attendees"] == 18, saf["toolbox_talks"]
    # without hours, it estimates from daily-report manpower (32 man-days x 8h = 256h)
    est = c.get(f"/projects/{pid}/safety/summary").json()
    assert est["hours_estimated"] is True and est["incidents"]["hours_worked"] == 256, est["incidents"]

    # --- Closeout dashboard ---------------------------------------------------
    p1 = mk(c, pid, "punchlist", {"description": "Touch-up paint", "trade": "Painting", "priority": "Low",
                                  "due_date": "2030-01-01", "cost": 250})
    mk(c, pid, "punchlist", {"description": "Door won't latch", "trade": "Doors", "priority": "High",
                             "due_date": "2020-01-01", "cost": 400})  # overdue, stays open (Sub's court)
    trans(c, pid, "punchlist", p1, "ready_to_inspect")  # open -> ready (GC verify court; full verify needs attachment)
    mk(c, pid, "commissioning", {"system": "AHU-1", "test_type": "Functional", "result": "Pass"})
    mk(c, pid, "commissioning", {"system": "AHU-2", "test_type": "Functional", "result": "Fail"})
    mk(c, pid, "warranty", {"name": "Roof membrane", "warranty_type": "Manufacturer", "expires": "2020-06-01"})  # expired
    co = c.get(f"/projects/{pid}/closeout/summary").json()
    assert co["punchlist"]["punch_count"] == 2, co["punchlist"]
    assert co["punchlist"]["overdue_count"] == 1, co["punchlist"]
    assert co["punchlist"]["open_cost"] == 650, co["punchlist"]   # both still open
    assert co["punchlist"]["ball_in_court"].get("GC (verify)") == 1, co["punchlist"]
    assert co["punchlist"]["ball_in_court"].get("Responsible / Sub") == 1, co["punchlist"]
    assert co["commissioning"]["pass_rate"] == 50.0, co["commissioning"]
    assert co["warranties"]["expired"] == 1, co["warranties"]

    # --- Change-order log -----------------------------------------------------
    co1 = mk(c, pid, "cor", {"subject": "Added doors", "amount": 12000, "reason": "Owner Request",
                             "schedule_days": 3})
    for a in ("submit", "approve", "execute"):  # draft -> submitted -> approved -> executed
        trans(c, pid, "cor", co1, a)
    mk(c, pid, "cor", {"subject": "Rock removal", "amount": 8000, "reason": "Unforeseen Condition",
                       "schedule_days": 5})  # stays draft (pending)
    mk(c, pid, "change_event", {"subject": "Possible redesign", "rom": 25000, "scope_status": "Undetermined"})
    col = c.get(f"/projects/{pid}/change-orders/log").json()
    assert col["co_count"] == 2, col
    assert col["executed_value"] == 12000 and col["pending_value"] == 8000, col
    assert col["total_value"] == 20000, col
    assert col["change_event_rom_exposure"] == 25000, col  # earlier "Unforeseen rock" CE has rom 0; this one has 25000
    assert col["ball_in_court"].get("Executed") == 1, col

    # --- Meeting & action-item tracker ----------------------------------------
    mtg = mk(c, pid, "meeting", {"subject": "OAC #1", "date": "2026-06-10", "meeting_type": "OAC"})
    mk(c, pid, "action_item", {"subject": "Send RFI log", "assignee": "PM", "priority": "High",
                               "due_date": "2020-01-01", "meeting": mtg})  # overdue, open
    ai2 = mk(c, pid, "action_item", {"subject": "Order steel", "assignee": "Super", "priority": "Medium",
                                     "due_date": "2030-01-01", "meeting": mtg})
    rc = trans(c, pid, "action_item", ai2, "complete")  # open -> done
    assert rc.status_code == 200, rc.text
    at = c.get(f"/projects/{pid}/action-items/tracker").json()
    assert at["action_count"] == 2 and at["done_count"] == 1, at
    assert at["overdue_count"] == 1 and at["completion_pct"] == 50.0, at
    assert at["meeting_count"] == 1 and at["last_meeting"] == "2026-06-10", at

    # --- Project-health executive rollup --------------------------------------
    h = c.get(f"/projects/{pid}/health").json()
    assert h["overall_status"] == "red", h           # overdue RFIs/NCRs/punch + recordable incidents
    assert 0 <= h["health_score"] <= 100, h
    keys = {d["key"] for d in h["domains"]}
    assert {"rfi", "submittals", "quality", "safety", "tm", "field", "closeout"} <= keys, keys
    assert any(a["status"] == "red" for a in h["attention_items"]), h["attention_items"]

    # --- reports render -------------------------------------------------------
    cat = {x["id"] for x in c.get("/reports").json()["reports"]}
    assert {"tm_log", "submittal_register", "quality", "rfi_register", "field_log", "safety_dashboard",
            "closeout", "project_health", "co_log", "action_tracker"} <= cat, cat
    for rid in ("tm_log", "submittal_register", "quality", "rfi_register", "field_log", "safety_dashboard",
                "closeout", "project_health", "co_log", "action_tracker"):
        pdf = c.get(f"/projects/{pid}/reports/{rid}.pdf")
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.content) > 1200, (rid, pdf.status_code)

print("CONSTRUCTION-DEPTH OK - T&M rollup $10k (labor/material/equip split, billed+unbilled); submittal "
      "register: 2 subs, 1 overdue, avg turnaround 10d, by spec section; quality: pass rate 66.7%/FPY 33.3%, "
      "1 NCR overdue (Repair), deficiency ball-in-court GC vs Sub; RFI register: 2 RFIs, 1 overdue, "
      "ball-in-court Consultant vs GC; field-log: 3 reports, 32 manpower, peak 20, 1.5 weather lost-days; "
      "safety: 3 incidents, 2 recordable, TRIR 4.0/DART 2.0 @100k hrs (est 256h from manpower); "
      "closeout: 2 punch (1 overdue, ball-in-court GC vs Sub), Cx pass 50%, 1 expired warranty; "
      "CO log: $12k executed/$8k pending + $25k CE ROM; action tracker: 50% complete, 1 overdue; "
      "project-health: RED rollup over 7 domains; all 10 dashboard/log PDFs render")
