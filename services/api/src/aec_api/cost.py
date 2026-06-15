"""Cost / financials engine (GC portal): AIA G703 Schedule of Values, G702 Pay Application
certificate, and the Cost Summary roll-up. Reads module records (SOV, commitments, direct
costs) and integrates the change-order chain — executed/approved CORs flow into the contract
sum and revised budget."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import modules as me

DEFAULT_RETAINAGE = 5.0


def _n(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _records(db: Session, key: str, pid: str) -> list[dict]:
    if key not in me.TABLES:
        return []
    return me.list_records(db, key, pid, limit=100000)


def change_order_total(db: Session, pid: str) -> float:
    """Net change by approved/executed Change Order Requests (the change-order chain)."""
    total = 0.0
    for r in _records(db, "cor", pid):
        if r["workflow_state"] in ("approved", "executed"):
            total += _n(r["data"].get("amount"))
    return round(total, 2)


def g703(db: Session, pid: str) -> dict[str, Any]:
    """Schedule of Values register with AIA G703 computed columns."""
    lines = []
    tot = {"scheduled": 0.0, "prev": 0.0, "this": 0.0, "stored": 0.0,
           "completed": 0.0, "balance": 0.0, "retainage": 0.0}
    for r in sorted(_records(db, "sov", pid), key=lambda x: str(x["data"].get("item_no", ""))):
        d = r["data"]
        scheduled = _n(d.get("scheduled_value"))
        prev, this, stored = _n(d.get("completed_prev")), _n(d.get("completed_this")), _n(d.get("materials_stored"))
        completed = prev + this + stored
        ret_pct = _n(d.get("retainage_pct")) or DEFAULT_RETAINAGE
        retainage = round(completed * ret_pct / 100, 2)
        line = {
            "item_no": d.get("item_no"), "description": d.get("description"),
            "cost_code": d.get("cost_code"), "scheduled_value": scheduled,
            "completed_prev": prev, "completed_this": this, "materials_stored": stored,
            "total_completed_stored": round(completed, 2),
            "percent": round(completed / scheduled * 100, 1) if scheduled else 0.0,
            "balance_to_finish": round(scheduled - completed, 2), "retainage": retainage,
        }
        lines.append(line)
        tot["scheduled"] += scheduled; tot["prev"] += prev; tot["this"] += this
        tot["stored"] += stored; tot["completed"] += completed
        tot["balance"] += scheduled - completed; tot["retainage"] += retainage
    tot = {k: round(v, 2) for k, v in tot.items()}
    return {"lines": lines, "totals": tot}


def g702(db: Session, pid: str, app_no: int = 1, period: str | None = None) -> dict[str, Any]:
    """AIA G702 Application & Certificate for Payment (lines 1-9)."""
    sov = g703(db, pid)
    t = sov["totals"]
    original = t["scheduled"]
    co = change_order_total(db, pid)
    contract_to_date = round(original + co, 2)
    completed = t["completed"]
    retainage = t["retainage"]
    earned_less_retainage = round(completed - retainage, 2)
    # previous certificates ≈ prior-period earned less retainage (from "completed_prev")
    prev = t["prev"]
    ret_prev = round(prev * DEFAULT_RETAINAGE / 100, 2)
    previous_certificates = round(prev - ret_prev, 2)
    current_due = round(earned_less_retainage - previous_certificates, 2)
    balance_to_finish = round(contract_to_date - earned_less_retainage, 2)
    return {
        "application_no": app_no, "period": period,
        "line1_original_contract_sum": original,
        "line2_net_change_orders": co,
        "line3_contract_sum_to_date": contract_to_date,
        "line4_total_completed_stored": round(completed, 2),
        "line5_retainage": retainage,
        "line6_total_earned_less_retainage": earned_less_retainage,
        "line7_less_previous_certificates": previous_certificates,
        "line8_current_payment_due": current_due,
        "line9_balance_to_finish_incl_retainage": balance_to_finish,
    }


def summary(db: Session, pid: str) -> dict[str, Any]:
    """Cost Summary roll-up: budget vs committed vs actual vs forecast, with over/under."""
    sov = g703(db, pid)["totals"]
    co = change_order_total(db, pid)
    budget = round(sov["scheduled"] + co, 2)  # revised budget incl approved changes
    committed = round(sum(_n(r["data"].get("amount")) for r in _records(db, "commitment", pid)
                          if r["workflow_state"] in ("executed", "closed")) + co, 2)
    actual = round(
        sum(_n(r["data"].get("amount")) for r in _records(db, "direct_cost", pid))
        + sum(_n(r["data"].get("labor_total")) + _n(r["data"].get("material_total"))
              + _n(r["data"].get("equipment_total"))
              for r in _records(db, "eticket", pid) if r["workflow_state"] in ("gc_signed", "billed")),
        2)
    forecast = round(max(committed, actual), 2)
    return {
        "budget": budget, "committed": committed, "actual": actual, "forecast": forecast,
        "projected_over_under": round(budget - forecast, 2),
        "pct_committed": round(committed / budget * 100, 1) if budget else 0.0,
        "pct_spent": round(actual / budget * 100, 1) if budget else 0.0,
    }
