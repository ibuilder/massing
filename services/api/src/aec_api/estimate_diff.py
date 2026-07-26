"""R25-ESTIMATE-DIFF — two estimates over two model versions, diffed by GlobalId.

The provenance thesis applied to money. "The estimate went up $340k" is not information; *which
elements* moved it, and *why*, is. Because both estimates key on GlobalId, the diff can attribute
every dollar of the change to a specific element and a specific cause — which is the whole reason the
platform refuses to identify elements any other way.

**Four causes, and they are genuinely different questions.**

* `added` — an element exists now that did not before. Scope grew.
* `removed` — an element is gone. Scope shrank, or something was deleted.
* `requantified` — the same element and rate, a different quantity. The design changed.
* `repriced` — the same element and quantity, a different rate. The *estimate* changed, not the
  building. This is the one people most want separated: a number that moved because a rate was
  updated is a commercial decision; one that moved because a wall got longer is a design event.
* `both` — quantity *and* rate moved. Not a leftover bucket: apportioning such a delta across the
  other two produces two numbers that add up correctly and neither of which is true.

**It diffs `by_element`, and refuses to invent it.** The first version of this module reconstructed
per-element quantities by dividing a line's total evenly across its GlobalIds. That is a fabrication,
and it failed on the most ordinary edit there is: add one wall to an existing line and every *other*
wall in that line reports as a design change, while the new wall is attributed the average rather
than its own quantity. `reconciles` stayed true throughout, because the invented numbers still summed
correctly — a worked example of why a self-consistency check is not a correctness check.

`fived.estimate` now emits `by_element` with the exact figures. When an input lacks it — a payload
assembled by hand, or an older stored estimate — this **does not fall back to apportionment**. It
diffs at line level instead, where quantity and rate are exact, and says so in `granularity`. A
coarser true answer beats a finer invented one.
"""
from __future__ import annotations

from typing import Any

#: Why a line's cost changed. Ordered as a reader should read them: scope, then design, then commerce.
CAUSES = ("added", "removed", "requantified", "repriced", "both")

CAUSE_MEANS = {
    "added": "Priced now, absent before — scope grew",
    "removed": "Priced before, absent now — scope shrank, or something was deleted",
    "requantified": "Same rate, different quantity — the design changed",
    "repriced": "Same quantity, different rate — the estimate changed, not the building",
    "both": "Quantity AND rate moved — reported as one change rather than split into two half-truths",
}

#: Money below this is rounding, not change. Named rather than inline, because an unstated epsilon
#: turns float noise into a line item on a change report.
EPSILON = 0.005

#: Quantities are not money and must not share money's epsilon. A quantity may be square metres,
#: cubic metres or a count, so the test is RELATIVE — 0.001 m³ is a real change to a 0.01 m³ element
#: and noise on a 900 m³ pour. Comparing a quantity against a currency threshold is what let a pure
#: design change (identical rates on both sides) be reported as `repriced`.
QTY_REL_TOL = 1e-6
QTY_ABS_TOL = 1e-9

#: Decimal places at which two rates count as "the same rate" when comparing the SET of rates in a
#: merged line group. Far finer than any real rate change; exists only so float noise in a stored
#: payload cannot read as a repricing.
_RATE_DP = 6

#: Items listed per cause. `truncated` is set when it bites — a capped list whose `count` covers the
#: whole set makes any UI that totals the items disagree with the reported delta, with no way to tell.
MAX_ITEMS = 500


def _moved(a: float, b: float) -> bool:
    """Did a quantity actually change? Relative, with an absolute floor for values near zero."""
    return abs(a - b) > max(QTY_ABS_TOL, QTY_REL_TOL * max(abs(a), abs(b)))


