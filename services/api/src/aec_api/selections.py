"""SELECTIONS (SPRINT D phase-3) — owner selections & allowances rollup.

Each ``selection`` record carries an **allowance** (the $ the contract budgeted for that item) and, once
chosen, an **actual_cost**. The delta (actual − allowance) is the amount that must flow to a change order
and the budget: **over** allowance is an add to the owner, **under** is a credit. This rolls the whole
selections log into that money picture — totals, net over/under, per-category, approval status, and the
list of over-allowance items that are change-order candidates.

Pure over the module records (no I/O beyond the record read), so it unit-tests directly.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

_MAX_CANDIDATES = 200


def _num(v: Any) -> float | None:
    """Parse a currency field (number, or a string like '$1,200.50') to a float, else None."""
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def summary(db: Session, pid: str) -> dict[str, Any]:
    """Roll up the project's ``selection`` records into the allowance-vs-actual money picture."""
    from . import modules as me

    recs = me.list_records(db, "selection", pid, limit=100_000)
    total_allow = total_actual = 0.0
    priced = over = under = at = 0
    by_cat: dict[str, dict] = {}
    candidates: list[dict] = []
    approved = 0
    for r in recs:
        d = r.get("data") or {}
        allow = _num(d.get("allowance"))
        actual = _num(d.get("actual_cost"))
        cat = (d.get("category") or "Other").strip() or "Other"
        if r.get("workflow_state") == "approved":
            approved += 1
        cb = by_cat.setdefault(cat, {"category": cat, "count": 0, "allowance": 0.0, "actual": 0.0, "delta": 0.0})
        cb["count"] += 1
        if allow is not None:
            total_allow += allow
            cb["allowance"] += allow
        if actual is None:
            continue                                  # not yet priced → no delta
        priced += 1
        total_actual += actual
        cb["actual"] += actual
        delta = round(actual - (allow or 0.0), 2)
        cb["delta"] += delta
        if delta > 0.005:
            over += 1
            candidates.append({"ref": r.get("ref"), "item": d.get("item"), "category": cat,
                               "allowance": round(allow or 0.0, 2), "actual": round(actual, 2),
                               "delta": delta, "state": r.get("workflow_state") or "open"})
        elif delta < -0.005:
            under += 1
        else:
            at += 1

    for cb in by_cat.values():
        for k in ("allowance", "actual", "delta"):
            cb[k] = round(cb[k], 2)
    for cnd in candidates:
        cnd["change_subject"] = _co_subject(cnd)      # the idempotency key used by push_to_change_events
    candidates.sort(key=lambda x: -x["delta"])
    net = round(total_actual - total_allow, 2)
    return {
        "count": len(recs), "priced": priced, "approved": approved,
        "total_allowance": round(total_allow, 2), "total_actual": round(total_actual, 2),
        "net_delta": net,
        "direction": "over" if net > 0.005 else "under" if net < -0.005 else "on-allowance",
        "over_count": over, "under_count": under, "on_count": at,
        "by_category": sorted(by_cat.values(), key=lambda c: -abs(c["delta"])),
        "co_candidate_count": len(candidates),
        "co_candidates": candidates[:_MAX_CANDIDATES],
        "note": "Allowance vs. actual across the selections log. Delta = actual − allowance: over is an add "
                "to the owner (a change-order candidate), under is a credit. Priced = selections with an "
                "actual cost entered; approved = owner-signed selections.",
    }


def _co_subject(cnd: dict) -> str:
    """Deterministic change-event subject for a selection overage — also the idempotency key."""
    return f"Allowance overage — {cnd.get('item') or 'selection'} ({cnd.get('ref') or '?'})"


def push_to_change_events(db: Session, pid: str, actor: str | None) -> dict[str, Any]:
    """Create a ``change_event`` (reason 'Allowance Reconciliation') for every over-allowance selection
    that doesn't already have one. Idempotent by the generated subject, so re-running only adds what's
    new. The ROM is the overage (actual − allowance)."""
    from . import modules as me

    cands = summary(db, pid)["co_candidates"]
    existing = {(r.get("data") or {}).get("subject", "") for r in me.list_records(db, "change_event", pid, limit=100_000)}
    created: list[str] = []
    skipped = 0
    for cnd in cands:
        subj = cnd["change_subject"]
        if subj in existing:
            skipped += 1
            continue
        rec = me.create_record(db, "change_event", pid, {"data": {
            "subject": subj, "rom": cnd["delta"], "reason": "Allowance Reconciliation",
            "scope_status": "In Scope"}}, actor, None)
        existing.add(subj)
        created.append(rec.get("ref"))
    return {"created": len(created), "skipped": skipped, "created_refs": created,
            "note": "Over-allowance selections pushed to change events (reason 'Allowance Reconciliation'); "
                    "idempotent — an overage already tracked as a change event is skipped."}
