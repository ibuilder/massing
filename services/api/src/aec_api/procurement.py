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
    supplier_totals = dict.fromkeys(suppliers, 0.0)
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


def record_quote_observations(db: Session, project_id: str, quotes: list[dict],
                              actor: str = "system") -> int:
    """PROC-LOOP: every leveled quote line becomes a durable **price observation**
    (`price_observation` record, source="quote"), so quote-time prices build the project's price
    history instead of evaporating with the request. Bad lines are skipped, never fatal."""
    from datetime import date as _date
    if "price_observation" not in me.TABLES:
        return 0
    n = 0
    for q in quotes[:50]:
        supplier = q.get("supplier") or ""
        for ln in (q.get("lines") or [])[:200]:
            item, up = (ln.get("item") or "").strip(), _num(ln.get("unit_price"))
            if not item or up <= 0:
                continue
            me.create_record(db, "price_observation", project_id, {"data": {
                "material": item[:120], "unit_price": up, "unit": ln.get("unit"),
                "qty": _num(ln.get("qty")) or None, "vendor": str(supplier)[:120],
                "date": _date.today().isoformat(), "source": "quote"}}, actor, None)
            n += 1
    return n


def price_history(db: Session, project_id: str, material: str | None = None) -> dict:
    """The price-observation ledger, rolled up per material (canonical match): count, min / median /
    avg / max, the latest observation, vendors seen, and the latest-vs-median drift — the number a
    buyer wants before signing the next PO."""
    import statistics
    rows = (me.list_records(db, "price_observation", project_id, limit=100_000)
            if "price_observation" in me.TABLES else [])
    want = _canon(material) if material else None
    by: dict[str, list[dict]] = {}
    labels: dict[str, str] = {}
    for r in rows:
        d = r.get("data") or {}
        key = _canon(d.get("material", ""))
        if not key or (want and key != want):
            continue
        labels.setdefault(key, d.get("material"))
        up = _num(d.get("unit_price"))
        if up > 0:
            by.setdefault(key, []).append({"unit_price": up, "date": str(d.get("date") or ""),
                                           "vendor": d.get("vendor"), "unit": d.get("unit"),
                                           "source": d.get("source")})
    materials = []
    for key, obs in sorted(by.items()):
        obs.sort(key=lambda o: o["date"])
        prices = [o["unit_price"] for o in obs]
        med = round(statistics.median(prices), 2)
        latest = obs[-1]
        materials.append({
            "material": labels[key], "observations": len(obs),
            "min": min(prices), "median": med, "avg": round(sum(prices) / len(prices), 2),
            "max": max(prices), "unit": latest.get("unit"),
            "latest": {"unit_price": latest["unit_price"], "date": latest["date"],
                       "vendor": latest.get("vendor"), "source": latest.get("source")},
            "latest_vs_median_pct": round((latest["unit_price"] - med) / med * 100, 1) if med else 0.0,
            "vendors": sorted({o.get("vendor") or "" for o in obs} - {""}),
            "series": [{"date": o["date"], "unit_price": o["unit_price"]} for o in obs[-24:]],
        })
    return {"materials": materials, "material_count": len(materials),
            "message": None if materials else "No price observations yet — level quotes with "
                                              "record=true, or add price_observation records."}


# unit preference when suggesting a request quantity from takeoff rows: volume > area > count
_QTY_PREF = (("volume", "m3"), ("area", "m2"), ("count", "ea"))


def suggest_material_requests(rows: list[dict], guids: set[str] | None = None) -> list[dict]:
    """PROC-LOOP: turn takeoff rows (optionally narrowed to a GUID selection) into per-class material
    request suggestions — the field 'order what the model says this pour needs' loop. Pure —
    unit-testable without an IFC."""
    picked = [r for r in rows if guids is None or r.get("guid") in guids]
    by: dict[str, dict] = {}
    for r in picked:
        c = by.setdefault(r.get("ifc_class") or "?", {"count": 0, "area": 0.0, "volume": 0.0,
                                                      "guids": []})
        c["count"] += 1
        c["area"] += float(r.get("area") or 0.0)
        c["volume"] += float(r.get("volume") or 0.0)
        if len(c["guids"]) < 500:
            c["guids"].append(r.get("guid"))
    out = []
    for cls, c in sorted(by.items()):
        qty, unit = None, None
        for k, u in _QTY_PREF:
            v = c["count"] if k == "count" else c[k]
            if v:
                qty, unit = round(float(v), 2), u
                break
        out.append({"material": cls.removeprefix("Ifc"), "ifc_class": cls, "qty": qty, "unit": unit,
                    "elements": c["count"], "guids": c["guids"]})
    return out


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
