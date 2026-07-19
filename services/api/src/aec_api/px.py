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
            "cpi": round(ev / tot["actual"], 2) if tot.get("actual") else None,   # EV(schedule) / AC(cost)
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


def make_ready(db: Session, pid: str, days: int = 14) -> dict[str, Any]:
    """READY-AGENT — the forward make-ready register: every activity starting within `days`, each with
    its preconditions **checked and cited** — incomplete predecessors (by ref + their % complete) and
    open submittals (by ref/title) — and a ready/blocked verdict. The Last Planner question ("can next
    week's work actually start?") answered proactively, with the evidence attached."""
    acts = pb._records(db, "schedule_activity", pid)
    today = date.today()
    horizon = today + timedelta(days=max(1, int(days)))
    pct_by_key: dict[str, float] = {}
    name_by_key: dict[str, str] = {}
    for r in acts:
        d = r.get("data") or {}
        for k in (r.get("ref"), d.get("wbs")):
            if k:
                pct_by_key[str(k)] = _n(d.get("percent"))
                name_by_key[str(k)] = str(d.get("name") or r.get("ref") or k)

    try:
        subs = pb._records(db, "submittal", pid)
        open_subs = [{"ref": x.get("ref"), "title": (x.get("data") or {}).get("title") or x.get("ref"),
                      "state": x.get("workflow_state")}
                     for x in subs if x.get("workflow_state") not in ("approved", "closed", "void")]
    except Exception:  # noqa: BLE001 — submittal module optional
        open_subs = []

    rows: list[dict[str, Any]] = []
    for r in acts:
        d = r.get("data") or {}
        s = pb._pdate(d.get("start"))
        if not s or not (today <= s < horizon) or _n(d.get("percent")) >= 100:
            continue
        blockers: list[dict[str, Any]] = []
        for p_key in [t.strip() for t in str(d.get("predecessors") or "").replace(";", ",").split(",") if t.strip()]:
            pct = pct_by_key.get(p_key)
            if pct is not None and pct < 100:
                blockers.append({"kind": "predecessor", "ref": p_key,
                                 "evidence": f"{name_by_key.get(p_key, p_key)} is {pct:.0f}% complete"})
        if open_subs:
            blockers.append({"kind": "submittals", "count": len(open_subs),
                             "evidence": "open: " + ", ".join(f"{x['ref']} ({x['state']})" for x in open_subs[:5]),
                             "refs": [x["ref"] for x in open_subs[:10]]})
        rows.append({"ref": r.get("ref"), "name": d.get("name") or r.get("ref"),
                     "start": s.isoformat(), "trade": d.get("trade"),
                     "ready": not blockers, "blockers": blockers})
    rows.sort(key=lambda x: (x["ready"], x["start"]))
    return {"window_days": int(days), "activities": rows,
            "ready": sum(1 for x in rows if x["ready"]),
            "blocked": sum(1 for x in rows if not x["ready"]),
            "note": "Make-ready look-ahead: each upcoming start checked against its predecessors' real "
                    "% complete and the open submittal register — evidence cited per blocker."}


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


# acceleration levers are advisory only — a planner must validate against logic ties and resources
_CRASH_FACTOR = 0.25       # indicative time a longer critical task can be shortened by crashing
_FASTTRACK_FACTOR = 0.30   # indicative overlap achievable between two consecutive critical tasks
_NEAR_CRITICAL_DAYS = 5    # total float at/under this = at risk of becoming critical


