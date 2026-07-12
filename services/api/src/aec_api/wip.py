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


# --- model-based physical progress (an independent POC method) ---------------------------------------
# Cost-to-cost % complete can mislead: a cost overrun makes a *behind* job look *ahead*, and front-loaded
# billing hides under-production. So we derive a second, physical signal straight from the model —
# **installed model elements ÷ total, by IFC GlobalId** (optionally weighted by an IFC quantity). This is
# the "units-installed" output method (ASC 606 output measure / EVM units-completed), and — because it's
# keyed on GlobalId — it survives re-conversion and ties WIP revenue recognition back to what's actually
# built in the field (the `verification` install-coverage data), not just what's been spent.

# Common IFC base quantities to weight physical progress by (all volumetric/areal — dimensionally
# consistent when a single name is chosen). Callers pass one via `quantity=`.
QUANTITY_HINTS = ("NetVolume", "GrossVolume", "NetArea", "GrossArea", "Length")


def model_progress(db: Session, pid: str, quantity: str | None = None) -> dict[str, Any]:
    """Physical percent-complete from the model: installed elements ÷ total (by IFC GlobalId), optionally
    weighted by an IFC base quantity. Installed = an element whose field-verification status is
    `installed` or `verified`. An independent cross-check on cost-to-cost POC; degrades to
    ``available: False`` when no model is loaded."""
    from sqlalchemy import select

    from . import model_query
    from .models import ElementVerification
    from .routers.properties import _INDEX, _ensure_loaded

    _ensure_loaded(pid)
    idx = _INDEX.get(pid, {})
    total_ct = len(idx)
    if not total_ct:
        return {"available": False,
                "note": "No model loaded — upload a model to derive physical % complete by GlobalId."}
    installed_guids = {g for (g,) in db.execute(
        select(ElementVerification.guid).where(
            ElementVerification.project_id == pid,
            ElementVerification.status.in_(("installed", "verified")))).all()}
    installed_ct = sum(1 for g in idx if g in installed_guids)
    pct_count = round(100 * installed_ct / total_ct, 1)
    out: dict[str, Any] = {
        "available": True, "method": "units-installed",
        "total_elements": total_ct, "installed_elements": installed_ct,
        "percent_complete_count": pct_count, "percent_complete": pct_count,
    }
    if quantity:
        tot_q = ins_q = 0.0
        n_with = 0
        for g, e in idx.items():
            q = model_query._qto_sum(e, quantity)
            if q:
                n_with += 1
                tot_q += q
                if g in installed_guids:
                    ins_q += q
        pct_q = round(100 * ins_q / tot_q, 1) if tot_q else 0.0
        out.update({"quantity": quantity, "elements_with_quantity": n_with,
                    "total_quantity": round(tot_q, 2), "installed_quantity": round(ins_q, 2),
                    "percent_complete_quantity": pct_q})
        if tot_q:                                   # quantity-weighted supersedes the count when present
            out["percent_complete"] = pct_q
    out["note"] = ("Physical progress = installed model elements ÷ total, by IFC GlobalId"
                   + (f", weighted by quantity '{quantity}'." if quantity and out.get("total_quantity")
                      else " (count-weighted)."))
    return out


