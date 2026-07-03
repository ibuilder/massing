"""Materials procure-to-pay — RFQ → quote leveling → PO → delivery → 3-way match.

The materials buying loop (FieldMaterials' territory) is downstream of estimating and distinct from
sub-bid leveling: a GC/trade buys materials from suppliers, and the money leaks are (1) not comparing
quotes, and (2) paying invoices that don't match the PO and the delivery. This provides the two
high-value, deterministic pieces on top of the modules we already have (`commitment` = PO, `delivery`,
`sub_invoice`):
  - **quote leveling** — normalize competing material quotes into an apples-to-apples grid with the
    low price per line item and the best-value supplier, and
  - **3-way match** — reconcile each PO against its deliveries and invoices, flagging over-billing,
    pay-before-receipt, and un-invoiced deliveries.
Offline/deterministic. Sending the RFQ to suppliers is a feature-flagged bridge (`procurement_bridge`)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import modules as me


def _num(v) -> float:
    if v in (None, ""):
        return 0.0
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _canon(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()


def level_quotes(quotes: list[dict]) -> dict:
    """Level material quotes: quotes = [{supplier, lines:[{item, qty, unit, unit_price}]}] →
    per-item comparison across suppliers + the low price and best-value supplier."""
    suppliers = [q.get("supplier") or f"Supplier {i+1}" for i, q in enumerate(quotes)]
    # item (canonical) -> {supplier -> {qty, unit, unit_price, ext}}
    items: dict[str, dict] = {}
    labels: dict[str, str] = {}
    supplier_totals = {s: 0.0 for s in suppliers}
    for q, s in zip(quotes, suppliers):
        for ln in q.get("lines", []):
            key = _canon(ln.get("item", ""))
            if not key:
                continue
            labels.setdefault(key, ln.get("item"))
            qty, up = _num(ln.get("qty")) or 1.0, _num(ln.get("unit_price"))
            ext = round(qty * up, 2)
            items.setdefault(key, {})[s] = {"qty": qty, "unit": ln.get("unit"), "unit_price": up, "ext": ext}
            supplier_totals[s] += ext

    rows = []
    savings = 0.0
    for key, per in sorted(items.items()):
        priced = {s: d for s, d in per.items() if d["unit_price"] > 0}
        low_s = min(priced, key=lambda s: priced[s]["unit_price"], default=None)
        high = max((d["unit_price"] for d in priced.values()), default=0)
        low = priced[low_s]["unit_price"] if low_s else 0
        rows.append({"item": labels[key], "low_supplier": low_s, "low_price": low,
                     "prices": {s: per.get(s, {}).get("unit_price") for s in suppliers},
                     "spread_pct": round((high - low) / low * 100, 1) if low else 0.0})
        # savings = buying each line from its low supplier vs the single cheapest all-in supplier
        if low_s:
            savings += (high - low) * (priced[low_s]["qty"])
    supplier_totals = {s: round(v, 2) for s, v in supplier_totals.items()}
    best_all_in = min(supplier_totals, key=lambda s: supplier_totals[s]) if supplier_totals else None
    return {"suppliers": suppliers, "items": rows, "supplier_totals": supplier_totals,
            "best_all_in_supplier": best_all_in,
            "line_by_line_savings": round(savings, 2),
            "message": (None if rows else "No quote lines to level.")}


def three_way_match(db: Session, project_id: str) -> dict:
    """Reconcile each PO (`commitment`) against its deliveries and invoices, flagging discrepancies."""
    pos = me.list_records(db, "commitment", project_id, limit=100_000) if "commitment" in me.TABLES else []
    deliveries = me.list_records(db, "delivery", project_id, limit=100_000) if "delivery" in me.TABLES else []
    invoices = me.list_records(db, "sub_invoice", project_id, limit=100_000) if "sub_invoice" in me.TABLES else []

    def _po_key(rec):
        return rec.get("id"), rec.get("ref")

    rows = []
    for po in pos:
        d = po.get("data", {})
        pid_, pref = _po_key(po)
        vendor, cc = d.get("vendor"), d.get("cost_code")
        po_amt = _num(d.get("amount"))
        # deliveries linked by commitment reference or po_number
        po_deliveries = [x for x in deliveries
                         if (x.get("data") or {}).get("commitment") in (pid_, pref)
                         or (x.get("data") or {}).get("po_number") in (pref, pid_)]
        received = [x for x in po_deliveries if str((x.get("data") or {}).get("status", "")).lower() in ("received", "closed")]
        # invoices matched (best-effort) by vendor + cost code
        po_invoices = [x for x in invoices
                       if (x.get("data") or {}).get("vendor") == vendor
                       and (not cc or (x.get("data") or {}).get("cost_code") == cc)]
        invoiced = round(sum(_num((x.get("data") or {}).get("amount")) for x in po_invoices), 2)

        flags = []
        if invoiced > po_amt + 0.005:
            flags.append(f"invoiced ${invoiced:,.0f} exceeds PO ${po_amt:,.0f}")
        if invoiced > 0 and not received:
            flags.append("invoiced but nothing received (pay-before-receipt)")
        if received and not po_invoices:
            flags.append("delivered but not yet invoiced")
        status = "ok" if not flags else "review"
        rows.append({"po": pref, "vendor": vendor, "cost_code": cc, "po_amount": round(po_amt, 2),
                     "deliveries": len(po_deliveries), "received": len(received),
                     "invoiced": invoiced, "invoice_count": len(po_invoices),
                     "variance": round(invoiced - po_amt, 2), "flags": flags, "status": status})
    rows.sort(key=lambda r: (r["status"] != "review", -abs(r["variance"])))
    flagged = [r["po"] for r in rows if r["status"] == "review"]
    return {"pos": rows, "po_count": len(rows), "flagged": flagged,
            "message": (None if not flagged else f"{len(flagged)} PO(s) need review — check over-billing, "
                        "pay-before-receipt, and un-invoiced deliveries.")}
