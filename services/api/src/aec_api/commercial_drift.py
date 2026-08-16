"""R41-COMMERCIAL-DRIFT — diff the money across DOCUMENTS, along references that already exist.

Premise-checked before building, and the entry was larger than the gap. `margin.py` already totals
budget / committed / actual / billed per cost code, and `cost_spine.py` already asks whether one code
carries the same *scope* from estimate through commitment to invoice. **That is drift measured per
cost code, and it structurally cannot see this one**: two documents can net to the right code total
while an individual award drifted, because a roll-up adds before it compares.

The references needed are already in the registers — no schema change:

    bid_submission ──awarded_from── subcontract ──subcontract── sub_invoice

so this walks them and compares amounts at each hop. Nothing is re-derived; every figure is read from
the document that carries it.

THE TWO REFUSALS, both of which are about not calling an agreed number a problem
------------------------------------------------------------------------------
1.  **A change order is not drift.** `subcontract.change_orders` is a rollup summing `cor.amount` —
    money somebody signed for. Folding it into the bid-to-contract comparison would flag every
    legitimate CO as scope added in the dark, on every project that has one, which is every project.
    So COs belong to the *contract → invoiced* hop as part of the agreed sum, and never to the
    *bid → award* hop. They are reported beside the drift, not inside it.

2.  **An unaccepted alternate was never awarded.** `bid_submission` carries `amount`, `base_bid`, and
    an `alternates` table whose rows have an `accepted` checkbox. Comparing `amount` blindly treats
    rejected alternates as if they were bought; comparing `base_bid` alone treats accepted ones as
    scope that appeared from nowhere. The comparable figure is **base bid + accepted alternates**, and
    the row says which basis it used so a reader can disagree with it.

And the standing one, because it is the same bug this codebase keeps finding: **a missing figure is
`absent`, never 0.0.** A bid with no amount compared against a contract is not a 100% overrun.

`drift_pct` is deliberately signed and unbounded rather than banded: the useful cases run in both
directions, and a band would decide for the reader what "material" means on a number they can see.
"""
from __future__ import annotations

from typing import Any

BASIS_BASE_PLUS_ACCEPTED = "base_bid_plus_accepted_alternates"
BASIS_AMOUNT = "bid_amount"
BASIS_UNAVAILABLE = "unavailable"

#: A hop is only comparable when BOTH ends carry a number. Stated as a constant because "how many
#: hops could not be compared" is the number that says whether this report means anything.
STATUS_COMPARED = "compared"
STATUS_INCOMPARABLE = "incomparable"


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool) or v == "":
        return None
    try:
        f = float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return None if f != f or f in (float("inf"), float("-inf")) else f


def _data(rec: Any) -> dict[str, Any]:
    if not isinstance(rec, dict):
        return {}
    d = rec.get("data")
    return d if isinstance(d, dict) else rec


def bid_award_figure(bid: dict | None) -> dict[str, Any]:
    """What the bid actually committed to, and on what basis.

    Base bid + **accepted** alternates when the alternates table can be read; the bid's own `amount`
    otherwise. Never a silent mix of the two.
    """
    d = _data(bid)
    base = _num(d.get("base_bid"))
    rows = d.get("alternates")
    if base is not None and isinstance(rows, list):
        accepted = [r for r in rows if isinstance(r, dict) and r.get("accepted")]
        add = sum(_num(r.get("amount")) or 0.0 for r in accepted)
        return {"value": round(base + add, 2), "basis": BASIS_BASE_PLUS_ACCEPTED,
                "base_bid": base, "accepted_alternates": len(accepted),
                "accepted_alternates_value": round(add, 2)}
    amt = _num(d.get("amount"))
    if amt is not None:
        return {"value": amt, "basis": BASIS_AMOUNT, "base_bid": base,
                "accepted_alternates": None, "accepted_alternates_value": None}
    return {"value": None, "basis": BASIS_UNAVAILABLE, "base_bid": base,
            "accepted_alternates": None, "accepted_alternates_value": None}


def _hop(name: str, frm: float | None, to: float | None, **extra: Any) -> dict[str, Any]:
    if frm is None or to is None:
        return {"hop": name, "status": STATUS_INCOMPARABLE, "from": frm, "to": to,
                "delta": None, "drift_pct": None,
                "note": "one side carries no figure — this hop is not comparable, and it is NOT a "
                        "zero-dollar difference", **extra}
    delta = round(to - frm, 2)
    return {"hop": name, "status": STATUS_COMPARED, "from": frm, "to": to, "delta": delta,
            "drift_pct": (round(delta / frm * 100.0, 2) if frm else None), **extra}


