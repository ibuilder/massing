"""Capital / investor engine — turns the `investor` module records into a cap table, and allocates
capital calls and distributions pro-rata by commitment. Pairs with the proforma JV waterfall (which
sizes the LP/GP pools over the hold); this layer handles per-investor cap-table math, call/distribution
allocation, and statements. Pure over investor dicts so it's testable without a DB."""
from __future__ import annotations

from typing import Any

from . import money


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


#: `investor`'s workflow is prospect -> committed -> funded -> exited. Ownership belongs to the two
#: middle states: the `commit` transition is the one that declares `requires: ["commitment"]`, so the
#: amount is only validated at that point, and `rescind` (committed -> prospect) is how a commitment is
#: withdrawn. `exited` is deliberately NOT here — an investor who has left does not hold current
#: ownership — while `prospect` is not yet a commitment, only an interest.
_OWNING_STATES = ("committed", "funded")


def cap_table(investors: list[dict]) -> dict[str, Any]:
    """Ownership by commitment, contributed/distributed/unreturned totals, per-investor rows.

    **Only committed capital owns anything, and a DEFAULT STATE IS NOT A SIGNAL.** This summed
    `commitment` across every investor whatever their state: one `prospect` carrying a $10M interest
    and $0 contributed took 50% of a $10M table and halved a real LP from 60% to 30% — and the number
    left here, because `distwaterfall` allocates off these rows.

    The obvious fix — filter out `prospect` — is wrong on its own, and that is the part worth knowing.
    `investor` declares `initial: prospect` and every record is stamped with it at creation, so on a
    project where nobody ever ran the `commit` transition EVERY investor is a prospect and the filter
    empties the cap table. `workflow_in_use` is what separates the two readings: until some investor
    has moved off the initial state, `prospect` means "untouched" and carries no information, so
    everyone counts; once one has, `prospect` genuinely means "not committed" and the state is
    evidence. Prospect rows are never dropped — they stay visible at 0% with their money reported as
    `pipeline_commitment`, so the interest is still on screen, just not as ownership.
    """
    # Has anyone actually used the workflow on this project? Any state other than the stamped initial
    # one proves it, `exited` included — that investor was committed once, which is the same evidence.
    workflow_in_use = any(
        (i.get("workflow_state") or "prospect") != "prospect" for i in investors)

    def _owns(i: dict) -> bool:
        return (not workflow_in_use) or (i.get("workflow_state") in _OWNING_STATES)

    rows = []
    total_commit = sum(_num((i.get("data") or i).get("commitment")) for i in investors if _owns(i))
    pipeline = sum(_num((i.get("data") or i).get("commitment"))
                   for i in investors if not _owns(i))
    for i in investors:
        d = i.get("data") or i
        commit = _num(d.get("commitment"))
        contributed = _num(d.get("contributed"))
        distributed = _num(d.get("distributed"))
        owns = _owns(i)
        rows.append({
            "id": i.get("id"), "ref": i.get("ref"), "investor": d.get("investor"),
            "investor_class": d.get("investor_class") or "LP",
            "entity_type": d.get("entity_type"),
            "commitment": round(commit, 2),
            # Carried on the ROW, not recomputed by each consumer: seven call sites read this table,
            # and a rule re-derived seven times is a rule that disagrees with itself somewhere.
            "counts_toward_ownership": owns,
            "ownership_pct": round(100 * commit / total_commit, 4) if (owns and total_commit) else 0.0,
            "contributed": round(contributed, 2),
            "distributed": round(distributed, 2),
            "unreturned": round(max(0.0, contributed - distributed), 2),
            "status": i.get("workflow_state"),
        })
    # Owners first, then by size. Sorting on commitment alone put the $10M prospect at the TOP of the
    # table as the largest apparent owner while showing 0%% — the reader's eye takes rank as ownership.
    rows.sort(key=lambda r: (not r["counts_toward_ownership"], -r["commitment"]))
    by_class: dict[str, float] = {}
    for r in rows:
        if not r["counts_toward_ownership"]:
            continue          # or by_class would sum to more than total_commitment
        by_class[r["investor_class"]] = by_class.get(r["investor_class"], 0.0) + r["commitment"]
    return {
        "investor_count": len(rows),
        # `total_commitment` is COMMITTED capital — the denominator ownership is computed against.
        # The uncommitted interest is reported beside it rather than folded in or silently dropped.
        "total_commitment": round(total_commit, 2),
        "pipeline_commitment": round(pipeline, 2),
        "workflow_in_use": workflow_in_use,
        "total_contributed": round(sum(r["contributed"] for r in rows), 2),
        "total_distributed": round(sum(r["distributed"] for r in rows), 2),
        "total_unreturned": round(sum(r["unreturned"] for r in rows), 2),
        "by_class": {k: round(v, 2) for k, v in by_class.items()},
        "rows": rows,
    }


