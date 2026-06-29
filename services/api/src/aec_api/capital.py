"""Capital / investor engine — turns the `investor` module records into a cap table, and allocates
capital calls and distributions pro-rata by commitment. Pairs with the proforma JV waterfall (which
sizes the LP/GP pools over the hold); this layer handles per-investor cap-table math, call/distribution
allocation, and statements. Pure over investor dicts so it's testable without a DB."""
from __future__ import annotations

from typing import Any


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def cap_table(investors: list[dict]) -> dict[str, Any]:
    """Ownership by commitment, contributed/distributed/unreturned totals, per-investor rows."""
    rows = []
    total_commit = sum(_num((i.get("data") or i).get("commitment")) for i in investors)
    for i in investors:
        d = i.get("data") or i
        commit = _num(d.get("commitment"))
        contributed = _num(d.get("contributed"))
        distributed = _num(d.get("distributed"))
        rows.append({
            "id": i.get("id"), "ref": i.get("ref"), "investor": d.get("investor"),
            "investor_class": d.get("investor_class") or "LP",
            "entity_type": d.get("entity_type"),
            "commitment": round(commit, 2),
            "ownership_pct": round(100 * commit / total_commit, 4) if total_commit else 0.0,
            "contributed": round(contributed, 2),
            "distributed": round(distributed, 2),
            "unreturned": round(max(0.0, contributed - distributed), 2),
            "status": i.get("workflow_state"),
        })
    rows.sort(key=lambda r: -r["commitment"])
    by_class: dict[str, float] = {}
    for r in rows:
        by_class[r["investor_class"]] = by_class.get(r["investor_class"], 0.0) + r["commitment"]
    return {
        "investor_count": len(rows),
        "total_commitment": round(total_commit, 2),
        "total_contributed": round(sum(r["contributed"] for r in rows), 2),
        "total_distributed": round(sum(r["distributed"] for r in rows), 2),
        "total_unreturned": round(sum(r["unreturned"] for r in rows), 2),
        "by_class": {k: round(v, 2) for k, v in by_class.items()},
        "rows": rows,
    }


def statement_pdf(row: dict, totals: dict, project_name: str) -> bytes:
    """A one-page investor capital-account statement (commitment, ownership, contributed/distributed,
    unreturned). `row`: a cap_table row; `totals`: the cap_table summary."""
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    m = lambda v: "$" + f"{float(v or 0):,.0f}"  # noqa: E731
    rows = [
        ["Investor", str(row.get("investor", ""))],
        ["Class", str(row.get("investor_class", "LP"))],
        ["Entity type", str(row.get("entity_type") or "—")],
        ["Commitment", m(row.get("commitment"))],
        ["Ownership", f"{row.get('ownership_pct', 0)}%"],
        ["Contributed to date", m(row.get("contributed"))],
        ["Distributed to date", m(row.get("distributed"))],
        ["Unreturned capital", m(row.get("unreturned"))],
        ["Unfunded commitment", m(max(0.0, float(row.get("commitment") or 0) - float(row.get("contributed") or 0)))],
    ]
    t = Table(rows, colWidths=[2.4 * inch, 3.0 * inch])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                           ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f6f8")),
                           ("FONTSIZE", (0, 0), (-1, -1), 10),
                           ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white])]))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title="Investor statement", topMargin=0.8 * inch)
    doc.build([
        Paragraph("Investor Capital Account Statement", ss["Title"]),
        Paragraph(f"{project_name} · fund commitment {m(totals.get('total_commitment'))}", ss["Normal"]),
        Spacer(1, 14), t, Spacer(1, 16),
        Paragraph("Distributions and capital calls are allocated pro-rata by commitment. This statement "
                  "is informational and not a tax document; K-1s are issued separately.", ss["Italic"]),
    ])
    return buf.getvalue()


def allocate(investors: list[dict], amount: float, kind: str = "call") -> dict[str, Any]:
    """Allocate a capital call or distribution pro-rata by commitment. `kind`: call | distribution.
    Returns per-investor amounts that sum to `amount` (last row absorbs rounding)."""
    ct = cap_table(investors)
    total = ct["total_commitment"]
    amt = _num(amount)
    allocations, running = [], 0.0
    for idx, r in enumerate(ct["rows"]):
        share = (r["commitment"] / total) if total else 0.0
        a = round(amt * share, 2)
        if idx == len(ct["rows"]) - 1:                     # absorb rounding into the last row
            a = round(amt - running, 2)
        running += a
        allocations.append({"ref": r["ref"], "investor": r["investor"],
                            "ownership_pct": r["ownership_pct"], "amount": a})
    return {"kind": kind, "amount": round(amt, 2), "allocations": allocations}
