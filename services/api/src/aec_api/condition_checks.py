"""R22-ENTITLEMENT ② — checking approval conditions against the model, and the unit it will not guess.

Slice ① turned `entitlement.conditions` from one textarea into tracked items with topics and
quantities. This is the clause the ring entry actually names: **conditions carried into the model as
constraints**. It checks the two topics the model can genuinely answer today and refuses the rest.

What the model answers: **height** (from `drawings.storey_elevations`) and **parking** (a count of
parking spaces). Setback needs a property line and is not attempted — `parcel_geometry` exists but a
setback check without a surveyed boundary is a number dressed as a compliance finding.

Three refusals, and the second is the one that would otherwise cause real harm:

1. **a condition this cannot check is `not_checkable`, never passing.** Same rule as slice ①'s
   `unparsed`: a condition reported as satisfied because nobody could evaluate it is a building put
   up out of compliance while the report said it was fine. `not_checkable` names why;
2. **units are converted explicitly and BOTH are shown.** A condition says "45 feet"; the model is
   in metres. Converting silently is exactly how a 45 ft height limit becomes a 45 m one — a
   three-fold error that reads as a pass. Every comparison reports the condition value, the model
   value, and the unit each was in;
3. **no model is `not_checkable`, not compliant.** An absent model cannot demonstrate compliance,
   and treating "nothing to compare against" as "nothing wrong" is the same failure as an empty
   estimate ledger reporting 100% documented.
"""
from __future__ import annotations

from typing import Any

M_PER_FT = 0.3048

VERDICT_PASS = "within_limit"
VERDICT_FAIL = "exceeds_limit"
VERDICT_NOT_CHECKABLE = "not_checkable"

#: Topics this can evaluate. Anything else is reported as not_checkable rather than attempted —
#: see the module docstring on setbacks.
CHECKABLE_TOPICS = ("height", "parking")

_LENGTH_UNITS = {"ft": M_PER_FT, "feet": M_PER_FT, "foot": M_PER_FT,
                 "m": 1.0, "metres": 1.0, "meters": 1.0}
_STOREY_UNITS = {"storey", "storeys", "storey s", "story", "stories"}
_COUNT_UNITS = {"spaces", "space", "units", "unit"}


def _to_metres(value: float, unit: str) -> tuple[float | None, str]:
    u = (unit or "").lower()
    if u in _LENGTH_UNITS:
        return value * _LENGTH_UNITS[u], u
    return None, u


