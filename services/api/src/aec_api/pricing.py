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
    # PRICE-MATCHED. Three populations, all of them computed here and, until 2026-10-15, all three
    # discarded. `matched` was the only one on the wire, and a caller could not recover the others
    # without parsing the per-line `note` strings.
    unmatched = 0            # no price-book keyword matched the material at all
    unit_mismatch = 0        # the book knows the material and REFUSED on the unit
    comparable = 0           # priced AND carrying an `estimated_unit_price`
    comparable_priced = 0.0  # the priced amount of exactly those lines
    for it in items:
        mat = it.get("material") or it.get("description") or ""
        qty = _num(it.get("quantity"))
        unit = (it.get("unit") or "").lower().strip().rstrip(".")
        est_up = _num(it.get("estimated_unit_price")) or None
        look = _lookup(mat, unit)
        row = {"material": mat, "quantity": qty, "unit": unit, "cost_code": it.get("cost_code") or ""}
        if not look:
            unmatched += 1
            row.update({"matched": None, "note": "no price-book match"})
            lines.append(row)
            continue
        kw, up, book_unit = look
        if book_unit and unit and book_unit != unit:
            # NOTE the two senses of "matched" this branch creates, and which `unit_mismatch` above
            # exists to make countable: the ROW says `matched: kw` (the book knows this material)
            # while the summary's `matched` counts only PRICED lines, so these are excluded from it.
            # The difference between the two senses is exactly this bucket.
            unit_mismatch += 1
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
            comparable += 1
            comparable_priced += priced
            row["estimated_unit_price"] = est_up
            row["variance"] = round(priced - est_amt, 2)
            row["variance_pct"] = round((priced - est_amt) / est_amt * 100, 1) if est_amt else None
        lines.append(row)
    # PRICE-MATCHED. `variance_total` WAS `priced_total - est_total`, which subtracts two totals
    # over different populations: `priced_total` is every matched line, `est_total` only the subset
    # of those that also carried an estimated unit price. Measured on this repo's own
    # `test_pricing.py` fixture -- 2 priced lines, 1 of them estimated -- that returned
    # `variance_total: +4250.0` where the comparable variance is **-1500**: the book is CHEAPER
    # than the estimate on the only line that can be compared, and the card renders a positive
    # variance in `--status-warn` red. The SIGN was wrong, not merely the magnitude, and the same
    # file asserts the correct sign one level down (`concrete["variance"] == 100*185 - 100*200`,
    # commented "negative variance (book cheaper)") without ever checking the total that
    # contradicts it. *A test that is right at the row level and silent at the summary level reads
    # exactly like a test of the summary.*
    #
    # It is now the difference over the SAME lines, and `comparable_priced_total` is published so a
    # reader can see which total it came out of. `priced_total` keeps its meaning -- every priced
    # line -- because that is the right answer to "what does this takeoff cost".
    return {"lines": lines, "line_count": len(lines), "matched": matched,
            "unmatched": unmatched, "unit_mismatch": unit_mismatch,
            "comparable_line_count": comparable,
            "priced_total": round(priced_total, 2), "estimated_total": round(est_total, 2),
            "comparable_priced_total": round(comparable_priced, 2),
            "variance_total": round(comparable_priced - est_total, 2) if comparable else None,
            "coverage_note": _coverage_note(len(lines), matched, unmatched, unit_mismatch,
                                            comparable),
            "pricing_source": "live" if pricing_bridge.is_enabled() else "book",
            "message": (None if lines else "No quantities to price.")}


def _coverage_note(total: int, matched: int, unmatched: int, unit_mismatch: int,
                   comparable: int) -> str:
    """The engine's own sentence about which lines the totals above are over.

    PRICE-MATCHED. The docstring at the top of this module already promises that "unmatched
    materials or unit mismatches are reported, not guessed" -- and they are, per line. What was
    missing is the sentence a SUMMARY reader needs, because 3 priced lines out of 400 and 3 out of
    3 produced identical text on the analytics card.
    """
    if not total:
        return "No takeoff quantities to price."
    bits = [f"{matched} of {total} takeoff line(s) priced"]
    if unmatched:
        bits.append(f"{unmatched} with no price-book match")
    if unit_mismatch:
        bits.append(f"{unit_mismatch} matched in the book but refused on the unit")
    head = bits[0] + (f" ({'; '.join(bits[1:])})" if len(bits) > 1 else "")
    if not comparable:
        return (head + ". No line carries both a price and an estimated unit price, so there is "
                "no variance to report -- not a variance of zero.")
    if comparable == matched:
        # The contrast below would be a FALSE one here, and the first draft printed it anyway:
        # "the variance is over 3 lines, which is not the 3 priced lines above". A sentence whose
        # job is to warn that two populations differ must not assert it when they are the same --
        # a reader who checks once and finds the warning spurious stops reading it.
        return head + f". The variance covers all {matched} priced line(s)."
    return (head + f". The variance is over the {comparable} line(s) carrying BOTH a price and an "
            f"estimated unit price, which is not the {matched} priced line(s) above.")


def project_pricing(db: Session, project_id: str) -> dict:
    """Price the project's production_quantity takeoff against the book / live feed."""
    recs = me.list_records(db, "production_quantity", project_id, limit=100_000) if "production_quantity" in me.TABLES else []
    items = [{"description": (r.get("data") or {}).get("description"),
              "quantity": (r.get("data") or {}).get("quantity"),
              "unit": (r.get("data") or {}).get("unit"),
              "cost_code": (r.get("data") or {}).get("cost_code")} for r in recs]
    return reconcile(items)