def optimize(db: Session, pid: str) -> dict[str, Any]:
    """Rule-based schedule-acceleration ADVISORY off the CPM critical path — it never rewrites the
    schedule. Surfaces three levers planners actually use: crash the longest critical activities,
    fast-track consecutive critical activities (overlap them), and watch near-critical activities
    that could swallow the float. Optionally adds an AI narrative; the levers stay deterministic."""
    from . import ai
    acts = pb._records(db, "schedule_activity", pid)
    cpm = schedule_cpm.compute(acts)
    by_id = {a["id"]: a for a in cpm["activities"]}
    pct_by_id: dict[str, float] = {}
    for r in acts:
        pct_by_id[r["id"]] = _n((r.get("data") or {}).get("percent"))

    def _name(a: dict) -> str:
        return a.get("name") or a.get("ref") or a["id"][:8]

    def _open(a: dict) -> bool:
        return pct_by_id.get(a["id"], 0.0) < 100

    critical = [a for a in cpm["activities"] if a["critical"] and _open(a)]

    crash: list[dict[str, Any]] = []
    for a in sorted(critical, key=lambda x: x["duration"], reverse=True):
        if a["duration"] < 2:
            continue
        days = int(round(a["duration"] * _CRASH_FACTOR))
        if days < 1:
            continue
        crash.append({"type": "crash", "ref": a.get("ref"), "name": _name(a),
                      "duration": a["duration"], "days_potential": days,
                      "detail": f"Critical, {a['duration']}d — add crews/shifts to recover up to ~{days}d"})
        if len(crash) >= 6:
            break

    fast_track: list[dict[str, Any]] = []
    for a in critical:
        crit_preds = [by_id[p] for p in a.get("predecessors", []) if p in by_id and by_id[p]["critical"]]
        for p in crit_preds:
            if not _open(p):
                continue
            days = int(round(min(a["duration"], p["duration"]) * _FASTTRACK_FACTOR))
            if days < 1:
                continue
            fast_track.append({"type": "fast_track", "ref": a.get("ref"), "name": _name(a),
                               "predecessor": _name(p), "days_potential": days,
                               "detail": f"Overlap '{_name(a)}' with '{_name(p)}' (fast-track) to save up to ~{days}d"})
    fast_track = fast_track[:6]

    near_critical = [
        {"type": "near_critical", "ref": a.get("ref"), "name": _name(a), "total_float": a["total_float"],
         "detail": f"Only {a['total_float']}d total float — protect it or it joins the critical path"}
        for a in sorted((x for x in cpm["activities"] if _open(x) and 0 < x["total_float"] <= _NEAR_CRITICAL_DAYS),
                        key=lambda x: x["total_float"])[:6]
    ]

    # indicative ceiling: the single best lever (savings aren't additive — each re-baselines the CPM)
    best = max((s["days_potential"] for s in crash + fast_track), default=0)
    levers = len(crash) + len(fast_track)
    if cpm.get("has_cycle"):
        headline = "Schedule has a dependency cycle — fix the logic ties before optimizing."
    elif not critical:
        headline = "No open critical activities to accelerate — schedule has float to spare."
    elif levers:
        headline = (f"{levers} acceleration lever(s) on the {cpm['critical_count']}-activity critical path; "
                    f"the strongest could recover ~{best}d (advisory — validate logic + resources).")
    else:
        headline = "Critical path is short-duration work; little to crash or fast-track."

    out = {"project_duration": cpm.get("project_duration", 0),
           "critical_count": cpm.get("critical_count", 0), "has_cycle": cpm.get("has_cycle", False),
           "headline": headline, "crash": crash, "fast_track": fast_track, "near_critical": near_critical,
           "best_single_lever_days": best, "source": "rules", "ai_enabled": ai.ai_enabled(), "narrative": ""}

    if ai.ai_enabled() and levers:
        res = ai.ask("Give a 2-3 sentence schedule-acceleration recommendation a project scheduler "
                     "could act on this week, based on these CPM levers. Be specific and cautious; "
                     "do not invent activities or numbers beyond the data.",
                     {"critical_path_days": out["project_duration"], "crash": crash,
                      "fast_track": fast_track, "near_critical": near_critical})
        if res.get("source") == "claude" and res.get("answer"):
            out["narrative"] = res["answer"]
            out["source"] = "claude"
    return out