#: What a K-1 needs that this platform does not hold. Named individually and returned with every pack,
#: because the failure mode here is not a missing number — it is a document that LOOKS complete. An
#: accountant who is told what is absent can supply it; one handed a plausible-looking pack cannot know.
K1_NOT_INCLUDED = [
    "taxable income or loss allocated per IRC §704(b) — the platform holds no income statement",
    "depreciation, amortisation and §754/§743(b) basis adjustments",
    "guaranteed payments to partners",
    "outside basis, at-risk and passive-activity limitations (partner-level, not partnership-level)",
    "separately stated items (§179, interest, charitable, foreign)",
    "state apportionment and composite-return detail",
]


def k1_pack(investors: list[dict], project_name: str, period: str) -> dict[str, Any]:
    """**K-1 PREPARATION pack — deliberately NOT a K-1, and it says so in its own payload.**

    A Schedule K-1 (Form 1065) reports each partner's *distributive share of taxable income*, which
    requires a partnership income statement allocated under §704(b). This platform has capital
    movements — commitments, contributions, distributions — and **no income statement at all**. Emitting
    something K-1-shaped from that would be the [[confident-wrong-beats-missing]] defect at its most
    expensive: a tax document is relied on, filed, and not re-derived.

    So this returns the half we genuinely hold — the capital-account movement an accountant needs as an
    input — plus `not_included`, an explicit list of what they must still supply. `statement_pdf`
    already draws exactly this boundary in prose (*"not a tax document; K-1s are issued separately"*);
    this makes the same boundary machine-readable.

    **`ownership_pct` is the allocation ratio, and allocation ratios must close.** Percentages are
    rounded for display and rounded shares do not sum to 100 — so `allocation_check` reports the exact
    residual rather than hiding it. A pack whose ratios silently sum to 99.9997% would allocate income
    slightly wrong for every partner, every year, and look right on inspection.
    """
    ct = cap_table(investors)
    rows = []
    for r in ct["rows"]:
        contributed, distributed = r["contributed"], r["distributed"]
        rows.append({
            "investor": r["investor"], "ref": r["ref"], "investor_class": r["investor_class"],
            "entity_type": r["entity_type"],
            "ownership_pct": r["ownership_pct"],
            "commitment": r["commitment"],
            # The capital-account movement we can actually evidence. NOT a §L rollforward: that needs
            # the income allocation above, so the beginning/ending balance is deliberately absent
            # rather than guessed from contributions alone.
            "contributions_to_date": contributed,
            "distributions_to_date": distributed,
            "net_capital_to_date": round(contributed - distributed, 2),
            "unreturned_capital": r["unreturned"],
            "status": r["status"],
        })
    pct_sum = round(sum(r["ownership_pct"] for r in rows), 6)
    return {
        "document_type": "k1_preparation_pack",
        "is_tax_document": False,
        "project": project_name,
        "period": period,
        "investor_count": ct["investor_count"],
        "totals": {
            "commitment": ct["total_commitment"],
            "contributions_to_date": ct["total_contributed"],
            "distributions_to_date": ct["total_distributed"],
            "unreturned_capital": ct["total_unreturned"],
        },
        "rows": rows,
        # Reported, not asserted: an empty fund legitimately sums to 0, and a rounding residual is a
        # fact the preparer should see rather than an error that hides the pack.
        "allocation_check": {
            "ownership_pct_sum": pct_sum,
            "residual": round((100.0 if rows else 0.0) - pct_sum, 6),
            "closes": abs((100.0 if rows else 0.0) - pct_sum) < 0.01,
        },
        "not_included": list(K1_NOT_INCLUDED),
        "note": ("Preparation input for Schedule K-1 (Form 1065) — NOT a K-1 and not a tax document. "
                 "It reports capital movement only; the distributive share of taxable income requires "
                 "a partnership income statement this platform does not hold. See `not_included`."),
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
    amt = _num(amount)
    rows = ct["rows"]
    # MONEY-WIRE (v0.3.718): largest-remainder allocation instead of "absorb the rounding into the
    # last row". Both sum to the total, but the old rule put EVERY leftover cent on whichever
    # investor happened to sort last — the same person each time, on every call and every
    # distribution. With enough investors that is a systematic, arbitrary transfer, and it is the
    # kind of thing an LP notices in a reconciliation and nobody can explain. Largest-remainder
    # gives the spare cents to the shares with the biggest fractional parts, which is the standard
    # method and defensible on a statement.
    parts = money.allocate(amt, [float(r["commitment"]) for r in rows])
    allocations = [{"id": r["id"], "ref": r["ref"], "investor": r["investor"],
                    "ownership_pct": r["ownership_pct"], "amount": a}
                   for r, a in zip(rows, parts)]
    return {"kind": kind, "amount": money.q2(amt), "allocations": allocations}
