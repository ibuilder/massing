"""Takeoff pricing — reconcile quantities against current unit costs, not a stale cost book.

ContractorPlus's Estimatic wedge is pricing takeoff from *live* localized material costs; the market is
moving from static cost books to current pricing. This prices a takeoff from a built-in regional unit
price book (a sane offline default a deployment can override) and, when a live-pricing provider is
configured, from that feed via `pricing_bridge`. It flags variance against the line's own estimated unit
price so an estimator sees where the estimate is stale. Deterministic; no fabrication — unmatched
materials or unit mismatches are reported, not guessed."""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import modules as me
from . import pricing_bridge

# material keyword -> (unit_price_usd, unit). Representative national-average unit costs (installed);
# a deployment overrides per region / via the live feed. Units are common US takeoff units.
PRICE_BOOK: dict[str, tuple[float, str]] = {
    "concrete": (185.0, "cy"), "rebar": (1.15, "lb"), "reinforc": (1.15, "lb"),
    "structural steel": (2.75, "lb"), "steel": (2.75, "lb"),
    "cmu": (13.5, "sf"), "block": (13.5, "sf"), "masonry": (18.0, "sf"), "brick": (22.0, "sf"),
    "drywall": (2.75, "sf"), "gypsum": (2.75, "sf"), "framing": (7.5, "sf"), "lumber": (0.95, "bf"),
    "insulation": (1.85, "sf"), "glazing": (65.0, "sf"), "curtain wall": (95.0, "sf"),
    "roofing": (9.5, "sf"), "paint": (1.65, "sf"), "carpet": (4.5, "sy"), "asphalt": (135.0, "ton"),
    "excavation": (14.0, "cy"), "conduit": (12.0, "lf"), "duct": (35.0, "lf"), "pipe": (28.0, "lf"),
}


def _num(v) -> float:
    if v in (None, ""):
        return 0.0
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _lookup(material: str, unit: str) -> tuple[str, float, str] | None:
    """(matched_keyword, unit_price, book_unit). Live feed first when configured, else the book."""
    low = (material or "").lower()
    live = pricing_bridge.unit_price(material, unit) if pricing_bridge.is_enabled() else None
    if live is not None:
        return ("live", live, (unit or "").lower())
    for kw, (price, u) in PRICE_BOOK.items():
        if kw in low:
            return kw, price, u
    return None


def reconcile(items: list[dict]) -> dict:
    """Price each takeoff line; compare to its estimated unit price where present.

    items: [{material|description, quantity, unit, estimated_unit_price?, cost_code?}]"""
    lines, priced_total, est_total = [], 0.0, 0.0
    matched = 0
    for it in items:
        mat = it.get("material") or it.get("description") or ""
        qty = _num(it.get("quantity"))
        unit = (it.get("unit") or "").lower().strip().rstrip(".")
        est_up = _num(it.get("estimated_unit_price")) or None
        look = _lookup(mat, unit)
        row = {"material": mat, "quantity": qty, "unit": unit, "cost_code": it.get("cost_code") or ""}
        if not look:
            row.update({"matched": None, "note": "no price-book match"})
            lines.append(row)
            continue
        kw, up, book_unit = look
        if book_unit and unit and book_unit != unit:
            row.update({"matched": kw, "unit_price": up, "book_unit": book_unit,
                        "priced_amount": None, "note": f"unit '{unit}' != book unit '{book_unit}'"})
            lines.append(row)
            continue
        matched += 1
        priced = round(qty * up, 2)
        priced_total += priced
        row.update({"matched": kw, "unit_price": up, "priced_amount": priced,
                    "source": "live" if kw == "live" else "book"})
        if est_up:
            est_amt = round(qty * est_up, 2)
            est_total += est_amt
            row["estimated_unit_price"] = est_up
            row["variance"] = round(priced - est_amt, 2)
            row["variance_pct"] = round((priced - est_amt) / est_amt * 100, 1) if est_amt else None
        lines.append(row)
    return {"lines": lines, "line_count": len(lines), "matched": matched,
            "priced_total": round(priced_total, 2), "estimated_total": round(est_total, 2),
            "variance_total": round(priced_total - est_total, 2) if est_total else None,
            "pricing_source": "live" if pricing_bridge.is_enabled() else "book",
            "message": (None if lines else "No quantities to price.")}


def project_pricing(db: Session, project_id: str) -> dict:
    """Price the project's production_quantity takeoff against the book / live feed."""
    recs = me.list_records(db, "production_quantity", project_id, limit=100_000) if "production_quantity" in me.TABLES else []
    items = [{"description": (r.get("data") or {}).get("description"),
              "quantity": (r.get("data") or {}).get("quantity"),
              "unit": (r.get("data") or {}).get("unit"),
              "cost_code": (r.get("data") or {}).get("cost_code")} for r in recs]
    return reconcile(items)
