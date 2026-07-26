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

#: Where a rate came from. The other half of v0.3.697's quantity provenance: an estimate is a rate
#: times a quantity, and both halves need to say what they rest on.
#:
#: `quoted`  — the rule carries the number. Somebody typed it; it may be a real subcontractor quote
#:             or a placeholder, and the estimate cannot tell those apart.
#: `vintage` — resolved from the project's pinned cost database, so the rate arrives with a YEAR and
#:             the localisation/escalation applied to it. Two estimates that differ by 40% because one
#:             priced off a 2019 vintage is a question somebody can answer; the same gap with bare
#:             numbers on both sides is not.
RATE_SOURCES = ("quoted", "vintage")

MAX_RULES = 500
MAX_SELECTOR_LEN = 500

#: Decimal places kept on a PER-ELEMENT amount in `by_element`. Deliberately not 2: cents are for
#: money as presented (a cost line, the total), and rounding every element to a cent before summing
#: drifts away from a line that rounds its sum once. This is wide enough only to trim float
#: representation noise, so summing `by_element` still reproduces `total`. See `estimate`.
_ELEM_DP = 10


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
        # R25-COST-VINTAGE: a rule may carry its own rate, or draw it from the project's pinned cost
        # vintage. `vintage` is not a fallback for a missing number — it is a different, better
        # provenance, and a rule that asks for it and cannot have it is REFUSED rather than quietly
        # priced from somewhere else.
        rate_from = str(r.get("rate_from") or "quoted").strip().lower()
        if rate_from not in RATE_SOURCES:
            raise QueryError(f"rule {i}: rate_from must be one of {list(RATE_SOURCES)}, got {rate_from!r}")
        rate = 0.0
        if rate_from == "quoted":
            try:
                rate = float(r.get("unit_cost"))
            except (TypeError, ValueError):
                raise QueryError(f"rule {i} needs a numeric unit_cost") from None
            if rate < 0:
                raise QueryError(f"rule {i}: unit_cost cannot be negative")
        out.append({"selector": sel, "code": code, "basis": basis, "unit_cost": rate,
                    "rate_from": rate_from,
                    "description": str(r.get("description") or code)})
    return out


def bind(idx: dict[str, dict] | None, rules: list[dict], limit: int = 200_000,
         vintage_rates: dict[str, float] | None = None) -> dict[str, Any]:
    """Resolve which rule prices each element, and at what rate.

    Returns the per-element assignment plus the **unpriced** list, which is the number an estimator
    should look at first, and **no_rate** — elements a `vintage` rule matched but the installed cost
    database has no rate for. That is a third state and it needs its own name: the rule found the
    element, so it is not unpriced; there is no number, so it is not priced either. Folding it into
    one of the two would make an estimate either silently short or silently free.
    """
    idx = idx or {}
    clean = validate_rules(rules)
    vr = vintage_rates or {}
    assigned: dict[str, dict] = {}
    no_rate: list[dict] = []
    for n, rule in enumerate(clean):
        hits = query_dsl.select(idx, rule["selector"], limit=limit)["guids"]
        for g in hits:
            rate, source = rule["unit_cost"], rule["rate_from"]
            if rule["rate_from"] == "vintage":
                cls = str((idx.get(g) or {}).get("ifc_class") or "")
                found = vr.get(cls)
                if found is None:
                    # Recorded against the RULE that wanted it, so the fix is actionable: either the
                    # vintage needs that class or the rule should quote a rate.
                    no_rate.append({"guid": g, "code": rule["code"], "rule": n, "ifc_class": cls})
                    assigned.pop(g, None)
                    continue
                rate = float(found)
            # later rules win — layering is how estimates are actually built
            assigned[g] = {"rule": n, "code": rule["code"], "basis": rule["basis"],
                           "unit_cost": rate, "rate_source": source,
                           "description": rule["description"], "selector": rule["selector"]}
    # Layering means a later rule can price an element an earlier vintage rule could not. Such an
    # element IS priced, so it must not stay in `no_rate` — reporting a gap that a subsequent rule
    # already closed sends an estimator to look at something that is fine. Filtered at the end,
    # against a SET: scanning the list per element is quadratic on a real model.
    no_rate = [x for x in no_rate if x["guid"] not in assigned]
    flagged = {x["guid"] for x in no_rate}
    unpriced = sorted(g for g in idx if g not in assigned and g not in flagged)
    return {
        "rules": clean,
        "assigned": assigned,
        "priced_count": len(assigned),
        "unpriced": unpriced[:5000],
        "unpriced_count": len(unpriced),
        "no_rate": no_rate[:5000],
        "no_rate_count": len(no_rate),
        "element_count": len(idx),
        "coverage_pct": round(100.0 * len(assigned) / len(idx), 1) if idx else 0.0,
        "note": ("An element matched by no rule is UNPRICED, never silently zero — the total would "
                 "still look like a total. Later rules win, and each element records the rule that "
                 "priced it so a line can be traced back to the selector that produced it."),
    }


