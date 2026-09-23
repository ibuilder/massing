"""Developer cost budget — line-item hard/soft/acquisition costs that roll into the proforma.

Each line: category (acquisition|hard|soft) · description · unit_cost ($/unit) · quantity (SF/unit)
· total = unit_cost × quantity · optional cost_code. Per-category contingency % applies to that
category's subtotal (hard "construction contingency", soft "design contingency") — matching
institutional practice (hard ≈ 70–80% of budget, soft ≈ 20–30%, contingency 5–10%).

Pure functions over plain dicts so the math is testable without a DB. `summarize()` aggregates;
`to_cost_lines()` emits the proforma cost tree (the seed the Finance view applies)."""
from __future__ import annotations

import hashlib
import json
from typing import Any

CATEGORIES = ("acquisition", "hard", "soft")
# proforma cost_lines use land/hard/soft/contingency/fee — map our categories onto those
_PROFORMA_CAT = {"acquisition": "land", "hard": "hard", "soft": "soft"}
_DEFAULT_CONTINGENCY = {"hard": 0.10, "soft": 0.10, "acquisition": 0.0}


def budget_rev(budget: dict[str, Any] | None) -> str:
    """A content-derived revision token for a budget blob — the thing a stale PUT is detected with.

    `Project.dev_budget` is a JSON column on a table with **no `modified_at`**, so there is no stored
    token to compare against and adding one is a migration. The blob's own content is a token that
    needs neither: two callers holding the same bytes hold the same revision, and any committed write
    changes it. Canonical JSON (sorted keys, no whitespace) so a re-serialisation that reorders keys
    is not read as an edit.

    **Compute it over the value the caller was SHOWN, not over the column.** `get_dev_budget` returns
    `p.dev_budget or starter_budget()`, so on a project that has never saved one the caller holds the
    starter budget while the column holds `None`. A token taken from the column would then never match
    the one the client echoes back, and every first save would 409 — *the mismatch is not in the
    comparison, it is in disagreeing about what was read.* Both sides call this with the same
    `or starter_budget()` fallback for that reason.
    """
    payload = json.dumps(budget or {}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def line_total(line: dict) -> float:
    """unit_cost × quantity (quantity defaults to 1 so flat lump sums work)."""
    return round(float(line.get("unit_cost", 0) or 0) * float(line.get("quantity", 1) or 1), 2)


def summarize(budget: dict[str, Any]) -> dict[str, Any]:
    """budget = {lines: [{category, description, unit_cost, quantity, cost_code}], contingency:{cat:pct}}.
    Returns per-category subtotals, contingency amounts, category totals, and the grand total."""
    lines = budget.get("lines") or []
    contingency = {**_DEFAULT_CONTINGENCY, **(budget.get("contingency") or {})}
    cats: dict[str, dict[str, Any]] = {
        c: {"subtotal": 0.0, "contingency_pct": float(contingency.get(c, 0.0)), "lines": []}
        for c in CATEGORIES}
    for ln in lines:
        cat = ln.get("category") if ln.get("category") in CATEGORIES else "hard"
        t = line_total(ln)
        cats[cat]["subtotal"] += t
        cats[cat]["lines"].append({
            "description": ln.get("description") or "(line)",
            "unit_cost": float(ln.get("unit_cost", 0) or 0),
            "quantity": float(ln.get("quantity", 1) or 1),
            "cost_code": ln.get("cost_code"),
            "total": t,
        })
    grand = 0.0
    for c in CATEGORIES:
        sub = round(cats[c]["subtotal"], 2)
        cont = round(sub * cats[c]["contingency_pct"], 2)
        cats[c]["subtotal"] = sub
        cats[c]["contingency"] = cont
        cats[c]["total"] = round(sub + cont, 2)
        grand += cats[c]["total"]
    grand = round(grand, 2)
    hard_total = cats["hard"]["total"]
    soft_total = cats["soft"]["total"]
    hs = hard_total + soft_total
    return {
        "categories": cats,
        "grand_total": grand,
        # institutional sanity ratios (of hard+soft, excl. acquisition)
        "hard_pct": round(hard_total / hs, 3) if hs else 0.0,
        "soft_pct": round(soft_total / hs, 3) if hs else 0.0,
        "line_count": len(lines),
    }


def to_cost_lines(budget: dict[str, Any]) -> list[dict[str, Any]]:
    """Emit the proforma's four canonical cost_lines in fixed order — land, hard, soft, contingency
    — so they line up with the proforma's positional driver fields. Contingency combines the hard
    (construction) + soft (design) + acquisition contingencies. Reconciles to the grand total."""
    s = summarize(budget)
    cats = s["categories"]
    contingency = round(sum(cats[c]["contingency"] for c in CATEGORIES), 2)
    return [
        {"category": "land", "name": "Acquisition", "amount": cats["acquisition"]["subtotal"], "curve": "upfront"},
        {"category": "hard", "name": "Hard costs", "amount": cats["hard"]["subtotal"], "curve": "scurve"},
        {"category": "soft", "name": "Soft costs", "amount": cats["soft"]["subtotal"], "curve": "linear"},
        {"category": "contingency", "name": "Contingency (construction + design)", "amount": contingency, "curve": "scurve"},
    ]


def starter_budget() -> dict[str, Any]:
    """A small, sensible starter so the UI isn't empty (editable; conceptual placeholders)."""
    return {
        "contingency": {"hard": 0.10, "soft": 0.10, "acquisition": 0.0},
        "lines": [
            {"category": "acquisition", "description": "Purchase price", "unit_cost": 0, "quantity": 1},
            {"category": "acquisition", "description": "Transfer taxes & closing", "unit_cost": 0, "quantity": 1},
            {"category": "hard", "description": "Shell & core ($/sf)", "unit_cost": 0, "quantity": 0, "cost_code": "—"},
            {"category": "hard", "description": "MEP", "unit_cost": 0, "quantity": 1},
            {"category": "soft", "description": "Architecture & engineering", "unit_cost": 0, "quantity": 1},
            {"category": "soft", "description": "Permits & legal", "unit_cost": 0, "quantity": 1},
        ],
    }
