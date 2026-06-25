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