def _elements(est: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    """The estimate's exact per-element facts, or None when it does not carry them.

    None is the honest answer, not an invitation to reconstruct. See the module docstring.
    """
    by = est.get("by_element")
    if not isinstance(by, dict) or not by:
        return None
    # Underscore-prefixed keys are this module's own internals (`_rate_set`), and `by_element` arrives
    # from the request body — so they are stripped rather than trusted. Otherwise a caller could hand
    # in a `_rate_set` and steer its own cause attribution.
    return {str(g): {k: x for k, x in v.items() if not str(k).startswith("_")}
            for g, v in by.items() if isinstance(v, dict)}


def _lines(est: dict[str, Any]) -> dict[tuple, dict[str, Any]]:
    """Line-level facts keyed by (code, basis) — the coarse view, exact by construction.

    Duplicate keys **accumulate** rather than overwrite. Two lines with the same code and basis are
    two costs against that code; keeping only the last would drop money silently, which is precisely
    the failure this module exists to catch.

    **A group holding several rates reports its BLENDED rate** — total cost over total quantity.
    `fived.estimate` keys its own lines on (code, basis, unit_cost) so that layering ("later rules
    win") can price one code at several rates, and those lines merge here. Reporting `unit_cost=None`
    for such a group looked conservative and was not: `_classify` then saw neither a rate movement nor
    a quantity movement and attributed a pure repricing to nothing at all — $30 of real change
    reported as zero changes with `reconciles` false.

    The rate is deliberately NOT part of the key. Putting it there does make the money reconcile, but
    it reclassifies a repricing as a `removed` line plus an `added` one — scope change, which is the
    single distinction this module exists to draw. A blended rate is not a fabrication of the kind an
    apportioned per-element quantity would be: it is exactly what this code cost per unit, derived
    from two exact aggregates. It is computed ONLY when a group actually holds more than one rate, so
    the ordinary single-rate line keeps its own rate and never goes near a division.
    """
    out: dict[tuple, dict[str, Any]] = {}
    for ln in est.get("lines") or []:
        key = (str(ln.get("code") or ""), str(ln.get("basis") or ""))
        cur = out.setdefault(key, {"code": key[0], "basis": key[1], "quantity": 0.0, "amount": 0.0,
                                   "unit_cost": None, "rates": set()})
        cur["quantity"] += float(ln.get("quantity") or 0.0)
        cur["amount"] += float(ln.get("amount") or 0.0)
        raw = ln.get("unit_cost")
        # An absent rate is NOT 0.0 — an unpriced line and a line priced at zero are different claims,
        # and folding them together is the conflation `fived` refuses elsewhere.
        cur["rates"].add(None if raw is None else float(raw))
    for v in out.values():
        rates = v.pop("rates")
        # The SET of rates in the group, quantised so float noise cannot masquerade as a repricing.
        # `_classify` prefers this over the blended rate when deciding whether a rate moved, because a
        # blended rate also moves when the MIX shifts: raise the quantity of the cheaper sub-line and
        # the blend drops without anybody repricing anything. Comparing the sets separates the two —
        # same rates, different blend is a design change, not a commercial one.
        v["_rate_set"] = frozenset(None if r is None else round(r, _RATE_DP) for r in rates)
        if len(rates) == 1:
            v["unit_cost"] = rates.pop()                  # one rate across the group: exact, no maths
        elif v["quantity"]:
            v["unit_cost"] = v["amount"] / v["quantity"]  # several rates: the exact blended rate
        else:
            # Several rates and nothing to divide by. No rate can be stated, and `_classify` treats
            # None on both sides as "no rate movement" — so such a delta stays unattributed and shows
            # up in `residual` rather than being given an invented cause.
            v["unit_cost"] = None
        v["amount"] = round(v["amount"], 2)
    return out


def _classify(was: dict[str, Any], now: dict[str, Any]) -> tuple[str, float] | None:
    """The cause and delta for one key present on both sides, or None when nothing moved.

    Order matters: the causes are decided from what actually moved, **then** the delta is taken. The
    first version skipped on a small money delta *before* classifying, so a compensating change —
    quantity doubled, rate halved — was reported as unchanged. That is the textbook `both` case being
    asserted not to exist.
    """
    q_moved = _moved(float(was.get("quantity") or 0.0), float(now.get("quantity") or 0.0))
    s_was, s_now = was.get("_rate_set"), now.get("_rate_set")
    if s_was is not None and s_now is not None:
        # Line granularity: ask whether the RATES changed, not whether the blend did. A merged group's
        # blended rate also moves when the mix shifts, which would report a pure quantity change as
        # `both` and imply a commercial decision that never happened.
        r_moved = s_was != s_now
    else:
        # Element granularity: one element carries one rate, so comparing it directly is exact.
        r_was, r_now = was.get("unit_cost"), now.get("unit_cost")
        r_moved = (r_was is None) != (r_now is None) or (
            r_was is not None and r_now is not None and abs(float(r_was) - float(r_now)) > EPSILON)
    delta = round(float(now.get("amount") or 0.0) - float(was.get("amount") or 0.0), 2)
    if not q_moved and not r_moved:
        # Nothing that can move a cost moved. A residual delta here is rounding, and the
        # reconciliation reports it rather than this inventing a cause for it.
        return None
    if q_moved and r_moved:
        return "both", delta
    return ("requantified" if q_moved else "repriced"), delta


def diff(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:
    """Diff two `fived.estimate` payloads.

    Per element when both sides carry `by_element`; per cost line otherwise, with `granularity`
    saying which. Returns the changes by cause plus a **reconciliation**: the attributed deltas must
    add back to the difference in totals. That check is not a correctness proof — the first version
    of this module reconciled perfectly while fabricating every per-element figure — but a diff that
    fails it is definitely wrong, and one that passes has at least not lost money.
    """
    before, after = before or {}, after or {}
    ea, eb = _elements(before), _elements(after)
    element_level = ea is not None and eb is not None
    granularity = "element" if element_level else "line"
    a: dict[Any, dict[str, Any]] = ea if element_level else _lines(before)  # type: ignore[assignment]
    b: dict[Any, dict[str, Any]] = eb if element_level else _lines(after)   # type: ignore[assignment]

    changes: dict[str, list[dict[str, Any]]] = {c: [] for c in CAUSES}

    def ident(key: Any, fact: dict[str, Any]) -> dict[str, Any]:
        return ({"guid": key, "code": fact.get("code")} if element_level
                else {"code": fact.get("code"), "basis": fact.get("basis")})

    def amount(fact: dict[str, Any]) -> float:
        """A fact's amount, treating an absent one as zero rather than raising.

        `by_element` is caller-supplied on this path — the module docstring anticipates "a payload
        assembled by hand, or an older stored estimate" — so a missing `amount` is bad input, not a
        server fault. A bare `fact["amount"]` raised KeyError, which is not in the route's caught
        tuple, so it escaped as a 500 and wrote an error-log row per attempt.
        """
        return float(fact.get("amount") or 0.0)

    for key in sorted(set(a) | set(b), key=str):
        was, now = a.get(key), b.get(key)
        if was is None and now is not None:
            changes["added"].append({**ident(key, now), "delta": round(amount(now), 2),
                                     "to": round(amount(now), 2)})
            continue
        if now is None and was is not None:
            changes["removed"].append({**ident(key, was), "delta": -round(amount(was), 2),
                                       "from": round(amount(was), 2)})
            continue
        if was is None or now is None:
            continue
        got = _classify(was, now)
        if got is None:
            continue
        cause, delta = got
        changes[cause].append({
            **ident(key, now), "delta": delta,
            "from": round(amount(was), 2), "to": round(amount(now), 2),
            "quantity_from": round(float(was.get("quantity") or 0.0), 6),
            "quantity_to": round(float(now.get("quantity") or 0.0), 6),
            "rate_from": was.get("unit_cost"), "rate_to": now.get("unit_cost"),
        })

    by_cause = {}
    for c in CAUSES:
        items = sorted(changes[c], key=lambda x: -abs(x["delta"]))
        by_cause[c] = {"cause": c, "means": CAUSE_MEANS[c], "count": len(items),
                       "delta": round(sum(x["delta"] for x in items), 2),
                       "items": items[:MAX_ITEMS],
                       # stated, so a UI totalling `items` can tell why it disagrees with `delta`
                       "truncated": max(0, len(items) - MAX_ITEMS)}

    attributed = round(sum(v["delta"] for v in by_cause.values()), 2)
    t_before = round(float(before.get("total") or 0.0), 2)
    t_after = round(float(after.get("total") or 0.0), 2)
    total_delta = round(t_after - t_before, 2)
    changed = sum(v["count"] for v in by_cause.values())
    residual = round(total_delta - attributed, 2)

    return {
        "granularity": granularity,
        "before_total": t_before,
        "after_total": t_after,
        "total_delta": total_delta,
        "attributed": attributed,
        "residual": residual,
        # Rounding per key then summing cannot always land on a total rounded once, so a cent per
        # changed key is allowed — and the residual is REPORTED either way rather than asserted away.
        "reconciles": abs(residual) <= max(EPSILON, 0.01 * max(changed, 1)),
        "causes": [by_cause[c] for c in CAUSES],
        "changed": changed,
        "unchanged": len(set(a) & set(b)) - sum(
            by_cause[c]["count"] for c in ("requantified", "repriced", "both")),
        "note": ("Every delta is attributed to ONE cause; `both` is the honest answer when quantity "
                 "and rate move together, not a leftover bucket. `granularity` is `element` only when "
                 "BOTH estimates carry `by_element` — otherwise this diffs whole cost lines rather "
                 "than inventing each element's share of one. `reconciles` says the parts add back to "
                 "the whole; it is a floor, not a proof of correctness."),
    }
