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

from . import cost, money
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
    rows = list(db.execute(select(ElementVerification.guid, ElementVerification.status)
                           .where(ElementVerification.project_id == pid)).all())
    installed_guids = {g for g, st in rows if st in ("installed", "verified")}
    # EVM-COVERAGE, second site. `percent_complete` here is `installed ÷ total` over the WHOLE model,
    # so an element nobody has walked is counted exactly like one inspected and found absent. On a
    # 4,000-element model with 40 verified, this reads 1% — and `schedule(method="units-installed")`
    # multiplies it by the contract value to get EARNED REVENUE, which then drives over-billing, which
    # `accounting.journal_entries` posts back as the WIP-ADJ line. *The EVM instance raises a banner;
    # this one moves a number in a financial statement, and it was found second.*
    #
    # DETERMINED, not merely tracked: a `pending` row is a queued inspection and is not evidence.
    # A `deviation` IS evidence — of something not installed as designed — so it bounds the ceiling.
    deviated_guids = {g for g, st in rows if st == "deviation"} - installed_guids
    determined_guids = (installed_guids | deviated_guids) & set(idx)
    installed_ct = sum(1 for g in idx if g in installed_guids)
    pct_count = round(100 * installed_ct / total_ct, 1)
    # The ceiling: everything except what is known to deviate. See `test_evm_coverage.py` for why
    # this is a bound rather than a coverage threshold — any percentage would have been invented.
    dev_in_model = sum(1 for g in idx if g in deviated_guids)
    pct_count_max = round(100 * max(0, total_ct - dev_in_model) / total_ct, 1)
    out: dict[str, Any] = {
        "available": True, "method": "units-installed",
        "total_elements": total_ct, "installed_elements": installed_ct,
        "determined_elements": len(determined_guids), "deviated_elements": dev_in_model,
        "coverage_pct": round(100 * len(determined_guids) / total_ct, 1),
        "percent_complete_count": pct_count, "percent_complete": pct_count,
        "percent_complete_count_max": pct_count_max, "percent_complete_max": pct_count_max,
        "fully_determined": len(determined_guids) >= total_ct,
    }
    if quantity:
        tot_q = ins_q = undet_q = 0.0
        n_with = 0
        for g, e in idx.items():
            q = model_query._qto_sum(e, quantity)
            if q:
                n_with += 1
                tot_q += q
                if g in installed_guids:
                    ins_q += q
                elif g not in determined_guids:
                    undet_q += q
        pct_q = round(100 * ins_q / tot_q, 1) if tot_q else 0.0
        # The ceiling has to be weighted the SAME WAY as the figure it bounds. A count-weighted
        # ceiling over a quantity-weighted percentage is not a bound at all: one unsurveyed 400 m³
        # pour is 1 element and a quarter of the concrete.
        pct_q_max = round(100 * min(tot_q, ins_q + undet_q) / tot_q, 1) if tot_q else 0.0
        out.update({"quantity": quantity, "elements_with_quantity": n_with,
                    "total_quantity": round(tot_q, 2), "installed_quantity": round(ins_q, 2),
                    "undetermined_quantity": round(undet_q, 2),
                    "percent_complete_quantity": pct_q,
                    "percent_complete_quantity_max": pct_q_max})
        if tot_q:                                   # quantity-weighted supersedes the count when present
            out["percent_complete"] = pct_q
            out["percent_complete_max"] = pct_q_max
    out["note"] = ("Physical progress = installed model elements ÷ total, by IFC GlobalId"
                   + (f", weighted by quantity '{quantity}'." if quantity and out.get("total_quantity")
                      else " (count-weighted).")
                   + ("" if out["fully_determined"] else
                      f" Only {len(determined_guids)} of {total_ct} element(s) have a DETERMINED "
                      f"install status, so physical progress is between {out['percent_complete']}% "
                      f"and {out['percent_complete_max']}% — the rest is unsurveyed, not absent."))
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
    # A REJECTED application is not billed. WIP is the worst place for it to leak: `billed` drives
    # over/under-billing, which `accounting.journal_entries` then posts back as the WIP-ADJ revenue-
    # recognition line, so one refused invoice moves the ledger twice by two different routes.
    from .project_budget import OWNER_INVOICE_NOT_BILLED
    billed = money.q2(me.sum_field(db, "owner_invoice", pid, "amount",
                                   exclude_states=list(OWNER_INVOICE_NOT_BILLED))
                      if "owner_invoice" in me.TABLES else 0.0)
    # MONEY-SCOPE — `or` treated an EXPLICIT 0% retainage as an absent one (cost.py:49 records the
    # same shape under the name FIN-SUITE-BLIND), so a contract the owner agreed to hold nothing on
    # reported 5% of everything billed as retainage held. The comment above says `billed` drives
    # over/under-billing, which posts to the ledger, so an invented figure moves it twice.
    #
    # The condition is COMPLETED WORK, not the mere existence of an SOV: retainage is withheld from
    # what has been earned, so a schedule of values with nothing completed has no basis to state one
    # and the estimate is the only answer available. With work completed, the SOV's figure is
    # authoritative INCLUDING when it is zero. (The first draft of this keyed on `sov["lines"]` and
    # broke `test_wip`, which bills against an SOV that records no progress — an existing test
    # catching a predicate that was right about the defect and too broad about the remedy.)
    sov = cost.g703(db, pid)
    retainage = (money.q2(sov["totals"].get("retainage", 0.0)) if sov["totals"].get("completed")
                 else money.q2(cost.DEFAULT_RETAINAGE / 100 * billed))

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
        m_pct_max = model.get("percent_complete_max", m_pct)
        c_pct = round(cost_pct * 100, 1)
        diff = round(m_pct - c_pct, 1)
        # THE BOUND IS ASYMMETRIC, AND THAT IS THE POINT. Missing survey coverage can only ever
        # DEPRESS the measured physical percentage, so it biases this comparison in one direction:
        #   * `physical-ahead` (m > c) cannot be manufactured by a coverage gap — the gap works
        #     against it — so it keeps the shipped ±10 threshold untouched.
        #   * `cost-ahead` (c > m) is exactly what a gap fabricates, and this block's own note calls
        #     it "the classic front-loaded-billing signal". It must now clear the CEILING.
        # Bounding both would have suppressed a real finding to fix a false one.
        diff_max = round(m_pct_max - c_pct, 1)
        flag = ("cost-ahead" if diff_max <= -10 else "physical-ahead" if diff >= 10 else "aligned")
        result["model"] = {
            "model_percent_complete": m_pct, "cost_percent_complete": c_pct, "divergence_pct": diff,
            "model_percent_complete_max": m_pct_max, "divergence_pct_max": diff_max,
            "installed_elements": model["installed_elements"], "total_elements": model["total_elements"],
            "determined_elements": model.get("determined_elements"),
            "coverage_pct": model.get("coverage_pct"),
            "fully_determined": model.get("fully_determined", True),
            "flag": flag,
            "note": "Physical progress (installed model elements ÷ total, by IFC GlobalId) vs cost-to-cost "
                    "POC. A large gap flags over/under-billing risk or a cost / productivity variance — "
                    "cost running ahead of physical progress is the classic front-loaded-billing signal, "
                    "which is why `cost-ahead` must clear the ceiling an incomplete survey allows while "
                    "`physical-ahead` need not: unsurveyed elements only ever lower the physical figure."
                    + ("" if model.get("fully_determined", True) else
                       f" Coverage is partial — physical progress is between {m_pct}% and {m_pct_max}%."),
        }
        # WHEN THE PARTIAL FIGURE IS DRIVING REVENUE, SAY SO ON THE WIP ROW ITSELF, not only in the
        # cross-check block a reader may never open. `earned_revenue` is deliberately NOT changed
        # here: which end of the band a percentage-of-completion schedule should recognise is a
        # revenue-recognition policy question for the project's accountant, not something to pick in
        # an engine. What was wrong was that nothing said a band existed.
        if pct_method == "units-installed" and not model.get("fully_determined", True):
            result["percent_complete_max"] = m_pct_max
            result["earned_revenue_max"] = round(min(1.0, m_pct_max / 100.0) * contract_value, 2)
            result["poc_coverage_partial"] = True
            result["note"] += (
                f" POC IS DRIVEN BY A PARTIAL SURVEY: {model.get('determined_elements')} of "
                f"{model['total_elements']} element(s) have a determined install status, so physical "
                f"progress is between {m_pct}% and {m_pct_max}% and earned revenue between "
                f"{result['earned_revenue']} and {result['earned_revenue_max']}. The figure recognised "
                "here is the lower bound; which end a WIP schedule should recognise is an accounting "
                "policy decision.")
    return result


_ROW_KEYS = ("contract_value", "estimated_cost", "cost_to_date", "percent_complete", "earned_revenue",
             "billed_to_date", "over_billing", "under_billing", "billing_status", "gross_profit",
             "profit_to_date", "retainage", "backlog")


def portfolio(db: Session, project_ids: set[str] | None = None) -> dict[str, Any]:
    """WIP across the caller's projects — one row each, worst cash position (largest under-billing)
    first. `project_ids=None` = no restriction (RBAC off / admin); otherwise tenant-scoped."""
    rows: list[dict[str, Any]] = []
    tot = {"contract_value": 0.0, "earned_revenue": 0.0, "billed_to_date": 0.0,
           "over_billing": 0.0, "under_billing": 0.0, "gross_profit": 0.0, "retainage": 0.0}
    q = db.query(Project)
    if project_ids is not None:
        q = q.filter(Project.id.in_(project_ids))
    for p in q.all():
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
