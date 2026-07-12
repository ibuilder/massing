"""Report builders — bim domain (extracted from reports.py, A2)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..reports_core import Report
from ..reports_core import money as _money
from ._common import _records


def _bim_kpi(db: Session, pid: str, name: str) -> Report:
    """BIM KPI scorecard (ISO 19650): the ten information-management categories graded, plus the
    handover data-drop acceptance checklist."""
    from .. import bim_kpi
    sc = bim_kpi.scorecard(db, pid)
    ha = bim_kpi.handover_acceptance(db, pid)
    r = Report("BIM KPI Scorecard (ISO 19650)", name)
    s = sc["summary"]
    r.kpi("Health", f"{s['health_pct']}%" if s["health_pct"] is not None else "—")
    r.kpi("Good / Warn / Poor", f"{s['good']} / {s['warn']} / {s['poor']}")
    r.kpi("Not scored (n/a)", s["na"])
    r.kpi("Model scored", "yes" if sc["model_scored"] else "no")
    r.kpi("Handover acceptance", "ACCEPTED" if ha["accepted"] else "not ready")
    r.table("KPI categories", ["Category", "Grade", "Headline"],
            [[c["label"], c["grade"].upper(), c["headline"]] for c in sc["categories"]])
    r.table("Handover data-drop acceptance", ["Check", "Status"],
            [[c["label"], "OK" if c["ok"] else "missing"] for c in ha["checks"]])
    return r


def _model_health(db: Session, pid: str, name: str) -> Report:
    """Model Health — the single composite score over the model-quality checks (integrity/hygiene, ISO
    19650 KPIs, clash coordination, verified-as-built), each lens graded and headlined."""
    import json

    from .. import model_health, storage
    from ..deps import open_source_ifc
    model = None
    try:
        model = open_source_ifc(db, pid)             # enables the hygiene lens
    except Exception:            # noqa: BLE001 — score the DB-based lenses without a parsed model
        pass
    try:
        elements = json.loads(storage.get(f"{pid}/props.json")).get("elements", [])
    except Exception:            # noqa: BLE001
        elements = []
    h = model_health.scorecard(db, pid, model=model, elements=elements)
    r = Report("Model Health Scorecard", name)
    r.kpi("Overall", f"{h['overall_score']}/100" if h["overall_score"] is not None else "—")
    r.kpi("Band", h["band"])
    r.kpi("Checks scored", f"{h['scored_lenses']} / {len(h['lenses'])}")
    r.kpi("Model parsed", "yes" if h["model_available"] else "no")
    if any(ln["score"] is not None for ln in h["lenses"]):
        scored = [ln for ln in h["lenses"] if ln["score"] is not None]
        r.chart("bar", "Health by lens", [ln["label"] for ln in scored],
                [{"name": "Score", "values": [ln["score"] for ln in scored]}])
    r.table("Model-quality lenses", ["Lens", "Score", "Status", "Headline"],
            [[ln["label"], f"{ln['score']}/100" if ln["score"] is not None else "n/a",
              ln["status"].upper(), ln["headline"]] for ln in h["lenses"]])
    return r


def _bep(db: Session, pid: str, name: str) -> Report:
    """ISO 19650 BIM Execution Plan — a produced governance document, assembled from the CDE, the
    information-requirements register, the discipline vocabulary and the delivery (drawing-set)
    register. Answers WHO does WHAT, to WHAT level, WHEN, and HOW information is managed."""
    from .. import cde, classification
    cde_st = cde.status(db, pid)
    reqs = cde.requirements(db, pid)
    disc = classification.disciplines()
    sets = _records(db, "drawing_set", pid)
    core = reqs["core_coverage"]

    r = Report("BIM Execution Plan (BEP)", name)
    r.kpi("Disciplines", len(disc))
    r.kpi("Information requirements", reqs["total"])
    r.kpi("Core coverage (EIR/BEP/AIR)",
          "complete" if core["complete"] else "missing " + ", ".join(core["missing"]))
    r.kpi("CDE containers", cde_st["total"])
    r.kpi("Published", cde_st["discipline"]["published"])
    r.kpi("Delivery sets", len(sets))
    r.kpi("Metadata completeness", f"{cde_st['discipline']['metadata_completeness_pct']}%")

    # 1. Information-requirements register (OIR / PIR / AIR / EIR / BEP / MIDP / TIDP)
    r.table("Information requirements register", ["Type", "Total", "Issued", "Draft", "Superseded"],
            [[code, b["total"], b["issued"], b["draft"], b["superseded"]]
             for code, b in reqs["by_type"].items()] or [["(none logged)", "", "", "", ""]])

    # 2. Roles, responsibilities & authorities (ISO 19650 appointment roles + discipline leads)
    roles = [["Appointing Party (Owner)", "Sets the EIR; approves deliverables; owns the asset information."],
             ["Lead Appointed Party (BIM Manager)", "Owns this BEP and the CDE; coordinates the federated model; QA."],
             ["Information Manager", "Runs the CDE workflow (WIP -> Shared -> Published -> Archived) and naming/standards."]]
    roles += [[f"{d['code']} — {d['name']} lead (Appointed Party)",
               f"Authors and coordinates the {d['name']} model; delivers MasterFormat "
               + ", ".join(d["divisions"]) + " content."] for d in disc]
    r.table("Roles, responsibilities & authorities", ["Role", "Responsibility"], roles)

    # 3. Level of Information Need (target LOD per delivery stage; A2 refines to per-element)
    r.table("Level of Information Need (target by stage)", ["Stage", "Target LOD", "Information focus"],
            [["Concept / SD (RIBA 2)", "LOD 200", "Generalized geometry, approximate quantities, orientation"],
             ["Design Development (RIBA 3)", "LOD 300", "Exact dimensions, materials, discipline coordination"],
             ["Construction Docs (RIBA 4)", "LOD 350", "System interfaces, clash coordination, connections"],
             ["Construction (RIBA 5)", "LOD 400", "Fabrication and installation detail, shop drawings"],
             ["Handover / As-built (RIBA 6)", "LOD 500", "Verified as-built condition and asset / O&M data"]])

    # 4. Information delivery / exchange schedule (MIDP / TIDP -> delivery sets)
    def _d2(x):
        return x.get("data") or x
    r.table("Information delivery schedule", ["Delivery set", "Discipline", "Issued", "Purpose", "State"],
            [[str(_d2(s).get("name") or _d2(s).get("title") or s.get("id", ""))[:60],
              _d2(s).get("discipline", ""),
              str(_d2(s).get("issued_date") or _d2(s).get("issue_date") or ""),
              _d2(s).get("purpose", ""), s.get("workflow_state", "")]
             for s in sets] or [["(no delivery sets registered)", "", "", "", ""]])

    # 5. Information standards & naming conventions
    r.table("Information standards & naming", ["Item", "Convention"],
            [["Sheet identification", "US NCS: discipline designator + sheet-type digit + sequence "
              "(e.g. A-101 = Architectural / Plans / 01)."],
             ["Container / file naming", "Type_Discipline_Description_Revision_Date; revision-controlled, "
              "approved files never overwritten."],
             ["Classification", "CSI MasterFormat divisions + Uniformat II elements, tagged via "
              "IfcClassificationReference and keyed to GlobalId."],
             ["Discipline designators", ", ".join(f"{d['code']}={d['name']}" for d in disc)]])

    # 6. CDE & information management (ISO 19650 states)
    st = cde_st["by_state"]
    r.table("CDE workflow (ISO 19650)", ["State", "Metric"],
            [["WIP", st.get("wip", 0)], ["Shared", st.get("shared", 0)],
             ["Published", st.get("published", 0)], ["Archived", st.get("archived", 0)],
             ["Revision control", f"{cde_st['discipline']['revision_control_pct']}%"],
             ["Approval-status coverage", f"{cde_st['discipline']['approval_status_pct']}%"]])

    # 7. Model coordination & quality assurance
    missing = core["missing"]
    r.table("Model coordination & QA", ["Process", "Definition"],
            [["Federation", "Discipline models federated on shared GlobalIds; each authored in its own container."],
             ["Clash detection", "Cross-discipline clash run each coordination cycle; issues round-tripped via BCF."],
             ["Model quality", "IDS validation + LOIN + metadata completeness scored in the openBIM quality "
              "scorecard and the BIM-KPI report."],
             ["Requirement coverage",
              "Compliant." if not missing else "Missing core requirement(s): " + ", ".join(missing)]])
    return r


def _lod(db: Session, pid: str, name: str) -> Report:
    """LOD matrix + achieved-LOD coverage of the loaded model (inferred from LOIN facets)."""
    from .. import lod
    from ..model_index import _INDEX, _ensure_loaded
    try:
        _ensure_loaded(pid)
    except Exception:                     # noqa: BLE001 — targets-only when no model is loaded
        pass
    a = lod.assess(db, pid, _INDEX.get(pid))
    r = Report("LOD Matrix & Coverage", name)
    r.kpi("Model scored", "yes" if a["model_scored"] else "no")
    r.kpi("Elements", a["elements"])
    r.kpi("Targets", len(a["targets"]) if a["targets"] else f"{len(a['default'])} (stage defaults)")
    if a["model_scored"] and a["elements"]:
        r.kpi("Most common LOD", max(a["distribution"].items(), key=lambda kv: kv[1])[0])
    tgt = a["targets"] or [{"phase": t["phase"], "discipline": "(all)", "element_category": "(all)",
                            "target_lod": t["target_lod"]} for t in a["default"]]
    r.table("Target LOD matrix", ["Stage", "Discipline", "Element / category", "Target LOD"],
            [[t.get("phase", ""), t.get("discipline", ""), t.get("element_category", ""),
              t.get("target_lod", "")] for t in tgt])
    if a["model_scored"]:
        r.table("Achieved LOD — distribution", ["LOD band", "Elements"],
                [[k, v] for k, v in a["distribution"].items()])
        r.table("Achieved LOD — by discipline", ["Discipline", "Elements", "Avg achieved LOD"],
                [[d["discipline"], d["elements"], d["avg_lod"]] for d in a["by_discipline"]]
                or [["(none)", "", ""]])
        r.chart("bar", "Achieved LOD distribution", list(a["distribution"].keys()),
                [{"name": "Elements", "values": list(a["distribution"].values())}])
    return r


def _naming(db: Session, pid: str, name: str) -> Report:
    """Naming-convention compliance across the CDE containers + drawing register."""
    from .. import naming
    a = naming.audit(db, pid)
    conv = a["conventions"]
    cc, ss = a["containers"], a["sheets"]
    r = Report("Naming Convention Compliance", name)
    r.kpi("Container documents", cc["total"])
    r.kpi("Container compliance", f"{cc['compliance_pct']}%" if cc["compliance_pct"] is not None else "—")
    r.kpi("Drawing sheets", ss["total"])
    r.kpi("Sheet-ID compliance", f"{ss['compliance_pct']}%" if ss["compliance_pct"] is not None else "—")
    r.table("Conventions", ["Kind", "Pattern", "Example / note"],
            [["Container / document", conv["container"]["pattern"], conv["container"]["note"]],
             ["Drawing sheet", conv["sheet"]["pattern"], conv["sheet"]["note"]]])
    r.table("Container naming violations", ["Name", "Issues"],
            [[v["name"], "; ".join(v["issues"])] for v in cc["violations"]] or [["(all compliant)", ""]])
    r.table("Sheet-ID violations", ["Sheet", "Issues"],
            [[v["name"], "; ".join(v["issues"])] for v in ss["violations"]] or [["(all compliant)", ""]])
    return r


def _document_control(db: Session, pid: str, name: str) -> Report:
    """Document-control health over the standard folder taxonomy: naming, required-folder coverage,
    revision control, CDE-state spread and required-doc gaps."""
    from .. import docmanager
    h = docmanager.health(pid)
    t = docmanager.tree(pid)

    def _p(v):
        return f"{v}%" if v is not None else "—"
    r = Report("Document Control Health", name)
    r.kpi("Documents on file", h["total_files"])
    r.kpi("Naming compliance", _p(h["naming_compliance_pct"]))
    r.kpi("Required-folder coverage", _p(h["required_coverage_pct"]))
    r.kpi("Revision control", _p(h["revision_control_pct"]))
    if h["by_cde_state"]:
        r.chart("bar", "Documents by CDE state", list(h["by_cde_state"].keys()),
                [{"name": "Files", "data": list(h["by_cde_state"].values())}])
    r.table("Required documents still missing", ["Folder"],
            [[p] for p in h["required_missing"]] or [["(all required folders populated)"]])
    r.table("Folders (file counts + owner)", ["Folder", "Owner", "Files"],
            [[n["path"], n.get("owner_role") or "", n["count"]]
             for n in t["nodes"] if n["depth"] == 0])
    return r


def _design_options(db: Session, pid: str, name: str) -> Report:
    """Design options / variants compared on program + economics, best-in-class per metric."""
    from .. import design_options
    a = design_options.compare(db, pid)
    r = Report("Design Options Comparison", name)
    r.kpi("Options", a["count"])
    r.kpi("Selected", a["selected"] or "—")
    for ldr in a["leaders"].values():
        if ldr["option"]:
            r.kpi(ldr["label"], ldr["option"])
    r.table("Options", ["Option", "State", "Area (sf)", "Units", "Eff %", "Hard cost", "$/sf", "EUI", "IRR %"],
            [[o["name"], o["state"], o["gross_area_sf"], o["unit_count"], o["efficiency_pct"],
              _money(o["hard_cost"]) if o["hard_cost"] is not None else "", o["cost_per_sf"],
              o["energy_eui"], o["irr_pct"]] for o in a["options"]] or [["(no options)"] + [""] * 8])
    if any(o["irr_pct"] is not None for o in a["options"]):
        r.chart("bar", "Levered IRR by option", [o["name"] for o in a["options"]],
                [{"name": "IRR %", "values": [o["irr_pct"] or 0 for o in a["options"]]}])
    return r


def _design_standards(db: Session, pid: str, name: str) -> Report:
    """Design-standards ruleset + model compliance (prohibited / non-approved type + material use)."""
    from .. import design_standards
    from ..model_index import _INDEX, _ensure_loaded
    try:
        _ensure_loaded(pid)
    except Exception:                     # noqa: BLE001 — ruleset-only when no model is loaded
        pass
    a = design_standards.check(db, pid, _INDEX.get(pid))
    rs = a["ruleset"]
    r = Report("Design Standards Compliance", name)
    r.kpi("Standards", rs["count"])
    r.kpi("Approved / preferred", len(rs["by_status"]["approved"]) + len(rs["by_status"]["preferred"]))
    r.kpi("Prohibited", len(rs["by_status"]["prohibited"]))
    r.kpi("Model scored", "yes" if a["model_scored"] else "no")
    if a["model_scored"]:
        r.kpi("Prohibited hits", a["prohibited_hits"])
        r.kpi("Unapproved", a["unapproved"])
    r.table("Ruleset", ["Item", "Category", "Status", "Discipline", "Match keyword"],
            [[i["name"], i["category"], i["status"], i["discipline"], i["match_keyword"]]
             for i in rs["items"]] or [["(none defined)"] + [""] * 4])
    if a["model_scored"]:
        r.table("Model violations", ["Element", "Type", "Issue"],
                [[v["guid"][:22], v["type"], v["issue"]] for v in a["violations"]] or [["(none)", "", ""]])
    return r


def _mep(db: Session, pid: str, name: str) -> Report:
    """MEP equipment schedule + per-system rollup + first-pass duct/pipe sizing reference tables."""
    from .. import mep
    s = mep.schedule(db, pid)
    r = Report("MEP Equipment Schedule", name)
    r.kpi("Equipment items", s["count"])
    r.kpi("Systems", len(s["by_system"]))
    r.table("Equipment schedule", ["Tag", "Type", "System", "Capacity", "Unit", "Flow", "Size", "State"],
            [[i["tag"], i["type"], i["system"], i["capacity"], i["capacity_unit"], i["flow"],
              i["size"], i["state"]] for i in s["items"]] or [["(none)"] + [""] * 7])
    r.table("System rollup", ["System", "Items", "Total capacity"],
            [[b["system"], b["count"],
              ", ".join(f"{v} {u}" for u, v in b["capacity_by_unit"].items()) or "—"]
             for b in s["by_system"]] or [["(none)", "", ""]])
    # model-derived MEP counts (complements the register when a model is loaded)
    try:
        from ..model_index import _INDEX, _ensure_loaded
        _ensure_loaded(pid)
        mx = mep.extract_from_model(_INDEX.get(pid))
    except Exception:                     # noqa: BLE001 — targets-only when no model is loaded
        mx = {"model_scored": False, "mep_elements": 0, "by_class": []}
    if mx.get("model_scored"):
        r.kpi("MEP elements (model)", mx["mep_elements"])
        r.table("MEP elements off the model", ["IFC class", "Type", "Count"],
                [[x["ifc_class"], x["label"], x["count"]] for x in mx["by_class"]] or [["(none)", "", ""]])
    r.table("Duct sizing reference (equal-velocity @ 1000 fpm)", ["CFM", "Round diameter (in)"],
            [[q, mep.size_duct(q)["round_diameter_in"]] for q in (500, 1000, 2000, 4000, 8000)])
    r.table("Pipe sizing reference (velocity @ 6 fps)", ["GPM", "Nominal size (in)"],
            [[q, mep.size_pipe(q)["nominal_pipe_size_in"]] for q in (20, 50, 100, 200, 400)])
    return r


def _resource_loading(db: Session, pid: str, name: str) -> Report:
    """Resource histogram + S-curve + peak manpower from the crew-loaded schedule."""
    from .. import resource_loading
    a = resource_loading.loading(db, pid)
    r = Report("Resource-Loaded Schedule", name)
    r.kpi("Loaded resources", a["loads"])
    r.kpi("Weeks", a["weeks_span"])
    r.kpi("Trades", len(a["trades"]))
    r.kpi("Peak units", f"{a['peak']['units']} ({a['peak']['week']})" if a["peak"]["week"] else "—")
    r.kpi("Total cost", _money(a["total_cost"]))
    r.table("Weekly resource histogram", ["Week", "Total units", "Cost"] + a["trades"],
            [[w["week"], w["total"], _money(w["cost"])] + [w["by_trade"].get(t, 0) for t in a["trades"]]
             for w in a["histogram"]] or [["(no resource-loaded activities)"] + [""] * (len(a["trades"]) + 2)])
    if a["histogram"]:
        r.chart("bar", "Resource histogram (peak units/week)", [w["week"] for w in a["histogram"]],
                [{"name": "Units", "values": [w["total"] for w in a["histogram"]]}])
        r.chart("line", "Cumulative units + cost (S-curves)", [p["week"] for p in a["scurve"]],
                [{"name": "Units", "values": [p["cumulative"] for p in a["scurve"]]},
                 {"name": "Cost", "values": [p["cumulative"] for p in a["cost_curve"]]}])
    return r


def _envelope(db: Session, pid: str, name: str) -> Report:
    """Envelope assemblies checked against IECC 2021 climate-zone minimums."""
    from .. import envelope
    a = envelope.audit(db, pid)
    r = Report("Envelope Code Compliance (IECC 2021)", name)
    r.kpi("Assemblies", a["total"])
    r.kpi("Checked", a["checked"])
    r.kpi("Compliant", a["compliant"])
    r.kpi("Compliance", f"{a['compliance_pct']}%" if a["compliance_pct"] is not None else "—")
    r.table("Envelope compliance", ["Assembly", "Type", "Zone", "Provided", "Required", "Result"],
            [[x.get("name", ""), x.get("element_type", ""), x.get("climate_zone", ""),
              (f"R{x['provided_r']}" if x.get("provided_r") is not None else
               (f"U{x['provided_u']}" if x.get("provided_u") is not None else "—")),
              (f"R≥{x['required_min_r']}" if "required_min_r" in x else
               (f"U≤{x['required_max_u']}" if "required_max_u" in x else "—")),
              ("PASS" if x["compliant"] else "FAIL") if x.get("compliant") is not None
              else x.get("issue", "—")]
             for x in a["results"]] or [["(no assemblies)"] + [""] * 5])
    return r


def _productivity(db: Session, pid: str, name: str) -> Report:
    """Field labor productivity — per-entry units/man-hour + a by-trade rollup."""
    from .. import productivity
    s = productivity.summary(db, pid)
    r = Report("Field Labor Productivity", name)
    r.kpi("Entries", s["count"])
    r.kpi("Total man-hours", s["total_man_hours"])
    r.kpi("Overall units/man-hr", s["overall_units_per_manhour"] if s["overall_units_per_manhour"] is not None else "—")
    r.table("By trade", ["Trade", "Quantity", "Man-hours", "Units/man-hr"],
            [[t["trade"], t["quantity"], t["man_hours"], t["units_per_manhour"]]
             for t in s["by_trade"]] or [["(none)", "", "", ""]])
    r.table("Entries", ["Date", "Trade", "Activity", "Qty", "Unit", "Man-hrs", "Units/man-hr"],
            [[e["date"], e["trade"], e["activity"], e["quantity"], e["unit"], e["man_hours"],
              e["units_per_manhour"]] for e in s["entries"]] or [["(no entries)"] + [""] * 6])
    if s["by_trade"]:
        r.chart("bar", "Productivity by trade (units/man-hr)", [t["trade"] for t in s["by_trade"]],
                [{"name": "Units/man-hr", "values": [t["units_per_manhour"] or 0 for t in s["by_trade"]]}])
    return r