def estimate(idx: dict[str, dict] | None, rules: list[dict],
             quantities: dict[str, dict[str, float]] | None = None,
             limit: int = 200_000,
             sources: dict[str, dict[str, str]] | None = None,
             vintage_rates: dict[str, float] | None = None,
             vintage: dict[str, Any] | None = None) -> dict[str, Any]:
    """Roll the binding up into cost lines ready for `cost_ifc.write_cost_schedule`.

    `quantities` maps GlobalId → {basis: value} — normally `qto.measure()`'s output, so the estimate
    prices the **model's own** quantities. An element whose rule prices a basis it has no quantity for
    is reported in `missing_quantity` rather than billed as zero: a rate with nothing to multiply is
    not a cost of nothing, it is an unknown cost.

    `sources` is the parallel provenance map, GlobalId → {basis: "declared"|"computed"}. Each line
    reports how its quantity was obtained, because a quantity the model **declared** and one this
    platform **measured off a mesh** are different claims. They are usually close; the difference is
    exactly the sort of thing an estimator wants to know before signing, and a line that cannot say
    which it rests on cannot be checked.
    """
    b = bind(idx, rules, limit=limit, vintage_rates=vintage_rates)
    q = quantities or {}
    src = sources or {}
    lines: dict[tuple, dict] = {}
    missing: list[dict] = []
    per_element: dict[str, dict[str, Any]] = {}

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
                                    "quantity": 0.0, "guids": [], "rule": a["rule"],
                                    "_sources": set(), "_rates": set()})
        ln["quantity"] += float(have)
        ln["guids"].append(guid)
        # R25-ESTIMATE-DIFF needs the EXACT per-element quantity, and a line only carries the sum.
        # Reconstructing it by dividing a line evenly across its GUIDs is a fabrication: add one wall
        # to a line and every other wall in it reports as a design change. The number is exact right
        # here, so it is kept rather than re-derived later from something that lost it.
        # NOT rounded to cents. A line's amount and the total are rounded because that is where money
        # is *presented*; a per-element amount is an intermediate fact, and rounding each one to a
        # cent before summing drifts one-directionally away from the line that rounds the sum once —
        # -$150 across 50,000 elements at a fractional rate. Since `by_element` is part of the
        # response, anything that totals it would disagree with `total` and neither number would be
        # marked as the authoritative one. `_ELEM_DP` is only wide enough to trim float repr noise
        # (0.30000000000000004); it is thousands of times finer than a cent, so summation holds.
        per_element[guid] = {"code": a["code"], "basis": a["basis"],
                             "quantity": float(have), "unit_cost": a["unit_cost"],
                             "amount": round(float(have) * a["unit_cost"], _ELEM_DP),
                             "rate_source": a.get("rate_source") or "quoted",
                             "quantity_source": (src.get(guid) or {}).get(a["basis"]) or "unknown"}
        # An absent source is `unknown`, not `declared`. A legacy caller that supplies quantities and
        # no provenance has told us nothing about where they came from, and answering "the model
        # declared these" on its behalf is the exact overclaim this field exists to prevent.
        ln["_sources"].add((src.get(guid) or {}).get(a["basis"]) or "unknown")
        ln["_rates"].add(a.get("rate_source") or "quoted")

    out = []
    for ln in lines.values():
        ln["quantity"] = round(ln["quantity"], 4)
        ln["amount"] = round(ln["quantity"] * ln["unit_cost"], 2)
        ln["guids"] = sorted(ln["guids"])
        # A line is only `declared` when EVERY element in it was. One measured element in fifty still
        # means the line rests partly on our arithmetic rather than on the model's own assertion, and
        # rounding that away to "declared" is the sort of small lie an estimate cannot afford.
        kinds = ln.pop("_sources")
        ln["quantity_source"] = kinds.pop() if len(kinds) == 1 else "mixed"
        # The other half of the multiplication. An estimate is a rate times a quantity; a line that
        # can say where the quantity came from but not the rate is only half checkable.
        rates = ln.pop("_rates")
        ln["rate_source"] = rates.pop() if len(rates) == 1 else "mixed"
        out.append(ln)
    out.sort(key=lambda x: (-x["amount"], x["code"]))

    return {
        "lines": out,
        "line_count": len(out),
        # Exact per-element facts, so a diff can attribute a change to an element without inventing
        # its share of a line. See `estimate_diff`.
        "by_element": per_element,
        "total": round(sum(x["amount"] for x in out), 2),
        "priced_count": b["priced_count"],
        "unpriced": b["unpriced"],
        "unpriced_count": b["unpriced_count"],
        "missing_quantity": missing,
        "missing_quantity_count": len(missing),
        # How much of the total rests on quantities this platform measured rather than the model
        # declared. Not a fault — often the model simply carries no Qto pset — but it is the number
        # an estimator wants before signing, and it is invisible unless it is stated.
        "no_rate": b["no_rate"],
        "no_rate_count": b["no_rate_count"],
        "vintage_rate_lines": sum(1 for x in out if x["rate_source"] == "vintage"),
        # The vintage's own metadata — year, region index, escalation. A rate sourced from a cost
        # database is only checkable if the database says which one it was.
        "vintage": vintage,
        "computed_quantity_lines": sum(1 for x in out if x["quantity_source"] != "declared"),
        "computed_quantity_amount": round(
            sum(x["amount"] for x in out if x["quantity_source"] != "declared"), 2),
        "coverage_pct": b["coverage_pct"],
        # the only honest headline: a total over a partly-unpriced model is not the project's cost
        # A matched element with no rate is neither priced nor unpriced, and an estimate carrying any
        # of them is not complete either — the total would be short by an amount nobody stated.
        "complete": bool(out) and not b["unpriced_count"] and not missing and not b["no_rate_count"],
        "note": ("`total` covers the priced lines only. With unpriced elements or missing quantities "
                 "it is a floor, not an estimate — `complete` says which."),
    }
