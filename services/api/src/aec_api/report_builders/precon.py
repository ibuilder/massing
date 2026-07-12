"""Report builders — precon domain (extracted from reports.py, A2)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import modules as me
from .. import px
from ..reports_core import Report
from ..reports_core import money as _money


def _estimate_continuity(db: Session, pid: str, name: str) -> Report:
    from .. import precon
    s = precon.estimate_continuity(db, pid)
    r = Report("Estimate Continuity (Preconstruction)", name)
    r.kpi("Estimate sets", s["set_count"])
    r.kpi("Latest", f"{_money(s['latest_total'])} ({s['latest_milestone'] or '—'})")
    if s["latest_psf"]:
        r.kpi("$/SF", _money(s["latest_psf"]))
    r.kpi("Drift (first→latest)", f"{_money(s['total_drift'])}"
          + (f" ({s['total_drift_pct']:+.1f}%)" if s["total_drift_pct"] is not None else ""))
    r.kpi("Budget / GMP", _money(s["budget"]) if s["budget"] is not None else "—")
    if s["variance_to_budget"] is not None:
        r.kpi("Variance to budget", ("OVER " if s["over_budget"] else "under ") + _money(abs(s["variance_to_budget"])))
    if any(x["total"] for x in s["rows"]):
        r.chart("line", "Estimate by design milestone", [x["milestone"] for x in s["rows"]],
                [{"name": "Total", "values": [round(x["total"]) for x in s["rows"]]}])
    r.table("Milestone estimates", ["Milestone", "Title", "Total", "$/SF", "Δ vs prev", "Δ%", "Basis", "Date"],
            [[x["milestone"], x.get("title", ""), _money(x["total"]),
              _money(x["psf"]) if x["psf"] is not None else "—",
              _money(x["delta_total"]) if x["delta_total"] is not None else "—",
              f"{x['delta_pct']:+.1f}%" if x.get("delta_pct") is not None else "—",
              x.get("basis") or "", x.get("estimate_date") or ""]
             for x in s["rows"]] or [["(no estimate sets — create them under Preconstruction ▸ Estimate Sets)"] + [""] * 7])
    return r


def _decision_log(db: Session, pid: str, name: str) -> Report:
    from .. import precon
    s = precon.decision_log(db, pid)
    r = Report("Decision Log", name)
    r.kpi("Decisions", s["decision_count"])
    r.kpi("Open", s["open_count"])
    r.kpi("Disputed", s["disputed_count"])
    r.kpi("Open cost exposure", _money(s["open_cost_exposure"]))
    r.kpi("Open schedule exposure", f"{s['open_schedule_exposure_days']} d")
    r.table("Decisions", ["Ref", "Decision", "Category", "Alignment", "State", "Cost", "Sched (d)", "Decide by"],
            [[x.get("ref", ""), x.get("subject", ""), x.get("category", ""), x.get("alignment", ""),
              x.get("state", ""), _money(x["cost_impact"]), x.get("schedule_impact_days", ""),
              x.get("due_date") or ""] for x in s["rows"]] or [["(no decisions logged)"] + [""] * 7])
    return r


def _assumptions_register(db: Session, pid: str, name: str) -> Report:
    from .. import precon
    s = precon.assumptions(db, pid)
    r = Report("Assumptions & Clarifications", name)
    r.kpi("Assumptions", s["assumption_count"])
    r.kpi("Open", s["open_count"])
    r.kpi("Confirmed", s["confirmed_count"])
    r.kpi("Open allowance exposure", _money(s["open_cost_exposure"]))
    r.table("Register", ["Ref", "Assumption", "Category", "State", "Cost / allowance", "Owner"],
            [[x.get("ref", ""), x.get("subject", ""), x.get("category", ""), x.get("state", ""),
              _money(x["cost_impact"]), x.get("owner") or ""]
             for x in s["rows"]] or [["(no assumptions logged)"] + [""] * 5])
    return r


def _precon_alignment(db: Session, pid: str, name: str) -> Report:
    from .. import precon
    s = precon.alignment(db, pid)
    r = Report("Preconstruction Alignment", name)
    r.kpi("Alignment score", f"{s['alignment_score']}/100" if s["alignment_score"] is not None else "—")
    r.kpi("Status", str(s["overall_status"]).upper())
    r.kpi("Latest estimate", f"{_money(s['latest_total'])} ({s['latest_milestone'] or '—'})")
    if s["variance_to_budget"] is not None:
        r.kpi("Vs budget", ("OVER " if s["variance_to_budget"] > 0 else "under ") + _money(abs(s["variance_to_budget"])))
    r.kpi("VE accepted / pipeline", f"{_money(s['ve_accepted'])} / {_money(s['ve_pipeline'])}")
    r.kpi("Open decisions / assumptions", f"{s['open_decisions']} / {s['open_assumptions']}")
    r.table("Alignment by domain", ["Domain", "Status", "Detail"],
            [[d["label"], d["status"].upper(), d["headline"]] for d in s["domains"]])
    return r


def _stakeholder_analysis(db: Session, pid: str, name: str) -> Report:
    """Power/interest (Mendelow) grid + stance read of the stakeholder register."""
    from .. import stakeholder
    a = stakeholder.analysis(db, pid)
    r = Report("Stakeholder Analysis", name)
    r.kpi("Stakeholders", a["total"])
    r.kpi("Supporters", f"{a['stance']['Supporter']} ({a['supporter_pct'] or 0}%)")
    r.kpi("Blockers", a["stance"]["Blocker"])
    for k in ("manage_closely", "keep_satisfied", "keep_informed", "monitor"):
        q = a["quadrants"][k]
        if q["stakeholders"]:
            r.table(f"{q['label']} ({q['count']}) — {q['advice']}",
                    ["Ref", "Name", "Organization", "Category", "Stance"],
                    [[s.get("ref") or "", s.get("name") or "", s.get("organization") or "",
                      s.get("category") or "", s.get("stance") or ""] for s in q["stakeholders"]])
    if a["high_power_blockers"]:
        r.table("High-power blockers to address", ["Ref", "Name", "Organization"],
                [[s.get("ref") or "", s.get("name") or "", s.get("organization") or ""]
                 for s in a["high_power_blockers"]])
    return r


def _site_feasibility(db: Session, pid: str, name: str) -> Report:
    from .. import feasibility as feas
    f = feas.feasibility(db, pid)
    r = Report("Site Feasibility / Zoning Envelope", name)
    if f.get("error"):
        r.table("Feasibility", ["Status"], [[f"{f['error']} — add a Zoning & Site record under Preconstruction."]])
        return r
    def sf(v):
        return f"{v:,.0f} SF" if isinstance(v, (int, float)) else "—"
    r.kpi("Site area", f"{f['site_area_sf']:,.0f} SF ({f['site_area_acres']:g} ac)")
    r.kpi("Allowed GFA", sf(f.get("allowed_gfa_sf")))
    r.kpi("Binding constraint", f.get("binding_constraint") or "—")
    r.kpi("Max floors", f.get("max_floors") if f.get("max_floors") is not None else "—")
    r.kpi("Unit yield", f.get("unit_yield") if f.get("unit_yield") is not None else "—")
    r.kpi("Parking required", f.get("parking_required") if f.get("parking_required") is not None else "—")
    if f.get("constraints"):
        r.table("Envelope constraints (the minimum binds)", ["Constraint", "Limit GFA", "Basis"],
                [[c["constraint"], sf(c["limit_gfa_sf"]), c["basis"]] for c in f["constraints"]])
    m = f.get("model")
    if m:
        r.table("Model reconciliation", ["Actual GFA", "FAR used", "% of allowed", "Headroom", "Status"],
                [[sf(m["actual_gfa_sf"]), m["far_used"], f"{m['pct_of_allowed']}%",
                  sf(m["headroom_gfa_sf"]), m["status"]]])
    summary = [["Net buildable (efficiency-adjusted)", sf(f.get("net_buildable_sf"))],
               ["Buildable footprint", sf(f.get("buildable_footprint_sf"))],
               ["Required open space", sf(f.get("open_space_required_sf"))]]
    r.table("Program summary", ["Metric", "Value"], summary)
    if f.get("warnings"):
        r.table("Notes", ["Assumption / gap"], [[w] for w in f["warnings"]])
    return r


def _executive(db: Session, pid: str, name: str) -> Report:
    s = px.summary(db, pid)
    sch, bud = s["schedule"], s["budget"]
    r = Report("Executive Summary", name)
    r.kpi("Overall status", s["status"].replace("_", " ").title())
    r.kpi("SPI", sch["spi"] if sch["spi"] is not None else "—")
    r.kpi("% complete", f"{sch['pct_complete']}%")
    r.kpi("EAC", _money(bud["eac"]))
    r.kpi("Variance at completion", _money(bud["variance_at_completion"]))
    r.kpi("Committed", f"{bud['committed_pct']}%")
    r.kpi("Spent", f"{bud['spent_pct']}%")
    # per-state tallies via SQL GROUP BY — never materialize the records just to count them (a big
    # project has 100k+ RFIs/submittals; loading them all to produce two integers is the audit's #1
    # report-perf gap). "Open" = anything not in a terminal state.
    _TERMINAL = {"closed", "executed", "approved", "rejected", "answered", "void"}
    open_counts = []
    for key, label in [("rfi", "Open RFIs"), ("submittal", "Open submittals"), ("cor", "Open change orders")]:
        sc = me.state_counts(db, key, pid)
        total = sum(sc.values())
        open_n = sum(n for st, n in sc.items() if st not in _TERMINAL)
        open_counts.append([label, open_n, total])
    inc_total = sum(me.state_counts(db, "incident", pid).values())
    open_counts.append(["Safety incidents", inc_total, inc_total])
    r.table("Open items", ["Item", "Open", "Total"], open_counts)
    al = px.alerts(db, pid)
    r.kpi("Schedule alerts", f"{al['counts']['high']} high / {al['counts']['medium']} med")
    if al["alerts"]:
        r.table("Predictive schedule alerts", ["Level", "Alert", "Detail"],
                [[a["level"].upper(), a["title"], a.get("detail", "")] for a in al["alerts"][:25]])
    return r


def _risk(db: Session, pid: str, name: str) -> Report:
    dg = px.risk_digest(db, pid)
    r = Report("Risk Digest", name)
    r.kpi("Headline", dg.get("headline") or "—")
    r.kpi("Risks flagged", len(dg.get("risks", [])))
    if dg.get("risks"):
        r.table("Prioritized risks", ["Level", "Risk"],
                [[str(x.get("level", "")).upper(), x.get("text", "")] for x in dg["risks"]])
    if dg["drivers"].get("top_alerts"):
        r.table("Top schedule alerts", ["Level", "Alert", "Detail"],
                [[a["level"].upper(), a["title"], a.get("detail", "")] for a in dg["drivers"]["top_alerts"]])
    return r
