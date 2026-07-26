"""R27-SOV-LOOP — the schedule of values built from the estimate, not re-keyed from it.

Every piece of this chain already existed and one link did not. `fived.estimate` measures the model
and prices it; `cost.g703` reads `sov` records into a continuation sheet; `report.payapp_pdf` renders
the application. Between the first and the second there was **nothing** — the schedule of values was
typed in again by hand from a number the platform had already computed. That is where the traceability
from a pay-app line back to a model element was being lost, and it was lost at the one seam where
somebody is asking to be paid.

**What the transformation actually is.** An estimate line is keyed by (cost code, basis, unit rate) —
it splits `03 30 00` into concrete-by-volume and formwork-by-area because those are priced
differently. A schedule of values is keyed by **what gets billed**, which is coarser: one item per
cost code, because that is the granularity a contract and an owner's reviewer work in. So this is a
regrouping, and the whole risk of a regrouping is money going missing inside it.

**Four things it refuses to do quietly.**

*Unpriced scope is EXCLUDED and SAID, never dropped.* `fived.estimate` already reports `unpriced`,
`no_rate` and `missing_quantity` — elements it could not price at all. An SOV built only from the
lines that happened to price is smaller than the job, and it looks complete because every line in it
is right. The caller gets `excluded` with counts and reasons, and `covers_whole_model` is False when
any exists. This is the same rule `fourd_ifc` learned about truncated tasks: a programme quietly
shorter than the project is discovered from a missed date rather than from a report.

*The rounding residual is placed, not discarded.* Rounding each item to cents and summing does not
equal rounding the total once. The difference is pennies and it is exactly the kind of penny that
makes an owner's reviewer reject a G703. The residual is applied to the largest item — the one where
it is proportionally invisible — and **reported**, so the number is auditable rather than merely
tidy.

*An SOV at cost says so.* Scheduled values are **contract** values; an estimate is **cost**. Billing a
lump-sum contract off unmarked-up cost under-bills it by the entire fee, silently and every month.
`markup_pct` defaults to zero because inventing a fee would be worse — but a zero-markup result
carries `at_cost: True` rather than passing as an ordinary schedule of values.

*Provenance survives the regrouping.* Each item keeps the GlobalIds behind it and the
`quantity_source`/`rate_source` shipped in v0.3.699, collapsing to `mixed` when its lines disagree.
That is the entire point of the exercise: a pay-app line can now be traced to the model elements it
bills for, and to whether those quantities were measured or declared.

**On `reconciles`.** It is a *conservation* check, not a correctness check — the distinction this
codebase learned the expensive way when `estimate_diff` reported `reconciles: True` over fabricated
numbers. It proves the regrouping lost no money; it cannot prove the estimate was right. So it is
checked **two ways against two independent accumulations** in the source: the line totals and the
per-element totals, which `fived` builds separately. Agreement between those catches a grouping bug;
neither can catch a pricing one, and this module does not claim otherwise.
"""
from __future__ import annotations

from typing import Any

#: Cap on items produced in one pass. A schedule of values with thousands of lines is unbillable, and
#: an unbounded regrouping turns one bad rule set into an unusable contract document.
MAX_ITEMS = 2000

#: How items are keyed. `code` is the ordinary contract granularity; `division` rolls up to the
#: two-digit CSI division for a summary-level contract; `line` keeps the estimate's own split for a
#: cost-plus job that bills at that detail.
GROUPINGS = ("code", "division", "line")

#: Money is presented in cents.
_DP = 2


def _division(code: str) -> str:
    """The two-digit CSI division of a cost code, or the code itself when it has none."""
    c = str(code or "").strip()
    head = c[:2]
    return head if head.isdigit() else c


def _key(line: dict[str, Any], grouping: str) -> str:
    code = str(line.get("code") or "").strip()
    if grouping == "division":
        return _division(code)
    if grouping == "line":
        # The estimate's own key, preserved: code + basis + rate.
        return f"{code}|{line.get('basis')}|{line.get('unit_cost')}"
    return code


