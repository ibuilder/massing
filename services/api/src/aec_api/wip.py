"""Work-in-Progress (WIP) schedule — the defining construction-accounting artifact, and the accounting
twin to the earned-value module. It converts job cost + billing into revenue, contract-asset and
contract-liability figures using **percentage-of-completion (cost-to-cost)**:

    % complete   = cost-to-date ÷ total estimated cost
    earned revenue = % complete × contract value

Comparing **earned** to **billed** yields the two contract positions:
  • over-billing  = billed − earned  → "Billings in Excess of Costs & Estimated Earnings" (a **liability**)
  • under-billing = earned − billed  → "Costs & Estimated Earnings in Excess of Billings" (an **asset**),
    and the #1 cash killer for otherwise-profitable contractors.

Retainage is carried separately (a distinct receivable). Built entirely on `cost.py`
(budget / committed / actual / forecast + the G703 retainage) — no new cost model; contract value comes
from the prime contract + approved change orders (falling back to the SOV). Keyed, like everything, on
cost code.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import cost
from . import modules as me
from .models import Project


def _n(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def schedule(db: Session, pid: str) -> dict[str, Any]:
    """The project's WIP row: contract, estimated cost, % complete (cost-to-cost), earned revenue,
    billed, over/under-billing, retainage, gross profit and backlog."""
    cs = cost.summary(db, pid)
    # total estimated cost at completion = the revised budget (SOV + approved COs); fall back to the
    # committed/actual floor if no budget is set. This is the denominator for cost-to-cost % complete.
    estimated_cost = cs["budget"] or cs["forecast"]
    cost_to_date = cs["actual"]
    co = cost.change_order_total(db, pid)
    # contract value (revenue): the prime contract(s) + approved COs; fall back to the SOV/budget
    pcs = me.list_records(db, "prime_contract", pid, limit=1000) if "prime_contract" in me.TABLES else []
    pc_val = sum(_n((r.get("data") or {}).get("value")) for r in pcs)
    contract_value = round((pc_val + co) if pc_val else cs["budget"], 2)
    # billed to date: owner invoices — SQL SUM, not a 100k-row load into Python (this runs per project
    # in the portfolio roll-up, so the full-table materialization was the worst scale hazard).
    billed = round(me.sum_field(db, "owner_invoice", pid, "amount")
                   if "owner_invoice" in me.TABLES else 0.0, 2)
    retainage = round(cost.g703(db, pid)["totals"].get("retainage", 0.0)
                      or (cost.DEFAULT_RETAINAGE / 100 * billed), 2)

    pct = cost_to_date / estimated_cost if estimated_cost else 0.0
    pct = max(0.0, min(1.0, pct))
    earned = round(pct * contract_value, 2)
    over = round(max(0.0, billed - earned), 2)          # liability
    under = round(max(0.0, earned - billed), 2)         # asset
    gross_profit = round(contract_value - estimated_cost, 2)
    return {
        "contract_value": contract_value, "estimated_cost": round(estimated_cost, 2),
        "cost_to_date": round(cost_to_date, 2), "cost_to_complete": round(max(0.0, estimated_cost - cost_to_date), 2),
        "percent_complete": round(pct * 100, 1),
        "earned_revenue": earned, "billed_to_date": billed,
        "over_billing": over, "under_billing": under,
        "billing_status": "over-billed" if over else "under-billed" if under else "even",
        "retainage": retainage,
        "gross_profit": gross_profit,
        "gross_margin_pct": round(gross_profit / contract_value * 100, 1) if contract_value else 0.0,
        "profit_to_date": round(earned - cost_to_date, 2),
        "backlog": round(contract_value - billed, 2),
        "note": "Percentage-of-completion is cost-to-cost. Over-billing is a contract liability "
                "(billings in excess of costs & earnings); under-billing is a contract asset (costs & "
                "earnings in excess of billings) and a cash-flow drag. Retainage is tracked separately.",
    }


_ROW_KEYS = ("contract_value", "estimated_cost", "cost_to_date", "percent_complete", "earned_revenue",
             "billed_to_date", "over_billing", "under_billing", "billing_status", "gross_profit",
             "profit_to_date", "retainage", "backlog")


def portfolio(db: Session) -> dict[str, Any]:
    """WIP across all projects — one row each, worst cash position (largest under-billing) first."""
    rows: list[dict[str, Any]] = []
    tot = {"contract_value": 0.0, "earned_revenue": 0.0, "billed_to_date": 0.0,
           "over_billing": 0.0, "under_billing": 0.0, "gross_profit": 0.0, "retainage": 0.0}
    for p in db.query(Project).all():
        w = schedule(db, p.id)
        if not (w["contract_value"] or w["cost_to_date"]):
            continue
        rows.append({"id": p.id, "name": p.name, **{k: w[k] for k in _ROW_KEYS}})
        for k in tot:
            tot[k] = round(tot[k] + w[k], 2)
    rows.sort(key=lambda r: -r["under_billing"])       # biggest cash drag first
    return {"projects": rows, "totals": tot, "project_count": len(rows),
            "note": "Under-billed jobs (contract assets) tie up cash; over-billed jobs (contract "
                    "liabilities) have borrowed against future work. Sorted by under-billing."}