def schedule(db: Session, pid: str, method: str = "cost-to-cost", with_model: bool = True) -> dict[str, Any]:
    """The project's WIP row: contract, estimated cost, % complete, earned revenue, billed,
    over/under-billing, retainage, gross profit and backlog.

    ``method`` selects the percentage-of-completion driver:
      • ``cost-to-cost`` (default) — cost-to-date ÷ estimated cost (the accounting standard).
      • ``units-installed`` — physical progress from the model (installed elements ÷ total, by GlobalId).
    When a model is loaded, a ``model`` block always reports both percentages and their divergence, so the
    physical signal cross-checks the cost signal regardless of which one drives revenue recognition."""
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

    cost_pct = cost_to_date / estimated_cost if estimated_cost else 0.0
    cost_pct = max(0.0, min(1.0, cost_pct))
    model = model_progress(db, pid) if with_model else {"available": False}

    # choose the POC driver: model-installed physical % when asked and available, else cost-to-cost.
    if method == "units-installed" and model.get("available"):
        pct = max(0.0, min(1.0, model["percent_complete"] / 100.0))
        pct_method = "units-installed"
    else:
        pct = cost_pct
        pct_method = "cost-to-cost"

    earned = round(pct * contract_value, 2)
    over = round(max(0.0, billed - earned), 2)          # liability
    under = round(max(0.0, earned - billed), 2)         # asset
    gross_profit = round(contract_value - estimated_cost, 2)
    result = {
        "contract_value": contract_value, "estimated_cost": round(estimated_cost, 2),
        "cost_to_date": round(cost_to_date, 2), "cost_to_complete": round(max(0.0, estimated_cost - cost_to_date), 2),
        "percent_complete": round(pct * 100, 1), "pct_method": pct_method,
        "earned_revenue": earned, "billed_to_date": billed,
        "over_billing": over, "under_billing": under,
        "billing_status": "over-billed" if over else "under-billed" if under else "even",
        "retainage": retainage,
        "gross_profit": gross_profit,
        "gross_margin_pct": round(gross_profit / contract_value * 100, 1) if contract_value else 0.0,
        "profit_to_date": round(earned - cost_to_date, 2),
        "backlog": round(contract_value - billed, 2),
        "note": f"Percentage-of-completion driven by {pct_method}. Over-billing is a contract liability "
                "(billings in excess of costs & earnings); under-billing is a contract asset (costs & "
                "earnings in excess of billings) and a cash-flow drag. Retainage is tracked separately.",
    }
    if with_model and model.get("available"):
        m_pct = model["percent_complete"]
        c_pct = round(cost_pct * 100, 1)
        diff = round(m_pct - c_pct, 1)
        result["model"] = {
            "model_percent_complete": m_pct, "cost_percent_complete": c_pct, "divergence_pct": diff,
            "installed_elements": model["installed_elements"], "total_elements": model["total_elements"],
            "flag": "cost-ahead" if diff <= -10 else "physical-ahead" if diff >= 10 else "aligned",
            "note": "Physical progress (installed model elements ÷ total, by IFC GlobalId) vs cost-to-cost "
                    "POC. A large gap flags over/under-billing risk or a cost / productivity variance — "
                    "cost running ahead of physical progress is the classic front-loaded-billing signal.",
        }
    return result


_ROW_KEYS = ("contract_value", "estimated_cost", "cost_to_date", "percent_complete", "earned_revenue",
             "billed_to_date", "over_billing", "under_billing", "billing_status", "gross_profit",
             "profit_to_date", "retainage", "backlog")


def portfolio(db: Session) -> dict[str, Any]:
    """WIP across all projects — one row each, worst cash position (largest under-billing) first."""
    rows: list[dict[str, Any]] = []
    tot = {"contract_value": 0.0, "earned_revenue": 0.0, "billed_to_date": 0.0,
           "over_billing": 0.0, "under_billing": 0.0, "gross_profit": 0.0, "retainage": 0.0}
    for p in db.query(Project).all():
        w = schedule(db, p.id, with_model=False)   # skip the per-project model scan in the roll-up
        if not (w["contract_value"] or w["cost_to_date"]):
            continue
        rows.append({"id": p.id, "name": p.name, **{k: w[k] for k in _ROW_KEYS}})
        for k in tot:
            tot[k] = round(tot[k] + w[k], 2)
    rows.sort(key=lambda r: -r["under_billing"])       # biggest cash drag first
    return {"projects": rows, "totals": tot, "project_count": len(rows),
            "note": "Under-billed jobs (contract assets) tie up cash; over-billed jobs (contract "
                    "liabilities) have borrowed against future work. Sorted by under-billing."}
