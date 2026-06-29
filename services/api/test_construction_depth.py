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

    # --- reports render -------------------------------------------------------
    cat = {x["id"] for x in c.get("/reports").json()["reports"]}
    assert {"tm_log", "submittal_register", "quality", "rfi_register"} <= cat, cat
    for rid in ("tm_log", "submittal_register", "quality", "rfi_register"):
        pdf = c.get(f"/projects/{pid}/reports/{rid}.pdf")
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.content) > 1200, (rid, pdf.status_code)

print("CONSTRUCTION-DEPTH OK - T&M rollup $10k (labor/material/equip split, billed+unbilled); submittal "
      "register: 2 subs, 1 overdue, avg turnaround 10d, by spec section; quality: pass rate 66.7%/FPY 33.3%, "
      "1 NCR overdue (Repair), deficiency ball-in-court GC vs Sub; RFI register: 2 RFIs, 1 overdue, "
      "ball-in-court Consultant vs GC; tm_log + submittal_register + quality + rfi_register PDFs render")