def from_estimate(est: dict[str, Any], *, markup_pct: float = 0.0,
                  grouping: str = "code") -> dict[str, Any]:
    """Regroup a `fived.estimate` result into schedule-of-values items.

    Returns the items plus what was **excluded**, whether the result **reconciles** against both of
    the estimate's independent accumulations, and whether it is **at cost**.
    """
    if grouping not in GROUPINGS:
        raise ValueError(f"grouping must be one of {list(GROUPINGS)}, got {grouping!r}")
    try:
        markup = float(markup_pct)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"markup_pct must be a number, got {markup_pct!r}") from exc
    if markup < 0 or markup > 500:
        # Refused rather than clamped. A negative fee is not a fee, and a 6000% one is a typo that
        # would otherwise reach a contract document looking deliberate.
        raise ValueError(f"markup_pct must be between 0 and 500, got {markup}")

    lines = list(est.get("lines") or [])
    factor = 1.0 + markup / 100.0

    groups: dict[str, dict[str, Any]] = {}
    seen_guids: set[str] = set()
    duplicate_guids: set[str] = set()
    for ln in lines:
        k = _key(ln, grouping)
        g = groups.setdefault(k, {"key": k, "cost_code": str(ln.get("code") or "").strip(),
                                  "estimate_amount": 0.0, "guids": [], "merged_lines": 0,
                                  "_descs": [], "_sources": set(), "_rates": set(),
                                  "_bases": set()})
        amount = float(ln.get("amount") or 0.0)
        g["estimate_amount"] += amount
        g["merged_lines"] += 1
        g["_descs"].append((amount, str(ln.get("description") or ln.get("code") or "")))
        g["_sources"].add(str(ln.get("quantity_source") or "unknown"))
        g["_rates"].add(str(ln.get("rate_source") or "unknown"))
        g["_bases"].add(str(ln.get("basis") or ""))
        for gid in (ln.get("guids") or []):
            # A GlobalId reaching two items would be billed twice. `fived` assigns each element to
            # exactly one line, so this should be impossible — which is precisely why it is checked
            # rather than assumed. An assumption that holds is free to verify; one that quietly stops
            # holding bills an owner twice for the same wall.
            if gid in seen_guids:
                duplicate_guids.add(gid)
            seen_guids.add(gid)
            g["guids"].append(gid)

    # Trade order, not amount order. An estimate sorts by amount because the reader is hunting for
    # what dominates the cost; a schedule of values is read down the trades by someone checking that
    # nothing is absent, and re-sorting it by size makes an omission invisible.
    ordered = sorted(groups.values(), key=lambda g: (g["cost_code"], g["key"]))
    truncated = max(0, len(ordered) - MAX_ITEMS)
    ordered = ordered[:MAX_ITEMS]

    items: list[dict[str, Any]] = []
    for i, g in enumerate(ordered, start=1):
        descs = sorted(g.pop("_descs"), reverse=True)
        head = descs[0][1] if descs else g["cost_code"]
        # When merged lines disagree on wording, the largest line names the item and the count is
        # kept visible. Silently showing one description for five kinds of work reads as a complete
        # scope statement and is not.
        distinct = {d for _, d in descs}
        description = head if len(distinct) <= 1 else f"{head} (+{len(distinct) - 1} more)"

        srcs, rates, bases = g.pop("_sources"), g.pop("_rates"), g.pop("_bases")
        value = round(g["estimate_amount"] * factor, _DP)
        items.append({
            "item_no": f"{i:04d}",
            "description": description,
            "cost_code": g["cost_code"],
            "scheduled_value": value,
            "estimate_amount": round(g["estimate_amount"], _DP),
            "markup_amount": round(value - round(g["estimate_amount"], _DP), _DP),
            "merged_lines": g["merged_lines"],
            "guids": sorted(set(g["guids"])),
            "element_count": len(set(g["guids"])),
            # `mixed` when the merged lines disagree — the same collapse rule `fived` applies within a
            # line, for the same reason: one measured element among fifty still means the item rests
            # partly on our arithmetic.
            "quantity_source": srcs.pop() if len(srcs) == 1 else "mixed",
            "rate_source": rates.pop() if len(rates) == 1 else "mixed",
            "basis": bases.pop() if len(bases) == 1 else "mixed",
        })

    est_total = round(float(est.get("total") or 0.0), _DP)
    target = round(est_total * factor, _DP)
    summed = round(sum(x["scheduled_value"] for x in items), _DP)
    residual = round(target - summed, _DP)
    # Placed on the largest item, where it is proportionally invisible, and reported so it can be
    # audited. Dropping it leaves a G703 whose column does not foot, which is a rejection.
    if residual and items:
        big = max(items, key=lambda x: x["scheduled_value"])
        big["scheduled_value"] = round(big["scheduled_value"] + residual, _DP)
        big["markup_amount"] = round(big["scheduled_value"] - big["estimate_amount"], _DP)
        summed = round(sum(x["scheduled_value"] for x in items), _DP)

    # The SECOND, independent accumulation. `fived` builds `by_element` per GlobalId in a separate
    # pass from `lines`, so totalling it and totalling the items are two different routes to the same
    # money. Agreement catches a regrouping that lost or double-counted an element; it says nothing
    # about whether the pricing was right, and this module does not pretend it does.
    by_element = est.get("by_element") or {}
    elem_total = round(sum(float(v.get("amount") or 0.0) for v in by_element.values()), _DP)

    excluded: list[dict[str, Any]] = []
    for reason, key in (("unpriced", "unpriced"), ("no rate", "no_rate"),
                        ("missing quantity", "missing_quantity")):
        rows = est.get(key) or []
        if rows:
            excluded.append({"reason": reason, "count": len(rows),
                             "guids": sorted({str(r.get("guid")) for r in rows
                                              if isinstance(r, dict) and r.get("guid")})[:200]})

    return {
        "items": items,
        "item_count": len(items),
        "grouping": grouping,
        "markup_pct": markup,
        # An SOV at cost is a real thing on a cost-plus job and a silent under-bill on a lump-sum one.
        # Stated either way so the caller cannot mistake the default for a decision.
        "at_cost": markup == 0.0,
        "estimate_total": est_total,
        "sov_total": summed,
        "residual_applied": residual,
        # CONSERVATION, not correctness — see the module docstring. Two checks against two
        # independently-built accumulations in the source.
        "reconciles": summed == target,
        "reconciles_by_element": abs(elem_total - est_total) < 0.01,
        "element_total": elem_total,
        "duplicate_guids": sorted(duplicate_guids),
        "excluded": excluded,
        # False whenever any scope was excluded. A schedule of values that covers only what happened
        # to price is smaller than the job and looks complete, because every line in it is correct.
        "covers_whole_model": not excluded,
        "truncated": truncated,
        "note": ("`reconciles` proves the regrouping lost no money, NOT that the estimate was right. "
                 "`covers_whole_model` is False whenever any scope could not be priced — those "
                 "elements are listed in `excluded` rather than dropped. `at_cost` means the "
                 "scheduled values carry no fee: correct for cost-plus, an under-bill on lump sum."),
    }
