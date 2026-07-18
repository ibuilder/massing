"""Cross-project benchmarking — turn your own historical records into portfolio intelligence.

The report finds 80% of leaders say historical data is critical yet 76% aren't realizing its potential.
This mines records ACROSS all projects (not one) into two things teams actually ask for:
  1. Cost benchmarks — the distribution (low / p25 / median / p75 / high) of actual costs per cost code,
     from `direct_cost`, so a new estimate can be sanity-checked against what things really cost you.
  2. Response-rate KPIs — RFI and submittal turnaround + overdue %, the ball-in-court accountability
     metric competitors (Jet.build) sell, computed from the records you already keep.

Deterministic, no AI, no external data — your data, aggregated. Percentiles need the full distribution,
so the cost query loads the relevant rows (an analytics endpoint, not a hot path)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import modules as me


def _rows(db: Session, key: str, project_ids: set[str] | None = None) -> list[dict]:
    """Every record of a module across the caller's projects, as {data, created_at, modified_at, state}.
    `project_ids=None` means no restriction (RBAC off / admin); otherwise the roll-up is tenant-scoped so
    portfolio aggregations never leak other tenants' data (see rbac.member_project_ids)."""
    t = me.TABLES.get(key)
    if t is None:
        return []
    stmt = select(t.c.data, t.c.created_at, t.c.modified_at, t.c.workflow_state)
    if project_ids is not None:
        stmt = stmt.where(t.c.project_id.in_(project_ids))
    out = []
    for data, created, modified, state in db.execute(stmt).all():
        out.append({"data": data or {}, "created_at": created, "modified_at": modified, "state": state})
    return out


def _num(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _pctile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolated percentile (q in 0..1)."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    frac = pos - lo
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def cost_benchmarks(db: Session, min_samples: int = 3,
                    project_ids: set[str] | None = None) -> dict:
    """Distribution of actual `direct_cost` amounts per cost code, across the caller's projects."""
    by_code: dict[str, list[float]] = {}
    for r in _rows(db, "direct_cost", project_ids):
        d = r["data"]
        code = (d.get("cost_code") or "").strip() or "(uncoded)"
        amt = _num(d.get("amount"))
        if amt is not None and amt > 0:
            by_code.setdefault(code, []).append(amt)
    codes = []
    for code, vals in by_code.items():
        if len(vals) < min_samples:
            continue
        s = sorted(vals)
        codes.append({
            "cost_code": code, "samples": len(s),
            "low": round(s[0], 2), "p25": round(_pctile(s, 0.25), 2),
            "median": round(_pctile(s, 0.5), 2), "p75": round(_pctile(s, 0.75), 2),
            "high": round(s[-1], 2), "total": round(sum(s), 2)})
    codes.sort(key=lambda c: -c["total"])
    dropped = sum(1 for v in by_code.values() if len(v) < min_samples)
    return {"cost_codes": codes, "code_count": len(codes),
            "min_samples": min_samples, "codes_below_threshold": dropped,
            "message": (None if codes else
                        f"Not enough history yet — need ≥{min_samples} posted direct costs per cost "
                        "code across your projects to benchmark.")}


def pull_planning(db: Session, min_committed: int = 3,
                  project_ids: set[str] | None = None) -> dict:
    """Pull-planning reliability across the caller's projects: the distribution of PPC and Tasks-Made-
    Ready % per project, so a team can see where a plan sits against its own portfolio and the ≥80%
    target."""
    t = me.TABLES.get("pull_plan_task")
    if t is None:
        return {"projects": 0, "message": "No pull-plan data yet."}
    ready_states = {"made_ready", "committed", "done", "not_done"}
    per_proj: dict[str, dict] = {}
    stmt = select(t.c.project_id, t.c.workflow_state)
    if project_ids is not None:
        stmt = stmt.where(t.c.project_id.in_(project_ids))
    for pid_, state in db.execute(stmt).all():
        p = per_proj.setdefault(pid_, {"total": 0, "ready": 0, "done": 0, "not_done": 0})
        p["total"] += 1
        if state in ready_states:
            p["ready"] += 1
        if state == "done":
            p["done"] += 1
        elif state == "not_done":
            p["not_done"] += 1
    rows, ppcs, tmrs = [], [], []
    for pid_, p in per_proj.items():
        committed = p["done"] + p["not_done"]
        if committed < min_committed:
            continue
        ppc = round(p["done"] / committed * 100, 1)
        tmr = round(p["ready"] / p["total"] * 100, 1) if p["total"] else 0.0
        ppcs.append(ppc); tmrs.append(tmr)
        rows.append({"project_id": pid_, "ppc_pct": ppc, "tmr_pct": tmr, "committed": committed})

    def dist(vals: list[float]) -> dict:
        s = sorted(vals)
        return {"low": round(s[0], 1), "median": round(_pctile(s, 0.5), 1),
                "high": round(s[-1], 1), "avg": round(sum(s) / len(s), 1)} if s else {}
    rows.sort(key=lambda r: -r["ppc_pct"])
    return {"projects": len(rows), "target_ppc": 80.0,
            "ppc": dist(ppcs), "tmr": dist(tmrs), "per_project": rows,
            "message": (None if rows else
                        f"Not enough history yet — need ≥{min_committed} committed pull-plan tasks per "
                        "project to benchmark reliability.")}


def _age_days(a, b) -> float | None:
    """Whole days between two datetimes/date-strings (b - a), or None."""
    da, dbb = _to_date(a), _to_date(b)
    if da and dbb:
        return (dbb - da).days
    return None


def _to_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v[:10]).date()
        except ValueError:
            return None
    return None


