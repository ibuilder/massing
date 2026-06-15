"""Generate module.json files for the GC portal breadth (run once).
Each module is config-only — the shared engine gives it CRUD, workflow, comments,
CSV/PDF, pins and the activity timeline. Workflow-marked modules get real state machines;
registers/logs get a simple open→closed lifecycle."""
import json
from pathlib import Path

MODULES = Path(__file__).resolve().parent / "modules"

GC = ["GC"]
SIMPLE = {"initial": "open", "states": ["open", "closed"],
          "transitions": [{"from": "open", "to": "closed", "action": "close", "party": GC}]}


def wf(initial, transitions):
    states = sorted({initial} | {t["from"] for t in transitions} | {t["to"] for t in transitions})
    return {"initial": initial, "states": states, "transitions": transitions}


def F(name, label, type="text", required=False, options=None):
    f = {"name": name, "label": label, "type": type}
    if required:
        f["required"] = True
    if options:
        f["options"] = options
    return f


# (key, name, section, icon, prefix, title_field, pinnable, fields, workflow)
DEFS = [
    # --- Preconstruction ---
    ("prequalification", "Prequalification", "Preconstruction", "✓", "PQ", "company", False,
     [F("company", "Company", required=True), F("trade", "Trade"), F("emr", "EMR Rate", "number"),
      F("bonding_capacity", "Bonding Capacity", "number")],
     wf("submitted", [{"from": "submitted", "to": "approved", "action": "approve", "party": GC},
                      {"from": "submitted", "to": "rejected", "action": "reject", "party": GC}])),
    ("bid_package", "Bid Packages", "Preconstruction", "▦", "BP", "name", False,
     [F("name", "Package", required=True), F("trade", "Trade"), F("budget", "Budget", "number")], SIMPLE),
    ("bid_solicitation", "Bid Solicitations (ITB)", "Preconstruction", "✉", "ITB", "name", False,
     [F("name", "Solicitation", required=True), F("due_date", "Bids Due", "date")],
     wf("open", [{"from": "open", "to": "closed", "action": "close", "party": GC}])),
    ("bid_submission", "Bid Submissions", "Preconstruction", "$", "BID", "bidder", False,
     [F("bidder", "Bidder", required=True), F("package", "Package"), F("amount", "Amount", "number")], SIMPLE),
    ("estimate", "Estimates", "Preconstruction", "Σ", "EST", "name", False,
     [F("name", "Estimate", required=True), F("amount", "Amount", "number")], SIMPLE),
    ("value_engineering", "Value Engineering", "Preconstruction", "◆", "VE", "subject", False,
     [F("subject", "VE Item", required=True), F("savings", "Est. Savings", "number")],
     wf("proposed", [{"from": "proposed", "to": "accepted", "action": "accept", "party": GC},
                     {"from": "proposed", "to": "rejected", "action": "reject", "party": GC}])),

    # --- Engineering ---
    ("drawing", "Drawings & Specs", "Engineering", "▭", "DWG", "number", False,
     [F("number", "Sheet No.", required=True), F("title", "Title"), F("revision", "Rev"), F("discipline", "Discipline")], SIMPLE),
    ("meeting", "Meetings", "Engineering", "☷", "MTG", "subject", False,
     [F("subject", "Meeting", required=True), F("date", "Date", "date"), F("minutes", "Minutes", "textarea")],
     wf("agenda", [{"from": "agenda", "to": "minutes", "action": "publish_minutes", "party": GC}])),
    ("transmittal", "Transmittals", "Engineering", "➟", "TR", "subject", False,
     [F("subject", "Subject", required=True), F("to_company", "To"), F("contents", "Contents", "textarea")],
     wf("draft", [{"from": "draft", "to": "sent", "action": "send", "party": GC}])),
    ("issue", "Issues", "Engineering", "!", "ISS", "subject", True,
     [F("subject", "Issue", required=True), F("description", "Description", "textarea"), F("priority", "Priority", "select", options=["Low", "Medium", "High"])],
     wf("open", [{"from": "open", "to": "resolved", "action": "resolve", "party": GC},
                 {"from": "resolved", "to": "closed", "action": "close", "party": GC}])),
    ("action_item", "Action Items", "Engineering", "□", "AI", "subject", False,
     [F("subject", "Action", required=True), F("assignee", "Assignee"), F("due_date", "Due", "date")],
     wf("open", [{"from": "open", "to": "done", "action": "complete", "party": GC}])),
    ("design_review", "Design Reviews", "Engineering", "◉", "DR", "subject", False,
     [F("subject", "Review", required=True), F("comments", "Comments", "textarea")],
     wf("open", [{"from": "open", "to": "closed", "action": "close", "party": GC}])),
    ("permit", "Permitting", "Engineering", "▣", "PMT", "name", False,
     [F("name", "Permit", required=True), F("authority", "Authority"), F("expires", "Expires", "date")],
     wf("applied", [{"from": "applied", "to": "issued", "action": "issue", "party": GC}])),

    # --- Field ---
    ("schedule_activity", "Schedule", "Field", "▸", "ACT", "name", False,
     [F("name", "Activity", required=True), F("wbs", "WBS"), F("start", "Start", "date"), F("finish", "Finish", "date"),
      F("percent", "% Complete", "number"), F("location", "Location")], SIMPLE),
    ("punchlist", "Punchlist", "Field", "✗", "PL", "description", True,
     [F("description", "Item", required=True), F("location", "Location"), F("trade", "Trade")],
     wf("open", [{"from": "open", "to": "ready", "action": "ready_to_inspect", "party": ["Subcontractor", "GC"]},
                 {"from": "ready", "to": "verified", "action": "verify", "party": GC},
                 {"from": "ready", "to": "open", "action": "reject", "party": GC}])),
    ("checklist", "Checklists", "Field", "☑", "CL", "name", False,
     [F("name", "Checklist", required=True), F("location", "Location")], SIMPLE),
    ("photo", "Photo Library", "Field", "▣", "PH", "caption", True,
     [F("caption", "Caption", required=True), F("location", "Location"), F("date", "Date", "date")], SIMPLE),
    ("timesheet", "Timesheets", "Field", "⏱", "TS", "worker", False,
     [F("worker", "Worker", required=True), F("date", "Date", "date"), F("hours", "Hours", "number"), F("cost_code", "Cost Code")],
     wf("draft", [{"from": "draft", "to": "approved", "action": "approve", "party": GC}])),
    ("manpower_log", "Manpower Log", "Field", "☺", "MP", "company", False,
     [F("company", "Company", required=True), F("date", "Date", "date"), F("count", "Headcount", "number")], SIMPLE),
    ("delivery", "Deliveries", "Field", "▤", "DEL", "description", False,
     [F("description", "Material", required=True), F("date", "Date", "date"), F("supplier", "Supplier")], SIMPLE),
    ("equipment_log", "Equipment Log", "Field", "⚙", "EQ", "equipment", False,
     [F("equipment", "Equipment", required=True), F("date", "Date", "date"), F("hours", "Hours", "number")], SIMPLE),
    ("production_quantity", "Production Quantities", "Field", "Σ", "PQTY", "description", False,
     [F("description", "Item", required=True), F("quantity", "Qty Installed", "number"), F("unit", "Unit"), F("cost_code", "Cost Code")], SIMPLE),
    ("site_logistics", "Site Logistics", "Field", "▦", "LOG", "resource", False,
     [F("resource", "Resource", "select", required=True, options=["Crane", "Hoist", "Laydown", "Gate"]),
      F("date", "Date", "date"), F("company", "Booked By")], SIMPLE),

    # --- Quality ---
    ("inspection", "Inspections", "Quality", "✓", "INS", "subject", True,
     [F("subject", "Inspection", required=True), F("location", "Location"), F("result", "Result", "select", options=["Pass", "Fail", "Conditional"])],
     wf("scheduled", [{"from": "scheduled", "to": "passed", "action": "pass", "party": GC},
                      {"from": "scheduled", "to": "failed", "action": "fail", "party": GC}])),
    ("ncr", "Non-Conformance Reports", "Quality", "⚠", "NCR", "subject", True,
     [F("subject", "Non-conformance", required=True), F("description", "Description", "textarea"), F("disposition", "Disposition", "select", options=["Rework", "Repair", "Use-as-is", "Reject"])],
     wf("open", [{"from": "open", "to": "dispositioned", "action": "disposition", "party": GC},
                 {"from": "dispositioned", "to": "closed", "action": "close", "party": GC}])),
    ("deficiency", "Deficiencies", "Quality", "✗", "DEF", "description", True,
     [F("description", "Deficiency", required=True), F("location", "Location")], SIMPLE),
    ("test_record", "Test Records", "Quality", "▣", "TST", "name", False,
     [F("name", "Test", required=True), F("result", "Result"), F("date", "Date", "date")], SIMPLE),

    # --- Safety ---
    ("observation", "Safety Observations", "Safety", "◎", "OBS", "description", True,
     [F("description", "Observation", required=True), F("type", "Type", "select", options=["Safe", "At-Risk"]), F("location", "Location")], SIMPLE),
    ("pretask_plan", "Pre-Task Plans", "Safety", "▤", "PTP", "task", False,
     [F("task", "Task", required=True), F("hazards", "Hazards", "textarea"), F("signature", "Signature", "signature")], SIMPLE),
    ("jha", "Job Hazard Analyses", "Safety", "⚠", "JHA", "task", False,
     [F("task", "Task", required=True), F("hazards", "Hazards", "textarea"), F("controls", "Controls", "textarea")], SIMPLE),
    ("orientation", "Employee Orientations", "Safety", "☺", "ORI", "worker", False,
     [F("worker", "Worker", required=True), F("company", "Company"), F("date", "Date", "date"), F("signature", "Signature", "signature")], SIMPLE),
    ("incident", "Incidents", "Safety", "⚑", "INC", "subject", True,
     [F("subject", "Incident", required=True), F("description", "Description", "textarea"), F("severity", "Severity", "select", options=["Near Miss", "First Aid", "Recordable", "Lost Time"])],
     wf("open", [{"from": "open", "to": "investigating", "action": "investigate", "party": GC},
                 {"from": "investigating", "to": "closed", "action": "close", "party": GC}])),
    ("safety_violation", "Safety Violations", "Safety", "✗", "SV", "description", True,
     [F("description", "Violation", required=True), F("company", "Company")], SIMPLE),
    ("toolbox_talk", "Toolbox Talks", "Safety", "☷", "TBT", "topic", False,
     [F("topic", "Topic", required=True), F("date", "Date", "date"), F("attendees", "Attendees", "number")], SIMPLE),

    # --- Sustainability ---
    ("leed_credit", "LEED / Green Credits", "Sustainability", "❖", "LEED", "credit", False,
     [F("credit", "Credit", required=True), F("points", "Points", "number"), F("status", "Status")], SIMPLE),
    ("waste_diversion", "Waste Diversion", "Sustainability", "♺", "WD", "material", False,
     [F("material", "Material", required=True), F("tons", "Tons", "number"), F("diverted", "Diverted %", "number")], SIMPLE),
    ("environmental_monitoring", "Environmental Monitoring", "Sustainability", "◉", "ENV", "metric", False,
     [F("metric", "Metric", required=True), F("value", "Value", "number"), F("date", "Date", "date")], SIMPLE),

    # --- Contracts ---
    ("prime_contract", "Prime Contract", "Contracts", "▣", "PC", "name", False,
     [F("name", "Contract", required=True), F("type", "Type", "select", options=["GMP", "Cost Plus", "Lump Sum", "CMAR"]), F("value", "Value", "number")], SIMPLE),
    ("subcontract", "Subcontracts", "Contracts", "▤", "SC", "vendor", False,
     [F("vendor", "Subcontractor", required=True), F("trade", "Trade"), F("value", "Value", "number")],
     wf("draft", [{"from": "draft", "to": "executed", "action": "execute", "party": GC}])),
    ("lien_waiver", "Lien Waivers", "Contracts", "✓", "LW", "vendor", False,
     [F("vendor", "Vendor", required=True), F("amount", "Through Amount", "number"), F("signature", "Signature", "signature")], SIMPLE),
    ("coi", "Insurance Certificates", "Contracts", "▣", "COI", "vendor", False,
     [F("vendor", "Vendor", required=True), F("expires", "Expires", "date")], SIMPLE),

    # --- Cost (more) ---
    ("budget", "Budget & Forecast", "Cost", "Σ", "BUD", "cost_code", False,
     [F("cost_code", "Cost Code", required=True), F("description", "Description"), F("budget", "Budget", "number"), F("forecast", "Forecast", "number")], SIMPLE),
    ("change_event", "Change Events", "Cost", "✚", "CE", "subject", False,
     [F("subject", "Change Event", required=True), F("rom", "ROM Cost", "number")],
     wf("open", [{"from": "open", "to": "pending", "action": "submit", "party": GC},
                 {"from": "pending", "to": "closed", "action": "close", "party": GC}])),
    ("owner_invoice", "Owner Invoices", "Cost", "$", "OINV", "number", False,
     [F("number", "Invoice No.", required=True), F("amount", "Amount", "number")],
     wf("draft", [{"from": "draft", "to": "submitted", "action": "submit", "party": GC},
                  {"from": "submitted", "to": "paid", "action": "mark_paid", "party": "Owner"}])),

    # --- BIM ---
    ("coordination_issue", "Coordination Issues", "BIM", "✶", "CI", "subject", True,
     [F("subject", "Issue", required=True), F("discipline", "Discipline"), F("description", "Description", "textarea")],
     wf("open", [{"from": "open", "to": "assigned", "action": "assign", "party": GC},
                 {"from": "assigned", "to": "resolved", "action": "resolve", "party": ["Subcontractor", "Consultant", "GC"]},
                 {"from": "resolved", "to": "closed", "action": "close", "party": GC}])),

    # --- Closeout ---
    ("om_manual", "O&M Manuals", "Closeout", "▤", "OM", "name", False,
     [F("name", "Manual", required=True), F("system", "System")], SIMPLE),
    ("warranty", "Warranties", "Closeout", "▣", "WAR", "name", False,
     [F("name", "Warranty", required=True), F("vendor", "Vendor"), F("expires", "Expires", "date")], SIMPLE),
    ("commissioning", "Commissioning", "Closeout", "◉", "CX", "system", False,
     [F("system", "System", required=True), F("status", "Status")],
     wf("open", [{"from": "open", "to": "tested", "action": "test", "party": GC},
                 {"from": "tested", "to": "accepted", "action": "accept", "party": "Owner"}])),
    ("as_built", "As-Builts", "Closeout", "▭", "AB", "number", False,
     [F("number", "Sheet", required=True), F("status", "Status")], SIMPLE),
    ("completion_certificate", "Completion Certificates", "Closeout", "✓", "CC", "subject", False,
     [F("subject", "Certificate", required=True)],
     wf("draft", [{"from": "draft", "to": "issued", "action": "issue", "party": GC},
                  {"from": "issued", "to": "accepted", "action": "accept", "party": "Owner"}])),
    ("asset_register", "Asset Register", "Closeout", "▦", "AST", "name", True,
     [F("name", "Asset", required=True), F("tag", "Tag"), F("location", "Location"), F("warranty_expires", "Warranty Expires", "date")], SIMPLE),

    # --- Resources (lookup tables) ---
    ("location", "Locations", "Resources", "◎", "LOC", "name", False,
     [F("name", "Location", required=True), F("level", "Level")], SIMPLE),
    ("cost_code", "Cost Codes", "Resources", "#", "CC", "code", False,
     [F("code", "Code", required=True), F("description", "Description")], SIMPLE),
    ("labor_rate", "Labor Rates", "Resources", "$", "LR", "trade", False,
     [F("trade", "Trade", required=True), F("rate", "Rate $/hr", "number")], SIMPLE),
    ("material_rate", "Material Rates", "Resources", "$", "MR", "material", False,
     [F("material", "Material", required=True), F("rate", "Unit Rate", "number"), F("unit", "Unit")], SIMPLE),
    ("equipment_rate", "Equipment Rates", "Resources", "$", "ER", "equipment", False,
     [F("equipment", "Equipment", required=True), F("rate", "Rate $/hr", "number")], SIMPLE),
]


def main():
    created = 0
    for key, name, section, icon, prefix, title, pinnable, fields, workflow in DEFS:
        d = MODULES / key
        d.mkdir(parents=True, exist_ok=True)
        mod = {"key": key, "name": name, "section": section, "icon": icon,
               "ref_prefix": prefix, "title_field": title, "pinnable": pinnable,
               "fields": fields, "workflow": workflow}
        (d / "module.json").write_text(json.dumps(mod, indent=2), encoding="utf-8")
        created += 1
    print(f"generated {created} module.json files")


if __name__ == "__main__":
    main()
