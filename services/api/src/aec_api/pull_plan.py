"""Pull planning — the Last Planner System phase board that sits upstream of the weekly work plan.

The Last Planner System (Lean Construction Institute) plans in levels: the master schedule sets the
milestones; the team **pull-plans** each phase by working backward from a milestone, every trade posting
tasks and defining the hand-offs between them; the **lookahead** makes those tasks ready by removing
constraints (design, submittals, materials, labour, equipment, prerequisite work, permits, access,
information); the **weekly work plan** turns ready tasks into commitments; and **PPC** (Percent Plan
Complete) plus the reasons for variance close the learning loop. This engine builds the phase board as a
trade × week matrix, tracks the constraint/make-ready log, and reports readiness, commitment and PPC —
over the config-driven `pull_plan_task` records every stakeholder edits. (`lean.ppc` already scores the
separate `weekly_plan` module; this is the collaborative phase board that feeds it.)"""
from __future__ import annotations

from typing import Any

from . import modules as me

READY_STATES = ("made_ready", "committed", "done", "not_done")   # cleared the make-ready gate
COMMIT_STATES = ("committed", "done", "not_done")


def _d(rec: dict) -> dict:
    return rec.get("data") or {}


def _pct(n: int, d: int) -> float | None:
    return round(100 * n / d, 1) if d else None


def board(db, pid: str, milestone: str | None = None) -> dict[str, Any]:
    """The phase pull-plan board: trade swimlanes × weeks, the hand-off sequence, the constraint /
    make-ready log, and readiness / commitment / PPC stats."""
    tasks = me.list_records(db, "pull_plan_task", pid, limit=100000)
    if milestone:
        tasks = [t for t in tasks if (_d(t).get("milestone") or "") == milestone]

    id_to_ref = {t.get("id"): t.get("ref") for t in tasks}   # predecessor stores the record id
    trades: dict[str, list] = {}
    weeks: set[str] = set()
    milestones: set[str] = set()
    constraint_counts: dict[str, int] = {}
    constrained = ready = committed = done = not_done = 0
    nodes = []
    edges = []
    for t in tasks:
        d = _d(t)
        st = t.get("workflow_state") or "pulled"
        trade = d.get("trade") or "(unassigned)"
        wk = d.get("planned_week") or "(unscheduled)"
        weeks.add(wk)
        if d.get("milestone"):
            milestones.add(d["milestone"])
        cons = d.get("constraints") or []
        open_cons = cons if st == "pulled" else []      # once made-ready, constraints are cleared
        for cc in open_cons:
            constraint_counts[cc] = constraint_counts.get(cc, 0) + 1
        if open_cons:
            constrained += 1
        if st in READY_STATES:
            ready += 1
        if st in COMMIT_STATES:
            committed += 1
        if st == "done":
            done += 1
        if st == "not_done":
            not_done += 1
        card = {"ref": t.get("ref"), "task": d.get("task") or t.get("ref"), "trade": trade,
                "week": wk, "state": st, "responsible": d.get("responsible") or "",
                "duration_days": d.get("duration_days"), "constraints": open_cons,
                "milestone": d.get("milestone") or ""}
        trades.setdefault(trade, []).append(card)
        nodes.append(card)
        if d.get("predecessor"):
            edges.append({"from": id_to_ref.get(d["predecessor"], d["predecessor"]), "to": t.get("ref")})

    week_order = sorted(w for w in weeks if w != "(unscheduled)") + \
        (["(unscheduled)"] if "(unscheduled)" in weeks else [])
    swimlanes = [{"trade": tr, "tasks": sorted(ts, key=lambda c: c["week"])}
                 for tr, ts in sorted(trades.items())]
    total = len(tasks)
    commit_total = done + not_done
    return {
        "total": total, "milestones": sorted(milestones), "milestone_filter": milestone,
        "weeks": week_order, "swimlanes": swimlanes,
        "handoffs": edges,
        "make_ready": {"constrained_tasks": constrained,
                       "by_constraint": [{"constraint": k, "count": v}
                                         for k, v in sorted(constraint_counts.items(), key=lambda kv: -kv[1])],
                       "open_constraints": sum(constraint_counts.values())},
        "readiness": {"ready": ready, "constrained": constrained,
                      "ready_pct": _pct(ready, total)},
        "commitment": {"committed": committed, "done": done, "not_done": not_done,
                       "ppc_pct": _pct(done, commit_total)},
        "note": "Last Planner phase board: work is pulled backward from the milestone, made ready by "
                "removing constraints, committed weekly, then scored by PPC. Every trade edits its own "
                "sticky notes; PPC = completed ÷ committed.",
    }


