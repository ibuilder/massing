"""Project-executive summary — the one view a PX lives in: is the job **on schedule** and **on
budget**? Aggregates the schedule (cost-loaded SPI, % complete, critical path, lookahead, milestones)
next to the budget (GMP, EAC, variance-at-completion, buyout, cash flow) into a single health payload
with an overall status. Reuses the project_budget + schedule_cpm engines (no new source of truth)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from . import project_budget as pb
from . import schedule_cpm


def _n(v: Any) -> float:
    return pb._n(v)


def summary(db: Session, pid: str, proforma_hard: float | None = None) -> dict:
    budget = pb.gmp_budget(db, pid, proforma_hard=proforma_hard)
    cash = pb.cashflow(db, pid)
    acts = pb._records(db, "schedule_activity", pid)
    today = date.today()

    # --- cost-loaded schedule performance (SPI = earned / planned value to date) ----
    pv = ev = 0.0
    pct_vals: list[float] = []
    late_ms = due_ms = upcoming_ms = 0
    lookahead = 0
    horizon = today + timedelta(days=21)
    for r in acts:
        d = r.get("data") or {}
        bud, pct = _n(d.get("budget")), _n(d.get("percent"))
        s, f = pb._pdate(d.get("start")), pb._pdate(d.get("finish"))
        f = f or s
        if bud and s and f:
            frac = 0.0 if today < s else 1.0 if today >= f else (today - s).days / max(1, (f - s).days)
            pv += bud * frac
            ev += bud * pct / 100
        if pct:
            pct_vals.append(pct)
        # near-term activity count (lookahead)
        if s and f and s < horizon and f >= today:
            lookahead += 1
        # milestone status
        if d.get("activity_type") == "Milestone" or (s and f and s == f):
            when = f or s
            if pct >= 100:
                pass
            elif when and when < today:
                late_ms += 1
            elif when and when <= today + timedelta(days=14):
                due_ms += 1
            else:
                upcoming_ms += 1

    spi = round(ev / pv, 2) if pv else None
    pct_complete = round(sum(pct_vals) / len(pct_vals), 1) if pct_vals else 0.0
    cpm = schedule_cpm.compute(acts)

    tot = budget["totals"]
    gmp = budget["gmp"]
    comp = budget.get("completion") or {}
    on_budget = tot["variance"] >= 0                       # variance-at-completion not negative
    on_schedule = spi is None or spi >= 0.95
    status = ("on_track" if (on_budget and on_schedule)
              else "behind" if (not on_budget and not on_schedule)
              else "at_risk")

    # current-month draw from the cash-flow curve
    this_month = today.strftime("%Y-%m")
    draw = next((b["cost"] for b in cash["series"] if b["month"] == this_month), 0.0)

    return {
        "status": status,
        "schedule": {
            "spi": spi,
            "pct_complete": pct_complete,
            "activities": len(acts),
            "critical_path_days": cpm.get("project_duration", 0),
            "critical_activities": cpm.get("critical_count", 0),
            "lookahead_3wk": lookahead,
            "milestones": {"late": late_ms, "due_soon": due_ms, "upcoming": upcoming_ms},
        },
        "budget": {
            "gmp": gmp["computed"],
            "revised_gmp": gmp.get("revised", gmp["computed"]),
            "eac": tot.get("eac", tot["forecast"]),
            "variance_at_completion": tot["variance"],
            "committed": tot["committed"],
            "committed_pct": round(tot["committed"] / tot["budget"] * 100, 1) if tot["budget"] else 0.0,
            "spent_pct": round(tot["actual"] / tot["budget"] * 100, 1) if tot["budget"] else 0.0,
            "draw_this_month": round(draw, 2),
            "buyout": budget.get("buyout"),
            "baseline_movement": comp.get("vac_delta"),
        },
    }


def alerts(db: Session, pid: str) -> dict[str, Any]:
    """Predictive schedule alerts from the cost-loaded schedule + CPM (rules first): overdue work,
    late starts, at-risk starts (incomplete predecessor), behind-schedule SPI, and a procurement
    proxy (open submittals with near-term work). Feeds the executive report + a live endpoint."""
    acts = pb._records(db, "schedule_activity", pid)
    today = date.today()
    horizon = today + timedelta(days=21)
    pct_by_key: dict[str, float] = {}
    for r in acts:
        d = r.get("data") or {}
        for k in (r.get("ref"), d.get("wbs")):
            if k:
                pct_by_key[str(k)] = _n(d.get("percent"))

    def _preds(raw: Any) -> list[str]:
        return [t.strip() for t in str(raw or "").replace(";", ",").split(",") if t.strip()]

    out: list[dict[str, Any]] = []
    for r in acts:
        d = r.get("data") or {}
        name = d.get("name") or r.get("ref")
        pct = _n(d.get("percent"))
        s, f = pb._pdate(d.get("start")), pb._pdate(d.get("finish"))
        f = f or s
        is_ms = d.get("activity_type") == "Milestone" or (s and f and s == f)
        if f and f < today and pct < 100:
            out.append({"level": "high", "type": "overdue", "ref": r.get("ref"),
                        "title": f"{'Milestone' if is_ms else 'Activity'} overdue: {name}",
                        "detail": f"due {f.isoformat()}, {pct:.0f}% complete"})
        elif s and s < today and pct == 0:
            out.append({"level": "medium", "type": "late_start", "ref": r.get("ref"),
                        "title": f"Not started: {name}", "detail": f"planned start {s.isoformat()}"})
        if s and today <= s < horizon and pct < 100:
            late = [p for p in _preds(d.get("predecessors")) if pct_by_key.get(p, 100) < 100]
            if late:
                out.append({"level": "high", "type": "predecessor", "ref": r.get("ref"),
                            "title": f"At-risk start: {name}",
                            "detail": f"starts {s.isoformat()} but predecessor(s) {', '.join(late)} incomplete"})

    spi = summary(db, pid)["schedule"]["spi"]
    if spi is not None and spi < 0.95:
        out.append({"level": "high" if spi < 0.85 else "medium", "type": "spi",
                    "title": f"Behind schedule (SPI {spi})", "detail": "earned value trailing planned value"})

    try:
        subs = pb._records(db, "submittal", pid)
        open_subs = [x for x in subs if x.get("workflow_state") not in ("approved", "closed", "void")]
        near = sum(1 for r in acts if (st := pb._pdate((r.get("data") or {}).get("start"))) and today <= st < horizon)
        if open_subs and near:
            out.append({"level": "medium", "type": "procurement",
                        "title": f"Procurement risk: {len(open_subs)} open submittal(s)",
                        "detail": f"{near} activit{'y' if near == 1 else 'ies'} start within 3 weeks"})
    except Exception:  # noqa: BLE001 — submittal module optional
        pass

    order = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda a: order.get(a["level"], 3))
    counts = {lvl: sum(1 for a in out if a["level"] == lvl) for lvl in ("high", "medium", "low")}
    return {"alerts": out, "counts": counts}


def risk_digest(db: Session, pid: str) -> dict[str, Any]:
    """A project risk digest across cost + schedule + open items + safety. Assembles the drivers and
    runs them through ai.risk_summary for a prioritized narrative (Claude when configured, else a
    deterministic rule-based summary)."""
    from . import ai
    s = summary(db, pid)
    al = alerts(db, pid)
    sch, bud = s["schedule"], s["budget"]
    open_items = {}
    closed_states = ("closed", "executed", "approved", "rejected", "answered", "void")
    for key, label in [("rfi", "open_rfis"), ("submittal", "open_submittals"), ("cor", "open_change_orders")]:
        try:
            recs = pb._records(db, key, pid)
            open_items[label] = sum(1 for x in recs if x.get("workflow_state") not in closed_states)
        except Exception:  # noqa: BLE001 — module optional
            open_items[label] = 0
    try:
        incidents = len(pb._records(db, "incident", pid))
    except Exception:  # noqa: BLE001
        incidents = 0
    kpis = {"status": s["status"], "spi": sch["spi"], "pct_complete": sch["pct_complete"],
            "schedule_alerts_high": al["counts"]["high"], "schedule_alerts_medium": al["counts"]["medium"],
            "incidents": incidents, **open_items}
    cost = {"eac": bud["eac"], "variance_at_completion": bud["variance_at_completion"],
            "committed_pct": bud["committed_pct"], "spent_pct": bud["spent_pct"]}
    narrative = ai.risk_summary(kpis, cost)
    return {"headline": narrative.get("headline", ""), "risks": narrative.get("risks", []),
            "source": narrative.get("source"), "ai_enabled": ai.ai_enabled(),
            "drivers": {"schedule": kpis, "cost": cost, "top_alerts": al["alerts"][:8]}}
