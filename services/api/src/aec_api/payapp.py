"""Pay-application ↔ lien-waiver exchange — the accountability layer between billing and payment.

Missed lien waivers are how GCs get double-paid or hit with a mechanic's lien (Siteline / Trimble Pay /
Procore Pay exist entirely for this). This reconciles what was **paid** (`sub_invoice`) against the
**lien waivers** on file (`lien_waiver`) per vendor, and surfaces the exposure: money paid out that no
*unconditional* waiver yet covers. Deterministic, offline; it doesn't move money (that's a licensed
processor via `payments_bridge`) — it enforces the paperwork discipline that protects the GC.

Convention: a waiver is *conditional* (effective only when payment clears) or *unconditional* (final,
after funds received), and *progress* or *final*. We match by substring on `waiver_type` so it works
with whatever labels a deployment uses."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy.orm import Session

from . import modules as me

_CENT = Decimal("0.01")


def _money(v) -> Decimal:
    """Parse a declared amount to an exact Decimal.

    This replaced `_num`, which did `float(str(v).replace(",", "").replace("$", "").strip())` and
    handed the result to an accumulator. Summing money as binary floats drifts — ten 0.10s do not
    make 1.00 — and `reconcile` accumulates across an unbounded number of rows. A pay application
    out by a penny gets rejected, so the drift is the document failing, not a rounding curiosity.

    `Decimal(str(v))` rather than `Decimal(v)` on purpose: `Decimal(0.1)` captures the float's error
    exactly (0.1000000000000000055511151231257827…) and preserves the very thing being fixed, while
    `Decimal("0.1")` is 0.1. Callers legitimately pass floats — records store JSON — so the string
    round-trip is where the value stops being binary.

    Same permissive contract as before: unparseable and empty both return zero rather than raising.
    A new parser is a contract change for every caller, and `test_money_parity.py` pins the accepted
    spellings so tightening it cannot happen by accident.
    """
    if v is None or v == "":
        return Decimal(0)
    try:
        return Decimal(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError, InvalidOperation):
        return Decimal(0)


def _q(d: Decimal) -> Decimal:
    """Quantize to cents, HALF-UP — the accounting convention.

    Not `round()` and not Decimal's default: both are ROUND_HALF_EVEN, so `round(0.125, 2)` gives
    0.12. An invoice rounds half away from zero. The difference is invisible until an auditor finds
    it, which is why it is asserted rather than assumed.
    """
    return d.quantize(_CENT, rounding=ROUND_HALF_UP)


def _retainage(amount: Decimal, pct: Decimal) -> Decimal:
    """Retainage as cents. Exact multiply, then one quantize — never quantize the operands first."""
    return _q(amount * pct / Decimal(100))


def _is_unconditional(wt: str) -> bool:
    return "unconditional" in (wt or "").lower()


def reconcile(db: Session, project_id: str) -> dict:
    """Per-vendor billed / paid / waiver coverage + lien exposure, and a project rollup."""
    invoices = me.list_records(db, "sub_invoice", project_id, limit=100_000) if "sub_invoice" in me.TABLES else []
    waivers = me.list_records(db, "lien_waiver", project_id, limit=100_000) if "lien_waiver" in me.TABLES else []

    vend: dict[str, dict] = {}

    def V(name: str) -> dict:
        return vend.setdefault(name or "(unknown)", {
            "vendor": name or "(unknown)", "billed": Decimal(0), "paid": Decimal(0),
            "retainage": Decimal(0),
            "waived_unconditional": Decimal(0), "waived_conditional": Decimal(0),
            "paid_invoices": 0, "waivers": 0})

    for r in invoices:
        d = r.get("data", {})
        v = V(d.get("vendor"))
        amt = _money(d.get("amount"))
        ret = _retainage(amt, _money(d.get("retainage_pct")))
        state = r.get("workflow_state")
        if state in ("approved", "paid"):
            v["billed"] += amt
            v["retainage"] += ret
        if state == "paid":
            v["paid"] += amt
            v["paid_invoices"] += 1

    for r in waivers:
        d = r.get("data", {})
        if r.get("workflow_state") not in ("received", "closed"):
            continue                                             # only waivers actually on file count
        v = V(d.get("vendor"))
        amt = _money(d.get("amount"))
        v["waivers"] += 1
        if _is_unconditional(d.get("waiver_type")):
            v["waived_unconditional"] += amt
        else:
            v["waived_conditional"] += amt

    rows = []
    for v in vend.values():
        exposure = _q(max(Decimal(0), v["paid"] - v["waived_unconditional"]))
        # Status is decided on the EXACT Decimal, before the float cast below. The old code
        # compared a float exposure against 0.005 — a tolerance that existed only to paper over
        # float drift. With exact cents the comparison is simply "is there any exposure at all".
        v["status"] = ("clear" if exposure <= 0 else
                       "conditional_only" if v["waived_conditional"] >= exposure else "no_waiver")
        v["exposure"] = float(exposure)
        # Cast to float only at the JSON boundary — accumulate exact, serialise at the edge.
        for k in ("billed", "paid", "retainage", "waived_unconditional", "waived_conditional"):
            v[k] = float(_q(v[k]))
        rows.append(v)
    rows.sort(key=lambda x: -x["exposure"])

    # The rollup is the number the user actually reads, so it is summed exactly too rather than
    # re-adding the floats we just cast. `at_risk` is derived from the per-vendor STATUS, not from a
    # second float comparison against 0.005 — two thresholds for one question is how a vendor ends
    # up "clear" in one column and "at risk" in another.
    total_exposure = float(_q(sum((_money(r["exposure"]) for r in rows), Decimal(0))))
    at_risk = [r["vendor"] for r in rows if r["status"] != "clear"]
    return {"vendors": rows, "vendor_count": len(rows),
            "total_lien_exposure": total_exposure, "vendors_at_risk": at_risk,
            "message": (None if not at_risk else
                        f"{len(at_risk)} vendor(s) paid without an unconditional lien waiver on file — "
                        "collect waivers to close the exposure.")}
