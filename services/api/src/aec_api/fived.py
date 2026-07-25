"""5D — the binding that ties the model to the money.

The takeoff already prices a model, but it maps **IFC class → cost code** and nothing else, so every
wall gets one rate regardless of type, storey, fire rating or phase. A real estimate does not work
that way: `IfcWall` where `FireRating=2HR` on the podium is a different line from a partition on
level 12, and the difference is worth more than the rounding.

`query_dsl` is already THE element selector in this codebase — clash scopes, view filters, smart
views and the rule library all compose on it. So a cost rule is **a stored selector plus a rate**, not
a new engine. That is the whole idea here.

Three properties carry this:

**Later rules win, and every element says which rule won.** Estimates are built by layering: price all
concrete, then override the podium, then override one stair core. A line nobody can attribute back to
the rule that produced it is the cost equivalent of an unattributed tag — the reader sees a number and
cannot check it.

**An element matched by no rule is UNPRICED and reported.** Never silently zero. An unpriced element
is the single most expensive defect an estimate can have, because the total still looks like a total:
it is the same failure as a clash matrix reporting an untested pair as clean.

**A quantity states its basis.** The rate is per unit of *something* — square metres of net wall face,
cubic metres of concrete, each. A rule that prices `area` against an element with no area is refused
rather than billed as zero.
"""
from __future__ import annotations

from typing import Any

from . import query_dsl
from .query_dsl import QueryError

# The bases we can price against, and where the quantity comes from. Kept aligned with the IFC-side
# writer (`aec_data.cost_ifc.QUANTITY_KINDS`) — the two tables are asserted equal in the test, because
# two tables encoding one vocabulary WILL drift silently.
BASES = ("length", "area", "volume", "weight", "count")

MAX_RULES = 500
MAX_SELECTOR_LEN = 500


def validate_rules(rules: list[dict]) -> list[dict]:
    """Validate + normalise cost rules. Order is meaningful and preserved: later rules override."""
    if not isinstance(rules, list) or len(rules) > MAX_RULES:
        raise QueryError(f"rules must be a list (max {MAX_RULES})")
    out = []
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            raise QueryError(f"rule {i} must be an object")
        sel = str(r.get("selector") or "").strip()
        if not sel or len(sel) > MAX_SELECTOR_LEN:
            raise QueryError(f"rule {i} needs a selector (max {MAX_SELECTOR_LEN} chars)")
        query_dsl.parse(sel)                       # validate the grammar now, not at estimate time
        code = str(r.get("code") or "").strip()
        if not code:
            raise QueryError(f"rule {i} needs a cost code")
        basis = str(r.get("basis") or "").strip().lower()
        if basis not in BASES:
            raise QueryError(f"rule {i}: basis must be one of {list(BASES)}, got {basis!r}")
        try:
            rate = float(r.get("unit_cost"))
        except (TypeError, ValueError):
            raise QueryError(f"rule {i} needs a numeric unit_cost") from None
        if rate < 0:
            raise QueryError(f"rule {i}: unit_cost cannot be negative")
        out.append({"selector": sel, "code": code, "basis": basis, "unit_cost": rate,
                    "description": str(r.get("description") or code)})
    return out


def bind(idx: dict[str, dict] | None, rules: list[dict], limit: int = 200_000) -> dict[str, Any]:
    """Resolve which rule prices each element.

    Returns the per-element assignment plus the **unpriced** list, which is the number an estimator
    should look at first.
    """
    idx = idx or {}
    clean = validate_rules(rules)
    assigned: dict[str, dict] = {}
    for n, rule in enumerate(clean):
        hits = query_dsl.select(idx, rule["selector"], limit=limit)["guids"]
        for g in hits:
            # later rules win — layering is how estimates are actually built
            assigned[g] = {"rule": n, "code": rule["code"], "basis": rule["basis"],
                           "unit_cost": rule["unit_cost"], "description": rule["description"],
                           "selector": rule["selector"]}
    unpriced = sorted(g for g in idx if g not in assigned)
    return {
        "rules": clean,
        "assigned": assigned,
        "priced_count": len(assigned),
        "unpriced": unpriced[:5000],
        "unpriced_count": len(unpriced),
        "element_count": len(idx),
        "coverage_pct": round(100.0 * len(assigned) / len(idx), 1) if idx else 0.0,
        "note": ("An element matched by no rule is UNPRICED, never silently zero — the total would "
                 "still look like a total. Later rules win, and each element records the rule that "
                 "priced it so a line can be traced back to the selector that produced it."),
    }


def estimate(idx: dict[str, dict] | None, rules: list[dict],
             quantities: dict[str, dict[str, float]] | None = None,
             limit: int = 200_000) -> dict[str, Any]:
    """Roll the binding up into cost lines ready for `cost_ifc.write_cost_schedule`.

    `quantities` maps GlobalId → {basis: value} (the takeoff's output). An element whose rule prices a
    basis it has no quantity for is reported in `missing_quantity` rather than billed as zero: a rate
    with nothing to multiply is not a cost of nothing, it is an unknown cost.
    """
    b = bind(idx, rules, limit=limit)
    q = quantities or {}
    lines: dict[tuple, dict] = {}
    missing: list[dict] = []

    for guid, a in sorted(b["assigned"].items()):
        have = (q.get(guid) or {}).get(a["basis"])
        if a["basis"] == "count":
            have = 1.0 if have is None else float(have)
        if have is None:
            missing.append({"guid": guid, "code": a["code"], "basis": a["basis"]})
            continue
        key = (a["code"], a["basis"], a["unit_cost"])
        ln = lines.setdefault(key, {"code": a["code"], "description": a["description"],
                                    "basis": a["basis"], "unit_cost": a["unit_cost"],
                                    "quantity": 0.0, "guids": [], "rule": a["rule"]})
        ln["quantity"] += float(have)
        ln["guids"].append(guid)

    out = []
    for ln in lines.values():
        ln["quantity"] = round(ln["quantity"], 4)
        ln["amount"] = round(ln["quantity"] * ln["unit_cost"], 2)
        ln["guids"] = sorted(ln["guids"])
        out.append(ln)
    out.sort(key=lambda x: (-x["amount"], x["code"]))

    return {
        "lines": out,
        "line_count": len(out),
        "total": round(sum(x["amount"] for x in out), 2),
        "priced_count": b["priced_count"],
        "unpriced": b["unpriced"],
        "unpriced_count": b["unpriced_count"],
        "missing_quantity": missing,
        "missing_quantity_count": len(missing),
        "coverage_pct": b["coverage_pct"],
        # the only honest headline: a total over a partly-unpriced model is not the project's cost
        "complete": bool(out) and not b["unpriced_count"] and not missing,
        "note": ("`total` covers the priced lines only. With unpriced elements or missing quantities "
                 "it is a floor, not an estimate — `complete` says which."),
    }
