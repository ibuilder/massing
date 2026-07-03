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
