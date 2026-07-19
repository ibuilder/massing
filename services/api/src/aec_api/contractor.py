"""Contractor financial statements — the construction-specific lines a generic small-business P&L and
balance sheet miss, derived from the WIP schedule (`wip.py`):

- **Income statement (percentage-of-completion):** revenue = **earned** (not billed), cost of revenue =
  cost-to-date, → gross profit + margin. This is ASC 606 "over time" recognition.
- **Contract position (balance-sheet section):** the two contract accounts plus retainage —
    • **Contract asset**  = under-billings ("Costs & Estimated Earnings in Excess of Billings")
    • **Contract liability** = over-billings ("Billings in Excess of Costs & Estimated Earnings")
    • **Retainage receivable** = retention withheld on the GC's billings
    • **Accounts payable** = unpaid subcontractor invoices
  → working capital contributed by contracts = (contract asset + retainage) − contract liability.

A2 of the resourcing/accounting plan; the balance-sheet twin to the WIP. Portfolio-level too.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import modules as me
from . import wip
from .models import Project


def _n(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _accounts_payable(db: Session, pid: str) -> float:
    """Unpaid subcontractor invoices (approved/submitted but not paid) — a proxy for trade AP.
    A pure filtered SUM, so it aggregates in SQL instead of loading every invoice into Python."""
    if "sub_invoice" not in me.TABLES:
        return 0.0
    return round(me.sum_field(db, "sub_invoice", pid, "amount",
                              exclude_states=["paid", "void"]), 2)


def _statements_from_wip(w: dict[str, Any], ap: float) -> dict[str, Any]:
    revenue = w["earned_revenue"]
    cor = w["cost_to_date"]
    contract_asset = w["under_billing"]
    contract_liability = w["over_billing"]
    retainage = w["retainage"]
    return {
        "income_statement": {
            "revenue_earned": revenue, "cost_of_revenue": cor,
            "gross_profit": round(revenue - cor, 2),
            "gross_margin_pct": round((revenue - cor) / revenue * 100, 1) if revenue else 0.0,
            "basis": "percentage-of-completion (cost-to-cost)",
        },
        "contract_position": {
            "contract_asset_underbillings": contract_asset,
            "contract_liability_overbillings": contract_liability,
            "retainage_receivable": retainage,
            "accounts_payable": ap,
            "net_contract_working_capital": round(contract_asset + retainage - contract_liability - ap, 2),
        },
        "backlog": w["backlog"],
    }


def statements(db: Session, pid: str) -> dict[str, Any]:
    """One project's POC income statement + contract-position balance-sheet section."""
    w = wip.schedule(db, pid)
    out = _statements_from_wip(w, _accounts_payable(db, pid))
    out["contract_value"] = w["contract_value"]
    out["percent_complete"] = w["percent_complete"]
    out["note"] = ("Percentage-of-completion recognizes revenue as it's earned, not billed. The contract "
                   "asset (under-billings) and liability (over-billings) reconcile earned to billed on the "
                   "balance sheet; retainage receivable is carried separately from AR.")
    return out


def portfolio_statements(db: Session, project_ids: set[str] | None = None) -> dict[str, Any]:
    """Company-wide contractor statements — the POC P&L and contract position summed across the
    caller's jobs. `project_ids=None` = no restriction (RBAC off / admin); otherwise tenant-scoped."""
    revenue = cor = asset = liability = retainage = ap = backlog = 0.0
    jobs = 0
    q = db.query(Project)
    if project_ids is not None:
        q = q.filter(Project.id.in_(project_ids))
    for p in q.all():
        w = wip.schedule(db, p.id)
        if not (w["contract_value"] or w["cost_to_date"]):
            continue
        jobs += 1
        revenue += w["earned_revenue"]; cor += w["cost_to_date"]
        asset += w["under_billing"]; liability += w["over_billing"]
        retainage += w["retainage"]; backlog += w["backlog"]
        ap += _accounts_payable(db, p.id)
    gp = round(revenue - cor, 2)
    return {
        "job_count": jobs,
        "income_statement": {
            "revenue_earned": round(revenue, 2), "cost_of_revenue": round(cor, 2),
            "gross_profit": gp, "gross_margin_pct": round(gp / revenue * 100, 1) if revenue else 0.0,
            "basis": "percentage-of-completion (cost-to-cost)",
        },
        "contract_position": {
            "contract_asset_underbillings": round(asset, 2),
            "contract_liability_overbillings": round(liability, 2),
            "retainage_receivable": round(retainage, 2),
            "accounts_payable": round(ap, 2),
            "net_contract_working_capital": round(asset + retainage - liability - ap, 2),
        },
        "backlog": round(backlog, 2),
        "note": "Company-wide percentage-of-completion. Net contract working capital = (under-billings + "
                "retainage) − over-billings − AP; persistently negative signals a cash squeeze even when "
                "profitable.",
    }
