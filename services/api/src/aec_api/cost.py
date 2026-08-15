"""Cost / financials engine (GC portal): AIA G703 Schedule of Values, G702 Pay Application
certificate, and the Cost Summary roll-up. Reads module records (SOV, commitments, direct
costs) and integrates the change-order chain — executed/approved CORs flow into the contract
sum and revised budget."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import modules as me
from . import money

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
           "completed": 0.0, "balance": 0.0, "retainage": 0.0, "retainage_prev": 0.0}
    for r in sorted(_records(db, "sov", pid), key=lambda x: str(x["data"].get("item_no", ""))):
        d = r["data"]
        scheduled = _n(d.get("scheduled_value"))
        prev, this, stored = _n(d.get("completed_prev")), _n(d.get("completed_this")), _n(d.get("materials_stored"))
        completed = prev + this + stored
        # FIN-SUITE-BLIND: `or DEFAULT_RETAINAGE` treated an EXPLICIT 0% as unset, so a line the owner
        # had agreed to hold nothing on — stored materials, a released line, a fully-bonded sub — had
        # the 5% default withheld anyway. $1,000 wrongly held on a $20,000 line, and the contractor is
        # underpaid by a number that looks entirely plausible on the certificate.
        #
        # Zero is a VALUE here, not an absence. Found the first time a fixture used a 0% rate; every
        # prior test used the default, where the bug is invisible because the fallback and the real
        # value coincide.
        # v0.3.969 — was `round(completed * ret_pct / 100, 2)` on binary floats. `round()` is
        # ROUND_HALF_EVEN, so it disagreed with `payapp`'s HALF-UP by a penny on 4 of 5 sampled
        # cases (2.50 @ 5% -> 0.12 here, 0.13 there). Two conventions inside one G702, and a pay
        # application out by a penny is rejected.
        raw_pct = d.get("retainage_pct")
        ret_pct = money.rate(raw_pct)
        retainage = money.retainage(completed, ret_pct)
        # MOD-G702: the same line's retainage on the PREVIOUS period alone. G702 line 7 needs it, and
        # computing it there from the global default while line 5 used the per-line rate is what made
        # a 10%-retainage contract report a negative payment due.
        retainage_prev = money.retainage(prev, ret_pct)
        line = {
            "item_no": d.get("item_no"), "description": d.get("description"),
            "cost_code": d.get("cost_code"), "scheduled_value": scheduled,
            "completed_prev": prev, "completed_this": this, "materials_stored": stored,
            "total_completed_stored": round(completed, 2),
            "percent": round(completed / scheduled * 100, 1) if scheduled else 0.0,
            "balance_to_finish": round(scheduled - completed, 2), "retainage": retainage,
            "retainage_prev": retainage_prev,
        }
        lines.append(line)
        tot["scheduled"] += scheduled; tot["prev"] += prev; tot["this"] += this
        tot["stored"] += stored; tot["completed"] += completed
        tot["balance"] += scheduled - completed; tot["retainage"] += retainage
        tot["retainage_prev"] += retainage_prev
    tot = {k: round(v, 2) for k, v in tot.items()}
    return {"lines": lines, "totals": tot}


def g702(db: Session, pid: str, app_no: int = 1, period: str | None = None,
         release_retainage: bool = False, previous_certificates: float | None = None) -> dict[str, Any]:
    """AIA G702 Application & Certificate for Payment (lines 1-9). `release_retainage` (final app):
    the previously-held retainage is released — retainage held → 0 and the held amount becomes due."""
    sov = g703(db, pid)
    t = sov["totals"]
    original = t["scheduled"]
    co = change_order_total(db, pid)
    contract_to_date = round(original + co, 2)
    completed = t["completed"]
    retainage = 0.0 if release_retainage else t["retainage"]
    earned_less_retainage = round(completed - retainage, 2)
    # Line 7, "less previous certificates for payment". Derived from `completed_prev` because until
    # MOD-G702 no application was ever STORED — there was no prior certificate to read, only a
    # reconstruction of one. It is now a fallback: `previous_certificates` is passed in when a
    # submitted `owner_invoice` exists, and that is a fact rather than an approximation.
    #
    # The retainage here is summed PER LINE, matching line 5. It used to apply DEFAULT_RETAINAGE to
    # the aggregate, so any line overriding the rate made lines 7 and 5 disagree — on a 10% contract
    # with $50k completed and nothing this period, line 8 came out at MINUS $2,500. `closeout.py`
    # reads line 8 for the final-payment amount, so the number had a consumer.
    prev = t["prev"]
    if previous_certificates is None:
        previous_certificates = round(prev - t["retainage_prev"], 2)
    current_due = round(earned_less_retainage - previous_certificates, 2)
    balance_to_finish = round(contract_to_date - earned_less_retainage, 2)
    return {
        "application_no": app_no, "period": period, "retainage_released": release_retainage,
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


def _certified_to_date(db: Session, pid: str) -> float | None:
    """MOD-G702 — what previous applications actually certified, or None if none has been submitted.

    Line 7 of a G702 is "less previous certificates for payment", and the AIA form tells you where to
    get it: *line 6 from the prior certificate*. It is a historical fact, not a recomputation. This
    codebase had no stored application, so it reconstructed the figure from the SOV's `completed_prev`
    — which is only equal to the truth while nothing about the earlier periods has changed. Edit a
    retainage rate, correct a scheduled value, or approve a change order that restates an earlier
    line, and the reconstruction moves. The certificate does not: it was signed.

    `architect_certified_amount` wins over line 8 when present, because the architect may certify less
    than was applied for, and what was actually certified is what a later application must deduct.
    """
    best = None
    for r in _records(db, "owner_invoice", pid):
        if r.get("workflow_state") not in ("submitted", "approved", "paid"):
            continue                       # a draft has certified nothing
        d = r.get("data") or {}
        amt = d.get("architect_certified_amount")
        if amt in (None, ""):
            amt = d.get("current_payment_due")
        prior = _n(d.get("previous_certificates"))
        # cumulative-to-date = what this application deducted, plus what it added
        tot = round(prior + _n(amt), 2)
        if best is None or tot > best:
            best = tot
    return best


def build_application(db: Session, pid: str, app_no: int | None = None, period: str | None = None,
                      period_from: str | None = None, period_to: str | None = None,
                      release_retainage: bool = False, actor: str = "system") -> dict[str, Any]:
    """MOD-G702 — snapshot the live SOV into an `owner_invoice` record: an application, not a view.

    A pay application is a CLAIM MADE ON A DATE. Everything that fed it — the schedule of values, the
    change orders, the retainage rates — keeps moving afterwards, so a "current" G702 assembled on
    demand silently restates applications that have already been signed and paid. That is the same
    defect shape as MOD-TOTALS, where re-pricing a rate library would have changed what was already
    owed: the fix there and here is to freeze the numbers into the document at the moment it is made.

    Draft, deliberately. This produces the record; submitting and certifying it are workflow
    transitions a person performs, because a certificate nobody signed is not a certificate.
    """
    sheet = g703(db, pid)
    if app_no is None:
        app_no = 1 + len(_records(db, "owner_invoice", pid))
    cert = g702(db, pid, app_no=app_no, period=period, release_retainage=release_retainage,
                previous_certificates=_certified_to_date(db, pid))
    data = {
        "number": str(app_no), "period": period or "", "period_from": period_from or "",
        "period_to": period_to or "",
        "line_items": sheet["lines"],
        "original_contract_sum": cert["line1_original_contract_sum"],
        "net_change_orders": cert["line2_net_change_orders"],
        "contract_sum_to_date": cert["line3_contract_sum_to_date"],
        "amount": cert["line4_total_completed_stored"],
        "retainage_total": cert["line5_retainage"],
        "earned_less_retainage": cert["line6_total_earned_less_retainage"],
        "previous_certificates": cert["line7_less_previous_certificates"],
        "current_payment_due": cert["line8_current_payment_due"],
        "balance_to_finish": cert["line9_balance_to_finish_incl_retainage"],
        "sov_snapshot_at": _now_date(),
        "status": "draft",
    }
    return me.create_record(db, "owner_invoice", pid, {"data": data}, actor, "GC")


def _now_date() -> str:
    from .timeutil import utc_today
    return utc_today().isoformat()


def advance_period(db: Session, pid: str, actor: str = "system") -> dict[str, Any]:
    """Multi-period roll-forward (C1): close the current pay period — each SOV line's completed-this
    rolls into completed-previous so the next application starts fresh, the way successive AIA pay
    apps accumulate. Returns the count of lines advanced."""
    from . import modules as me
    n = 0
    for r in _records(db, "sov", pid):
        d = r["data"]
        this = _n(d.get("completed_this"))
        if this:
            new_prev = round(_n(d.get("completed_prev")) + this, 2)
            me.update_record(db, "sov", pid, r["id"],
                             {"completed_prev": new_prev, "completed_this": 0}, actor, "GC")
            n += 1
    return {"lines_advanced": n}


# Lien waiver / release forms (C1). The four statutory progress/final × conditional/unconditional
# variants (Cal. Civ. Code §8132–8138 style, the de-facto national template). A *conditional* waiver
# is effective only once payment clears; an *unconditional* waiver releases on signing — so it must
# only be signed after funds are in hand. Bodies are the standard statutory language (public form).
LIEN_WAIVER_KINDS = ("conditional_progress", "unconditional_progress",
                     "conditional_final", "unconditional_final")
_LIEN_TITLES = {
    "conditional_progress": "Conditional Waiver and Release on Progress Payment",
    "unconditional_progress": "Unconditional Waiver and Release on Progress Payment",
    "conditional_final": "Conditional Waiver and Release on Final Payment",
    "unconditional_final": "Unconditional Waiver and Release on Final Payment",
}
_LIEN_NOTICE = {
    "conditional_progress": "This document waives the claimant's lien, stop payment notice, and "
        "payment bond rights effective on receipt of payment. A person should not rely on this "
        "document unless satisfied that the claimant has received payment.",
    "unconditional_progress": "This document waives and releases lien, stop payment notice, and "
        "payment bond rights unconditionally and states that you have been paid for giving up those "
        "rights. This document is enforceable against you if you sign it, even if you have not been "
        "paid. If you have not been paid, use a conditional waiver and release form.",
    "conditional_final": "This document waives the claimant's lien, stop payment notice, and payment "
        "bond rights effective on receipt of payment. A person should not rely on this document "
        "unless satisfied that the claimant has received payment.",
    "unconditional_final": "This document waives and releases lien, stop payment notice, and payment "
        "bond rights unconditionally and states that you have been paid for giving up those rights. "
        "This document is enforceable against you if you sign it, even if you have not been paid. If "
        "you have not been paid, use a conditional waiver and release form.",
}


def lien_waiver(db: Session, pid: str, kind: str = "conditional_progress", app_no: int = 1,
                claimant: str = "", customer: str = "", project_name: str = "",
                through_date: str = "", amount: float | None = None) -> dict[str, Any]:
    """Generate a statutory lien waiver / release to accompany a pay application (C1). `kind` is one
    of LIEN_WAIVER_KINDS. The waived amount defaults to the pay app's current payment due (progress)
    or the full contract sum to date (final). Returns the form fields + body for rendering/PDF."""
    if kind not in LIEN_WAIVER_KINDS:
        raise ValueError(f"unknown lien-waiver kind {kind!r}; have {LIEN_WAIVER_KINDS}")
    g7 = g702(db, pid, app_no, release_retainage=kind.endswith("final"))
    final = kind.endswith("final")
    amt = round(amount if amount is not None else
                (g7["line3_contract_sum_to_date"] if final else g7["line8_current_payment_due"]), 2)
    conditional = kind.startswith("conditional")
    if conditional:
        body = (f"Upon receipt by the undersigned of a check from {customer or '[Customer]'} in the "
                f"sum of ${amt:,.2f} payable to {claimant or '[Claimant]'}, and when the check has "
                "been properly endorsed and has been paid by the bank on which it is drawn, this "
                "document becomes effective to release and the undersigned releases " +
                ("any" if final else "any progress payment") +
                " mechanics lien, stop payment notice, or payment bond rights the undersigned has on "
                f"the job of {customer or '[Owner]'} located at {project_name or '[Project]'} "
                + ("." if final else f" to the following extent: this release covers a progress "
                   f"payment for all labor, services, equipment, or material furnished through "
                   f"{through_date or '[date]'}.")
                + (" This release covers the final payment to the claimant for all labor, services, "
                   "equipment, or material furnished on the project." if final else ""))
    else:
        body = (f"The undersigned has been paid in full for all labor, services, equipment, or "
                f"material furnished to {customer or '[Customer]'} on the job of {customer or '[Owner]'} "
                f"located at {project_name or '[Project]'} " +
                ("and does hereby waive and release any mechanics lien, stop payment notice, or "
                 "payment bond rights the undersigned has on the above referenced project."
                 if final else
                 f"to the following extent: this release covers a progress payment for all labor, "
                 f"services, equipment, or material furnished through {through_date or '[date]'} in "
                 f"the amount of ${amt:,.2f}, and does hereby waive and release any mechanics lien, "
                 f"stop payment notice, or payment bond rights the undersigned has to this extent."))
    return {
        "kind": kind, "title": _LIEN_TITLES[kind], "conditional": conditional, "final": final,
        "claimant": claimant, "customer": customer, "project_name": project_name,
        "through_date": through_date, "amount": amt, "application_no": app_no,
        "notice": _LIEN_NOTICE[kind], "body": body,
        "exceptions": "Disputed claims and items not included above are excepted from this release.",
        "signature_block": {"claimant_title": "Claimant's Title", "date": "Date of Signature"},
    }


_RATE_LOOKUP = {  # tm line type -> (rate module, name field)
    "labor": ("labor_rate", "trade"),
    "material": ("material_rate", "material"),
    "equipment": ("equipment_rate", "equipment"),
}


def _rate_for(db: Session, pid: str, line_type: str, name: str) -> float:
    mod, name_field = _RATE_LOOKUP.get(line_type, (None, None))
    if not mod or mod not in me.TABLES:
        return 0.0
    for r in _records(db, mod, pid):
        if str(r["data"].get(name_field, "")).lower() == str(name).lower():
            return _n(r["data"].get("rate"))
    return 0.0


def price_tm(db: Session, pid: str, lines: list[dict]) -> dict[str, Any]:
    """eTicket T&M builder: price each line from the project rate tables (or an explicit
    rate), compute per-type subtotals and a grand total."""
    priced = []
    subtotals = {"labor": 0.0, "material": 0.0, "equipment": 0.0}
    for ln in lines:
        lt = (ln.get("type") or "labor").lower()
        qty = _n(ln.get("qty"))
        rate = _n(ln.get("rate")) or _rate_for(db, pid, lt, ln.get("name", ""))
        amount = round(rate * qty, 2)
        subtotals[lt] = subtotals.get(lt, 0.0) + amount
        priced.append({"type": lt, "name": ln.get("name"), "qty": qty,
                       "rate": rate, "amount": amount})
    subtotals = {k: round(v, 2) for k, v in subtotals.items()}
    grand = round(sum(subtotals.values()), 2)
    return {"lines": priced, "labor_total": subtotals.get("labor", 0.0),
            "material_total": subtotals.get("material", 0.0),
            "equipment_total": subtotals.get("equipment", 0.0), "grand_total": grand}


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