def walk(bids: list[dict] | None, subcontracts: list[dict] | None,
         invoices: list[dict] | None,
         commitments: list[dict] | None = None) -> dict[str, Any]:
    """One row per subcontract: bid → executed contract → PO → invoiced. Pure, so it is testable flat.

    `commitments` is the PO leg, added v0.3.970. The roadmap recorded this hop as blocked on a
    `purchase_order` register that "still does not exist" — but `commitment` is that register: it is
    titled *"Commitments (POs)"*, carries `po_date`, `amount` and `retainage_pct`, and **already
    references `subcontract`**. So the hop needed no schema change, exactly like the three before it.
    The blocker was the name.

    Optional so every existing caller keeps working: a project with no commitments gets the same
    three-hop walk it got before, with the PO hop reported `incomparable` rather than as a zero.
    """
    by_bid = {str(b.get("id")): b for b in (bids or []) if isinstance(b, dict) and b.get("id")}
    po_by_sub: dict[str, list[dict]] = {}
    for po in commitments or []:
        if not isinstance(po, dict):
            continue
        sid = str(_data(po).get("subcontract") or "")
        if sid:
            po_by_sub.setdefault(sid, []).append(po)
    inv_by_sub: dict[str, list[dict]] = {}
    for inv in invoices or []:
        if not isinstance(inv, dict):
            continue
        sid = str(_data(inv).get("subcontract") or "")
        if sid:
            inv_by_sub.setdefault(sid, []).append(inv)

    rows: list[dict[str, Any]] = []
    for sc in subcontracts or []:
        if not isinstance(sc, dict):
            continue
        d = _data(sc)
        sid = str(sc.get("id") or "")
        value = _num(d.get("value"))
        cos = _num(d.get("change_orders")) or 0.0
        bid = by_bid.get(str(d.get("awarded_from") or ""))
        award = bid_award_figure(bid) if bid else {
            "value": None, "basis": BASIS_UNAVAILABLE, "base_bid": None,
            "accepted_alternates": None, "accepted_alternates_value": None}

        invs = inv_by_sub.get(sid, [])
        billed = sum(_num(_data(i).get("amount")) or 0.0 for i in invs) if invs else None

        # The PO leg. Summed across every commitment pointing at this subcontract, because a
        # subcontract is routinely bought out in more than one PO and comparing the contract to the
        # LARGEST of them would report the rest as money that vanished.
        pos = po_by_sub.get(sid, [])
        committed = (sum(_num(_data(p).get("amount")) or 0.0 for p in pos) if pos else None)

        hops = [
            # Bid -> executed contract. Change orders are NOT in this comparison: they are agreed
            # money, and including them would report every CO as scope added between bid and contract.
            _hop("bid_to_contract", award["value"], value,
                 award_basis=award["basis"],
                 accepted_alternates=award["accepted_alternates"],
                 linked_bid=(bid or {}).get("id")),
            # Executed contract -> what was actually committed on paper. This is the hop the entry
            # called blocked: a subcontract signed at one number and PO'd at another is money that
            # left the agreement without anyone signing a change order for it.
            #
            # Compared against the contract value WITHOUT change orders on purpose. A CO raises the
            # contract sum and is usually followed by its own PO; comparing the CO-inclusive sum to
            # POs raised before it would report every mid-job change as an under-commitment until
            # the paperwork caught up, which is a timing artefact rather than drift.
            _hop("contract_to_po", value, committed,
                 po_count=len(pos), change_orders_excluded=cos),
            # Contract (as agreed today, COs included) -> what has been invoiced against it.
            _hop("contract_to_invoiced",
                 (round(value + cos, 2) if value is not None else None), billed,
                 change_orders=cos, invoice_count=len(invs)),
        ]
        rows.append({
            "subcontract_id": sid,
            "vendor": d.get("vendor") or d.get("trade") or sid,
            "trade": d.get("trade"),
            "contract_value": value,
            "change_orders": cos,
            "contract_sum_to_date": round(value + cos, 2) if value is not None else None,
            "committed": committed,
            "po_count": len(pos),
            "invoiced": billed,
            "hops": hops,
            "incomparable_hops": [h["hop"] for h in hops if h["status"] == STATUS_INCOMPARABLE],
        })

    compared = [h for r in rows for h in r["hops"] if h["status"] == STATUS_COMPARED]
    drifted = [h for h in compared if h["delta"]]
    rows.sort(key=lambda r: -max((abs(h["delta"] or 0) for h in r["hops"]), default=0))
    return {
        "rows": rows,
        "subcontract_count": len(rows),
        "hops_compared": len(compared),
        "hops_incomparable": sum(len(r["incomparable_hops"]) for r in rows),
        "drifted_count": len(drifted),
        "largest_drift": max((abs(h["delta"]) for h in drifted), default=0.0),
        "total_change_orders": round(sum(r["change_orders"] for r in rows), 2),
        "note": ("bid → executed contract → invoiced, walked along references the registers already "
                 "carry. Change orders are reported beside the drift and never inside the "
                 "bid-to-contract hop: a CO is money somebody signed for, and counting it as drift "
                 "would flag every project that has one. An unaccepted alternate is not part of the "
                 "award. A hop with a figure missing on either side is `incomparable`, which is not "
                 "the same as a zero-dollar difference and is counted separately."),
    }


def for_project(db, project_id: str) -> dict[str, Any]:
    """The drift walk for one project, from the registers as stored."""
    from . import modules as me

    def load(key: str) -> list[dict]:
        return me.list_records(db, key, project_id, limit=100000) if key in me.TABLES else []

    # `commitment` IS the PO register — "Commitments (POs)", carrying po_date/amount/vendor and a
    # `subcontract` reference. The roadmap had this hop blocked on a `purchase_order` register that
    # "still does not exist"; the capability existed under the other name.
    out = walk(load("bid_submission"), load("subcontract"), load("sub_invoice"),
               load("commitment"))
    out["project_id"] = project_id
    return out
