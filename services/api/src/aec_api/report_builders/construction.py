"""Report builders — construction domain (extracted from reports.py, A2)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..reports_core import Report
from ..reports_core import money as _money
from ._common import _records


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


def _submittal_register(db: Session, pid: str, name: str) -> Report:
    from .. import submittals
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
    from .. import quality
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
    from .. import rfi
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
    from .. import dailylog
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
    from .. import safety
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
    from .. import closeout
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
    from .. import projecthealth
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
    from .. import changeorders
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
    from .. import actions
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


def _spec_submittal_log(db: Session, pid: str, name: str) -> Report:
    from .. import specs
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


def _cep(db: Session, pid: str, name: str) -> Report:
    """Construction Execution Plan (CEP) — the GC counterpart to the BEP: a produced governance document
    that states HOW the project is built, assembled live from the construction modules and summary
    engines. Ten sections (org / scope / schedule / procurement / cost control / safety / quality /
    submittal-RFI procedures / permits / closeout) so the plan reflects the real project record, not a
    stale Word template. Every data pull is guarded — a missing engine or empty module degrades to a
    placeholder row instead of 500ing the report."""

    def _safe(fn, default=None):
        try:
            return fn()
        except Exception:       # noqa: BLE001 — a missing engine/module must not sink the whole document
            return default

    bids = _records(db, "bid_package", pid)
    subs = _records(db, "subcontract", pid)
    preq = _records(db, "prequalification", pid)
    acts = _records(db, "schedule_activity", pid)
    perms = _records(db, "permit", pid)
    saf = _safe(lambda: __import__("aec_api.safety", fromlist=["safety_summary"]).safety_summary(db, pid), {})
    qual = _safe(lambda: __import__("aec_api.quality", fromlist=["quality_summary"]).quality_summary(db, pid), {})
    clo = _safe(lambda: __import__("aec_api.closeout", fromlist=["closeout_summary"]).closeout_summary(db, pid), {})
    co = _safe(lambda: __import__("aec_api.changeorders", fromlist=["co_log"]).co_log(db, pid), {})
    subm = _records(db, "submittal", pid)
    rfi = _records(db, "rfi", pid)

    r = Report("Construction Execution Plan (CEP)", name)
    r.kpi("Bid packages", len(bids))
    r.kpi("Subcontracts", len(subs))
    r.kpi("Schedule activities", len(acts))
    r.kpi("Permits", len(perms))
    r.kpi("Submittals", len(subm))
    r.kpi("Open RFIs", sum(1 for x in rfi if x.get("workflow_state") not in ("closed", "answered", "void")))
    if saf.get("incidents"):
        r.kpi("Safety incidents", saf["incidents"].get("incident_count", 0))
    if clo.get("punchlist"):
        r.kpi("Punch items", clo["punchlist"].get("punch_count", 0))

    # 1. Plan sections & governing procedure — the document's table of contents, each with the rule it runs by
    r.table("Plan sections & governing procedure", ["#", "Section", "Governing procedure"], [
        ["1", "Project organization & authorities", "Roles below; GC PM holds single-point authority for the appointment."],
        ["2", "Scope & work breakdown", "By bid package / trade; each package maps to a CSI/cost code."],
        ["3", "Master schedule & milestones", "CPM-driven; Last-Planner make-ready weekly; milestones tracked below."],
        ["4", "Procurement & subcontracting", "Prequalify → bid → award → execute subcontract; insurance/bond verified."],
        ["5", "Cost management & change control", "GMP budget; change events → COR → CO; owner approval before proceeding."],
        ["6", "Safety plan (OSHA)", "Site-specific safety plan; daily toolbox talks; incident + observation logging."],
        ["7", "Quality plan", "Inspection & test plan; NCR loop; first-pass-yield tracked."],
        ["8", "Submittal & RFI procedures", "Spec-driven submittal register; RFI within contract response time."],
        ["9", "Permits & regulatory", "AHJ permits tracked to issuance; inspections scheduled to the work."],
        ["10", "Closeout & turnover", "Punchlist → commissioning → warranties/O&M → record turnover (G704)."],
    ])

    # 2. Roles, responsibilities & authorities — standard construction appointment + any project directory
    roles = [["Owner / Appointing Party", "Funds the work; approves changes and the schedule of values; accepts the project."],
             ["General Contractor — Project Manager", "Owns this CEP; single point of authority; cost, schedule and contract lead."],
             ["Superintendent", "Runs the field: daily coordination, safety enforcement, look-ahead scheduling."],
             ["Project Engineer", "Submittals, RFIs, drawing control and the document record."],
             ["Safety Manager", "Site-specific safety plan, toolbox talks, incident investigation, OSHA logs."],
             ["Quality (QC) Manager", "Inspection & test plan, NCR disposition, first-pass-yield."],
             ["MEP/BIM Coordinator", "Trade coordination and clash resolution against the federated model."]]
    seen = set()
    for s in subs:                       # append awarded subcontractors as appointed trade parties
        d = s.get("data") or {}
        t = d.get("trade") or d.get("scope") or ""
        who = d.get("vendor_company") or d.get("vendor") or ""
        key = (t, who)
        if who and key not in seen:
            seen.add(key)
            roles.append([f"{t} subcontractor — {who}", "Appointed trade party; executes its scope to the contract & schedule."])
    r.table("Roles, responsibilities & authorities", ["Role", "Responsibility"], roles)

    # 3. Scope & work breakdown — by bid package
    r.table("Scope & work breakdown (by package)", ["Package", "Trade", "Discipline", "Budget", "State"],
            [[(x.get("data") or {}).get("name", ""), (x.get("data") or {}).get("trade", ""),
              (x.get("data") or {}).get("discipline", ""), _money((x.get("data") or {}).get("budget")),
              x.get("workflow_state", "")] for x in bids] or [["(no bid packages logged)"] + [""] * 4])

    # 4. Master schedule & key milestones — milestone activities (zero-duration or type=milestone), else first activities
    def _is_ms(d):
        return str(d.get("activity_type", "")).lower() == "milestone" or str(d.get("duration") or "") in ("0", "0.0")
    ms = [x for x in acts if _is_ms(x.get("data") or {})] or acts
    r.table("Master schedule & key milestones", ["Activity", "Trade", "Start", "Finish", "% complete", "State"],
            [[(x.get("data") or {}).get("name", ""), (x.get("data") or {}).get("trade", ""),
              (x.get("data") or {}).get("start", ""), (x.get("data") or {}).get("finish", ""),
              (x.get("data") or {}).get("percent", ""), x.get("workflow_state", "")]
             for x in ms[:40]] or [["(no schedule activities logged)"] + [""] * 5])

    # 5. Procurement & subcontracting — prequal + executed subs
    r.table("Prequalified & appointed subcontractors", ["Company", "Trade", "Value", "Insurance exp", "Bond", "State"],
            [[(x.get("data") or {}).get("vendor_company") or (x.get("data") or {}).get("vendor", ""),
              (x.get("data") or {}).get("trade", ""), _money((x.get("data") or {}).get("value")),
              (x.get("data") or {}).get("insurance_exp", ""),
              "yes" if (x.get("data") or {}).get("bond_required") else "—", x.get("workflow_state", "")]
             for x in subs] or [[f"({len(preq)} prequalified; no subcontracts executed yet)"] + [""] * 5])

    # 6. Cost management & change control
    r.table("Cost management & change control", ["Metric", "Value"],
            [["Change orders", co.get("co_count", 0)], ["Total CO value", _money(co.get("total_value", 0))],
             ["Pending", _money(co.get("pending_value", 0))], ["Approved", _money(co.get("approved_value", 0))],
             ["Executed", _money(co.get("executed_value", 0))],
             ["Change-event ROM exposure", _money(co.get("change_event_rom_exposure", 0))]])

    # 7. Safety plan
    inc = saf.get("incidents", {})
    r.table("Safety plan (OSHA)", ["Metric", "Value"],
            [["Incidents", inc.get("incident_count", 0)], ["Recordables", inc.get("recordable_count", 0)],
             ["TRIR", inc.get("trir") if inc.get("trir") is not None else "—"],
             ["DART", inc.get("dart_rate") if inc.get("dart_rate") is not None else "—"],
             ["Observations", saf.get("observations", {}).get("observation_count", 0)],
             ["Toolbox talks", saf.get("toolbox_talks", {}).get("talk_count", 0)]])

    # 8. Quality plan
    ins = qual.get("inspections", {})
    r.table("Quality plan", ["Metric", "Value"],
            [["Inspections", ins.get("total", 0)],
             ["Pass rate", f"{ins.get('pass_rate')}%" if ins.get("pass_rate") is not None else "—"],
             ["First-pass yield", f"{ins.get('first_pass_yield')}%" if ins.get("first_pass_yield") is not None else "—"],
             ["Open NCRs", qual.get("ncrs", {}).get("open_count", 0)],
             ["Open deficiencies", qual.get("deficiencies", {}).get("open_count", 0)]])

    # 9. Permits & regulatory
    r.table("Permits & regulatory", ["Permit", "Type", "Authority", "Number", "Status", "Expires"],
            [[(x.get("data") or {}).get("name", ""), (x.get("data") or {}).get("permit_type", ""),
              (x.get("data") or {}).get("authority", ""), (x.get("data") or {}).get("number", ""),
              (x.get("data") or {}).get("status", ""), (x.get("data") or {}).get("expires", "")]
             for x in perms] or [["(no permits logged)"] + [""] * 5])

    # 10. Closeout & turnover
    pu = clo.get("punchlist", {})
    r.table("Closeout & turnover", ["Metric", "Value"],
            [["Punch items", pu.get("punch_count", 0)],
             ["Punch complete", f"{pu.get('complete_pct')}%" if pu.get("complete_pct") is not None else "—"],
             ["Commissioning pass rate",
              f"{clo.get('commissioning', {}).get('pass_rate')}%" if clo.get("commissioning", {}).get("pass_rate") is not None else "—"],
             ["Warranties expiring (90d)", clo.get("warranties", {}).get("expiring_soon", 0)],
             ["O&M accepted",
              f"{clo.get('om_manuals', {}).get('accepted_pct')}%" if clo.get("om_manuals", {}).get("accepted_pct") is not None else "—"]])
    return r