_RFI_DONE = {"answered", "closed"}


def response_rates(db: Session, project_ids: set[str] | None = None) -> dict:
    """RFI + submittal turnaround and overdue %, across the caller's projects (ball-in-court
    accountability)."""
    today = datetime.now(timezone.utc).date()

    # RFI: turnaround = created -> last transition (modified) once answered/closed; overdue = past
    # due_date and still open.
    rfis = _rows(db, "rfi", project_ids)
    rfi_turn = [t for t in (_age_days(r["created_at"], r["modified_at"]) for r in rfis
                            if r["state"] in _RFI_DONE) if t is not None and t >= 0]
    rfi_open = [r for r in rfis if r["state"] not in _RFI_DONE and r["state"] != "void"]
    rfi_overdue = sum(1 for r in rfi_open
                      if (dd := _to_date(r["data"].get("due_date"))) and dd < today)
    rfi = {
        "total": len(rfis), "open": len(rfi_open),
        "answered_or_closed": sum(1 for r in rfis if r["state"] in _RFI_DONE),
        "avg_turnaround_days": round(sum(rfi_turn) / len(rfi_turn), 1) if rfi_turn else None,
        "overdue": rfi_overdue,
        "overdue_pct": round(rfi_overdue / len(rfi_open) * 100, 1) if rfi_open else 0.0,
    }

    # Submittal: turnaround = date_received -> date_returned (fields); overdue = required_on_site
    # passed and not yet returned.
    subs = _rows(db, "submittal", project_ids)
    sub_turn = [t for t in (_age_days(s["data"].get("date_received"), s["data"].get("date_returned"))
                            for s in subs) if t is not None and t >= 0]
    sub_open = [s for s in subs if not s["data"].get("date_returned")]
    sub_overdue = sum(1 for s in sub_open
                      if (rq := _to_date(s["data"].get("required_on_site"))) and rq < today)
    sub = {
        "total": len(subs), "open": len(sub_open),
        "returned": sum(1 for s in subs if s["data"].get("date_returned")),
        "avg_turnaround_days": round(sum(sub_turn) / len(sub_turn), 1) if sub_turn else None,
        "overdue": sub_overdue,
        "overdue_pct": round(sub_overdue / len(sub_open) * 100, 1) if sub_open else 0.0,
    }
    return {"rfi": rfi, "submittal": sub}
