"""Quality analytics — inspection pass-rate KPIs, the NCR disposition->corrective-action->close
loop, and the deficiency ball-in-court rollup. Pure read-side aggregation over the inspection / ncr /
deficiency modules; no writes. Mirrors the tm/submittals register engines."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

NCR_CLOSED = ("closed",)
DEF_CLOSED = ("closed",)
# deficiency workflow_state -> whose court the ball is in
DEF_COURT = {"open": "Subcontractor", "corrected": "GC (verify)", "closed": "Closed"}


def _parse(s: Any) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except ValueError:
        return None


def _d(r: dict) -> dict:
    return r.get("data") or r


def inspection_kpis(inspections: list[dict], as_of: date | None = None) -> dict[str, Any]:
    """Pass rate (Pass+Conditional / decided), first-pass yield (clean Pass / decided), by type/result."""
    total = len(inspections)
    by_result, by_type = {}, {}
    passed = failed = conditional = agency = 0
    for i in inspections:
        d = _d(i)
        res = (d.get("result") or "").strip() or "(pending)"
        by_result[res] = by_result.get(res, 0) + 1
        typ = (d.get("inspection_type") or "(unspecified)").strip() or "(unspecified)"
        by_type[typ] = by_type.get(typ, 0) + 1
        if res == "Pass":
            passed += 1
        elif res == "Fail":
            failed += 1
        elif res == "Conditional":
            conditional += 1
        if (d.get("agency") or "").strip():
            agency += 1
    decided = passed + failed + conditional
    pass_rate = round(100 * (passed + conditional) / decided, 1) if decided else None
    fpy = round(100 * passed / decided, 1) if decided else None
    return {
        "total": total, "decided": decided, "pending": total - decided,
        "passed": passed, "failed": failed, "conditional": conditional,
        "pass_rate": pass_rate, "first_pass_yield": fpy, "agency_inspections": agency,
        "by_result": dict(sorted(by_result.items())), "by_type": dict(sorted(by_type.items())),
    }


def ncr_rollup(ncrs: list[dict], as_of: date | None = None) -> dict[str, Any]:
    """NCR disposition->close loop: by state/disposition/severity, overdue, avg days-to-close."""
    today = as_of or date.today()
    by_state, by_disposition, by_severity = {}, {}, {}
    overdue, undispositioned = 0, 0
    days_to_close: list[int] = []
    rows = []
    for n in ncrs:
        d = _d(n)
        st = n.get("workflow_state") or "open"
        by_state[st] = by_state.get(st, 0) + 1
        disp = (d.get("disposition") or "").strip()
        by_disposition[disp or "(undecided)"] = by_disposition.get(disp or "(undecided)", 0) + 1
        if not disp:
            undispositioned += 1
        sev = (d.get("severity") or "(unrated)").strip() or "(unrated)"
        by_severity[sev] = by_severity.get(sev, 0) + 1
        due = _parse(d.get("due_date"))
        is_open = st not in NCR_CLOSED
        is_overdue = bool(due and due < today and is_open)
        if is_overdue:
            overdue += 1
        created = _parse(n.get("created_at"))
        # A module row's timestamp column is `modified_at`; this read `updated_at`, which no module
        # row carries, so `avg_days_to_close` was permanently None. Same typo as rfi.register's
        # turnaround, found with it. (`ncr` declares no refusal state — open/dispositioned/closed —
        # so unlike the RFI register there is nothing here to exclude.)
        closed_at = _parse(n.get("modified_at")) if st in NCR_CLOSED else None
        ttc = (closed_at - created).days if created and closed_at else None
        if ttc is not None and ttc >= 0:
            days_to_close.append(ttc)
        rows.append({
            "ref": n.get("ref"), "subject": d.get("subject"), "state": st,
            "disposition": disp or None, "severity": sev,
            "due_date": d.get("due_date"), "overdue": is_overdue,
            "has_corrective_action": bool((d.get("corrective_action") or "").strip()),
        })
    open_count = sum(v for k, v in by_state.items() if k not in NCR_CLOSED)
    avg_ttc = round(sum(days_to_close) / len(days_to_close), 1) if days_to_close else None
    return {
        "ncr_count": len(rows), "open_count": open_count,
        "closed_count": len(rows) - open_count, "overdue_count": overdue,
        "undispositioned_count": undispositioned, "avg_days_to_close": avg_ttc,
        "by_state": by_state, "by_disposition": dict(sorted(by_disposition.items())),
        "by_severity": dict(sorted(by_severity.items())),
        "rows": sorted(rows, key=lambda r: (not r["overdue"], r.get("ref") or "")),
    }


def deficiency_rollup(defs: list[dict], as_of: date | None = None) -> dict[str, Any]:
    """Deficiency ball-in-court: open=Subcontractor, corrected=GC(verify), closed; by trade/severity."""
    today = as_of or date.today()
    by_state, by_trade, by_severity, ball_in_court = {}, {}, {}, {}
    overdue = 0
    rows = []
    for f in defs:
        d = _d(f)
        st = f.get("workflow_state") or "open"
        by_state[st] = by_state.get(st, 0) + 1
        court = DEF_COURT.get(st, st)
        ball_in_court[court] = ball_in_court.get(court, 0) + 1
        trade = (d.get("trade") or "(unassigned)").strip() or "(unassigned)"
        by_trade[trade] = by_trade.get(trade, 0) + 1
        sev = (d.get("severity") or "(unrated)").strip() or "(unrated)"
        by_severity[sev] = by_severity.get(sev, 0) + 1
        due = _parse(d.get("due_date"))
        is_open = st not in DEF_CLOSED
        is_overdue = bool(due and due < today and is_open)
        if is_overdue:
            overdue += 1
        rows.append({
            "ref": f.get("ref"), "description": d.get("description"), "state": st,
            "ball_in_court": court, "trade": trade, "severity": sev,
            "due_date": d.get("due_date"), "overdue": is_overdue,
        })
    open_count = sum(v for k, v in by_state.items() if k not in DEF_CLOSED)
    return {
        "deficiency_count": len(rows), "open_count": open_count,
        "closed_count": len(rows) - open_count, "overdue_count": overdue,
        "ball_in_court": ball_in_court, "by_state": by_state,
        "by_trade": dict(sorted(by_trade.items())),
        "by_severity": dict(sorted(by_severity.items())),
        "rows": sorted(rows, key=lambda r: (not r["overdue"], r.get("trade") or "", r.get("ref") or "")),
    }


def quality_summary(db, pid: str) -> dict[str, Any]:
    """The combined quality dashboard: inspection KPIs + NCR loop + deficiency ball-in-court."""
    from . import modules as me
    insp = me.list_records(db, "inspection", pid, limit=100000) if "inspection" in me.TABLES else []
    ncrs = me.list_records(db, "ncr", pid, limit=100000) if "ncr" in me.TABLES else []
    defs = me.list_records(db, "deficiency", pid, limit=100000) if "deficiency" in me.TABLES else []
    return {
        "inspections": inspection_kpis(insp),
        "ncrs": ncr_rollup(ncrs),
        "deficiencies": deficiency_rollup(defs),
    }
