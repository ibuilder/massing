"""SCOPE-REG (R17 Sprint D) — a first-class **scope register** that ties the things we already hold
*separately* into one spine: a scope item → **quantify** (its QTO/CBS quantity + value) → **allocate** (a
responsible party / buyout package) → **schedule** (the activity that builds it).

Its value is the **gap analysis**: which scope is unquantified, which is unallocated (nobody owns it), which
is unscheduled — the holes that sink a job. Deterministic over the scope items + QTO lines + activities the
caller supplies; links resolve by cost code (the CBS key) or an explicit activity id.
"""
from __future__ import annotations

from datetime import date
from typing import Any


def _num(v: Any) -> float:
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def register(scope_items: list[dict], qto_lines: list[dict] | None = None,
             activities: list[dict] | None = None) -> dict[str, Any]:
    """Resolve each scope item's quantity/value (from QTO by cost code), owner, and schedule window → the
    register + a gap analysis (unquantified / unallocated / unscheduled)."""
    # index QTO value + qty by cost code
    qto_by_code: dict[str, dict] = {}
    for ln in qto_lines or []:
        cc = _norm(ln.get("cost_code"))
        if not cc:
            continue
        g = qto_by_code.setdefault(cc, {"qty": 0.0, "value": 0.0, "lines": 0})
        g["qty"] += _num(ln.get("qty"))
        g["value"] += _num(ln.get("cost")) or _num(ln.get("qty")) * _num(ln.get("unit_price"))
        g["lines"] += 1

    # index activity window by id and (earliest start / latest finish) by cost code
    act_by_id: dict[str, dict] = {}
    win_by_code: dict[str, dict] = {}
    for a in activities or []:
        s, f = _date(a.get("start") or a.get("planned_start")), _date(a.get("finish") or a.get("planned_finish"))
        rec = {"start": s.isoformat() if s else None, "finish": f.isoformat() if f else None,
               "name": a.get("name")}
        aid = str(a.get("id") or a.get("activity_id") or "")
        if aid:
            act_by_id[aid] = rec
        cc = _norm(a.get("cost_code"))
        if cc and (s or f):
            w = win_by_code.setdefault(cc, {"start": s, "finish": f})
            if s and (w["start"] is None or s < w["start"]):
                w["start"] = s
            if f and (w["finish"] is None or f > w["finish"]):
                w["finish"] = f

    rows = []
    n_quant = n_alloc = n_sched = complete = 0
    total_value = 0.0
    by_owner: dict[str, float] = {}
    for it in scope_items or []:
        if not isinstance(it, dict):
            continue
        cc = _norm(it.get("cost_code"))
        q = qto_by_code.get(cc)
        qty = _num(it.get("qty")) or (q["qty"] if q else 0.0)
        value = _num(it.get("value")) or _num(it.get("cost")) or (q["value"] if q else 0.0)
        quantified = bool(q) or qty > 0 or value > 0
        owner = it.get("responsible") or it.get("owner") or ""
        package = it.get("package") or ""
        allocated = bool(owner or package)
        aid = str(it.get("activity_id") or "")
        act = act_by_id.get(aid)
        win = win_by_code.get(cc)
        start = (act or {}).get("start") or (win["start"].isoformat() if win and win.get("start") else None)
        finish = (act or {}).get("finish") or (win["finish"].isoformat() if win and win.get("finish") else None)
        scheduled = bool(start or finish)

        gaps = []
        if not quantified:
            gaps.append("unquantified")
        if not allocated:
            gaps.append("unallocated")
        if not scheduled:
            gaps.append("unscheduled")
        status = "complete" if not gaps else "gap"

        n_quant += quantified
        n_alloc += allocated
        n_sched += scheduled
        complete += status == "complete"
        total_value += value
        if owner or package:
            by_owner[owner or package] = by_owner.get(owner or package, 0.0) + value

        rows.append({
            "id": it.get("id"), "name": it.get("name") or it.get("scope") or "",
            "cost_code": it.get("cost_code"), "qty": round(qty, 2) or None, "value": round(value, 2) or None,
            "responsible": owner or None, "package": package or None,
            "start": start, "finish": finish,
            "quantified": quantified, "allocated": allocated, "scheduled": scheduled,
            "gaps": gaps, "status": status,
        })

    n = len(rows)
    rows.sort(key=lambda r: (r["status"] == "complete", -(r["value"] or 0)))   # gaps first, highest-value first
    return {
        "item_count": n, "complete": complete, "with_gaps": n - complete,
        "pct_quantified": round(n_quant / n, 3) if n else 0.0,
        "pct_allocated": round(n_alloc / n, 3) if n else 0.0,
        "pct_scheduled": round(n_sched / n, 3) if n else 0.0,
        "total_value": round(total_value, 2),
        "by_owner": sorted(({"owner": k, "value": round(v, 2)} for k, v in by_owner.items()),
                           key=lambda r: -r["value"]),
        "gap_items": [r for r in rows if r["gaps"]],
        "items": rows,
        "note": "Scope register: each item resolves its quantity/value (QTO by cost code), owner (responsible/"
                "package), and schedule window (activity by id or cost code). Gap analysis surfaces "
                "unquantified / unallocated / unscheduled scope — gaps first, highest-value first — the "
                "connective spine across QTO · CBS · responsibility · schedule.",
    }