def metrics(db, pid: str, milestone: str | None = None) -> dict[str, Any]:
    """The Last Planner learning-loop metrics beyond PPC: **Tasks-Made-Ready %** (did we clear
    constraints ahead of the work?), the **make-ready runway** (how many weeks of ready work are
    staged), **perfect-handoff %** (did trades finish cleanly for the next trade?), the **PPC trend by
    week**, and the **variance-reason Pareto** (why commitments miss). These are the reliability
    signals a pull-planning team improves week over week."""
    tasks = me.list_records(db, "pull_plan_task", pid, limit=100000)
    if milestone:
        tasks = [t for t in tasks if (_d(t).get("milestone") or "") == milestone]
    total = len(tasks)
    ref_state = {t.get("ref"): (t.get("workflow_state") or "pulled") for t in tasks}
    id_to_ref = {t.get("id"): t.get("ref") for t in tasks}

    made_ready = sum(1 for t in tasks if (t.get("workflow_state") or "pulled") in READY_STATES)
    tmr_pct = _pct(made_ready, total)

    # make-ready runway: distinct future weeks that already carry ready (made_ready+) work
    runway_weeks = sorted({(_d(t).get("planned_week") or "") for t in tasks
                           if (t.get("workflow_state") or "pulled") in READY_STATES and _d(t).get("planned_week")})

    # perfect handoffs: predecessor done AND successor at least made-ready = a clean flow hand-off
    clean = handoff_total = 0
    for t in tasks:
        pred_id = _d(t).get("predecessor")
        if not pred_id:
            continue
        handoff_total += 1
        pred_ref = id_to_ref.get(pred_id)
        if ref_state.get(pred_ref) == "done" and (t.get("workflow_state") or "pulled") in READY_STATES:
            clean += 1
    handoff_pct = _pct(clean, handoff_total)

    # PPC by planned week (over the committed tasks) — the trend line
    wk: dict[str, dict] = {}
    variance: dict[str, int] = {}
    for t in tasks:
        d = _d(t)
        st = t.get("workflow_state") or "pulled"
        w = d.get("planned_week") or "(unscheduled)"
        if st in COMMIT_STATES:
            row = wk.setdefault(w, {"committed": 0, "done": 0})
            row["committed"] += 1
            if st == "done":
                row["done"] += 1
        if st == "not_done" and d.get("variance_reason"):
            variance[d["variance_reason"]] = variance.get(d["variance_reason"], 0) + 1
    ppc_trend = [{"week": w, "committed": r["committed"], "done": r["done"],
                  "ppc_pct": _pct(r["done"], r["committed"])}
                 for w, r in sorted(wk.items()) if w != "(unscheduled)"]
    done = sum(1 for t in tasks if (t.get("workflow_state") or "") == "done")
    not_done = sum(1 for t in tasks if (t.get("workflow_state") or "") == "not_done")

    return {
        "total": total, "milestone_filter": milestone,
        "tasks_made_ready": made_ready, "tmr_pct": tmr_pct,
        "make_ready_runway_weeks": len(runway_weeks), "runway": runway_weeks,
        "perfect_handoff_pct": handoff_pct, "clean_handoffs": clean, "handoffs": handoff_total,
        "ppc_pct": _pct(done, done + not_done), "committed": done + not_done, "done": done,
        "ppc_trend": ppc_trend,
        "variance_pareto": [{"reason": k, "count": v} for k, v in sorted(variance.items(), key=lambda kv: -kv[1])],
        "note": "Last Planner reliability metrics: TMR = tasks made ready ÷ planned (are we clearing "
                "constraints ahead?); perfect-handoff = predecessor done and successor ready ÷ hand-offs; "
                "PPC trend = completion reliability week over week; variance Pareto = the top reasons work "
                "misses. Target PPC ≥ 80%.",
    }


def pdf(db, pid: str, project_name: str, milestone: str | None = None) -> bytes:
    """Pull-plan board (PDF): the trade × week matrix, the constraint/make-ready log, and the PPC line —
    the printout a pull-planning session hands out."""
    import io

    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.pdfgen import canvas

    b = board(db, pid, milestone)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(letter))
    w, h = landscape(letter)
    margin, y = 40, h - 40
    c.setFont("Helvetica-Bold", 15)
    c.drawString(margin, y, "Pull Plan (Last Planner System)")
    c.setFont("Helvetica", 9)
    y -= 14
    c.drawString(margin, y, f"{project_name}" + (f"  —  milestone: {milestone}" if milestone else "")
                 + f"   ·   PPC {b['commitment']['ppc_pct'] if b['commitment']['ppc_pct'] is not None else '-'}%"
                 + f"   ·   {b['readiness']['ready']}/{b['total']} ready")
    y -= 18

    weeks = b["weeks"][:8]                                # keep the grid printable
    trade_w, week_w = 110, (w - 2 * margin - 110) / max(1, len(weeks))
    # header row
    c.setFont("Helvetica-Bold", 8)
    c.drawString(margin, y, "Trade")
    for i, wk in enumerate(weeks):
        c.drawString(margin + trade_w + i * week_w, y, wk[:14])
    y -= 4
    c.line(margin, y, w - margin, y)
    y -= 12
    c.setFont("Helvetica", 7)
    glyph = {"done": "[x]", "not_done": "[!]", "committed": "[o]", "made_ready": "[r]", "pulled": "[ ]"}
    for lane in b["swimlanes"]:
        rows = max(1, max((sum(1 for t in lane["tasks"] if t["week"] == wk) for wk in weeks), default=1))
        c.setFont("Helvetica-Bold", 8)
        c.drawString(margin, y, lane["trade"][:16])
        c.setFont("Helvetica", 7)
        for i, wk in enumerate(weeks):
            cell = [t for t in lane["tasks"] if t["week"] == wk]
            yy = y
            for t in cell[:4]:
                c.drawString(margin + trade_w + i * week_w, yy,
                             (glyph.get(t["state"], "[ ]") + " " + t["task"])[:26])
                yy -= 9
        y -= max(rows, 1) * 9 + 6
        if y < 90:
            c.showPage(); y = h - 50; c.setFont("Helvetica", 7)

    # constraint log
    y -= 6
    c.setFont("Helvetica-Bold", 9); c.drawString(margin, y, "Make-ready — open constraints"); y -= 12
    c.setFont("Helvetica", 8)
    if b["make_ready"]["by_constraint"]:
        for row in b["make_ready"]["by_constraint"]:
            c.drawString(margin, y, f"  {row['constraint']}: {row['count']}"); y -= 11
            if y < 60:
                c.showPage(); y = h - 50
    else:
        c.drawString(margin, y, "  none — all planned work is ready."); y -= 11
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(margin, 30, "[x] done  [!] missed  [o] committed  [r] ready  [ ] constrained/pulled")
    c.showPage(); c.save()
    return buf.getvalue()