def check_condition(cond: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one parsed condition (from `approval_conditions.parse`) against model facts.

    `facts` is `{height_m, storeys, parking_spaces}` — any may be None, and a None fact makes the
    condition `not_checkable` rather than passing.
    """
    base = {"seq": cond.get("seq"), "topic": cond.get("topic"), "text": cond.get("text")}
    topic = cond.get("topic")
    quantities = cond.get("quantities") or []

    if topic not in CHECKABLE_TOPICS:
        return {**base, "verdict": VERDICT_NOT_CHECKABLE,
                "reason": (f"topic {topic!r} is not one the model can answer. Checkable topics are "
                           f"{', '.join(CHECKABLE_TOPICS)}; a setback check without a surveyed "
                           "property line would be a number dressed as a compliance finding")}
    if not quantities:
        return {**base, "verdict": VERDICT_NOT_CHECKABLE,
                "reason": "the condition carries no quantity to compare against"}

    for q in quantities:
        unit = str(q.get("unit") or "").lower()
        value = float(q.get("value"))

        if topic == "height":
            if unit in _STOREY_UNITS:
                model_v, mu = facts.get("storeys"), "storeys"
            else:
                metres, _ = _to_metres(value, unit)
                if metres is None:
                    continue
                value, model_v, mu = metres, facts.get("height_m"), "m"
            if model_v is None:
                return {**base, "verdict": VERDICT_NOT_CHECKABLE,
                        "reason": f"the model reports no {mu} — an absent model fact cannot "
                                  "demonstrate compliance, so this is unchecked, not satisfied"}
            ok = float(model_v) <= value + 1e-9
            return {**base, "verdict": VERDICT_PASS if ok else VERDICT_FAIL,
                    "condition_value": round(value, 4), "condition_unit": mu,
                    "condition_as_written": f"{q.get('value')} {q.get('unit')}",
                    "model_value": round(float(model_v), 4), "model_unit": mu,
                    "reason": (f"condition allows {value:.4g} {mu} (written as "
                               f"{q.get('value')} {q.get('unit')}); the model is "
                               f"{float(model_v):.4g} {mu}. Both values and both units are shown "
                               "because converting silently is how a 45 ft limit becomes a 45 m one")}

        if topic == "parking":
            if unit not in _COUNT_UNITS:
                continue
            model_v = facts.get("parking_spaces")
            if model_v is None:
                return {**base, "verdict": VERDICT_NOT_CHECKABLE,
                        "reason": "the model reports no parking space count — unchecked, not satisfied"}
            ok = float(model_v) >= value - 1e-9      # parking conditions are minimums
            return {**base, "verdict": VERDICT_PASS if ok else VERDICT_FAIL,
                    "condition_value": value, "condition_unit": "spaces",
                    "condition_as_written": f"{q.get('value')} {q.get('unit')}",
                    "model_value": float(model_v), "model_unit": "spaces",
                    "reason": (f"condition requires at least {value:.4g} space(s); the model has "
                               f"{float(model_v):.4g}. Parking conditions are read as MINIMUMS — "
                               "the opposite direction to a height limit, and reading one as the "
                               "other inverts the finding")}

    return {**base, "verdict": VERDICT_NOT_CHECKABLE,
            "reason": (f"no quantity in this condition is in a unit the {topic} check understands "
                       f"({[q.get('unit') for q in quantities]})")}


def check_all(conditions: list[dict], facts: dict[str, Any] | None = None) -> dict[str, Any]:
    """Check parsed conditions against model facts, counting what could not be checked."""
    facts = facts or {}
    rows = [check_condition(c, facts) for c in conditions or []]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    failing = [r for r in rows if r["verdict"] == VERDICT_FAIL]
    return {
        "checks": rows, "counts": counts,
        "exceeds": failing, "exceeds_count": len(failing),
        "not_checkable_count": counts.get(VERDICT_NOT_CHECKABLE, 0),
        "checked_count": counts.get(VERDICT_PASS, 0) + len(failing),
        "facts": dict(facts),
        "note": ("a condition that could not be evaluated is NOT_CHECKABLE, never passing — a "
                 "condition reported satisfied because nobody could evaluate it is a building put "
                 "up out of compliance while the report said it was fine."),
    }


def model_facts(model) -> dict[str, Any]:
    """The facts a condition check can use, read from an opened IFC model.

    Returns None for anything the model does not answer rather than a zero — a zero parking count
    and "this model has no parking information" are different claims, and only the first would make
    a minimum-parking condition fail honestly.
    """
    from aec_data import drawings

    facts: dict[str, Any] = {"height_m": None, "storeys": None, "parking_spaces": None}
    try:
        storeys = drawings.storey_elevations(model)
    except Exception:                            # noqa: BLE001 — an unreadable model yields no facts
        storeys = []
    if storeys:
        facts["storeys"] = len(storeys)
        elevs = [float(s.get("elevation") or 0.0) for s in storeys]
        if elevs:
            facts["height_m"] = round(max(elevs), 4)
    try:
        spaces = model.by_type("IfcSpace")
        parking = [s for s in spaces
                   if "park" in str(getattr(s, "Name", "") or "").lower()
                   or "park" in str(getattr(s, "LongName", "") or "").lower()]
        if parking:
            facts["parking_spaces"] = len(parking)
    except Exception:                            # noqa: BLE001
        pass
    return facts
