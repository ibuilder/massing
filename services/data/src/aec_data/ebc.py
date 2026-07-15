"""CODE-EBC — existing-building scope-of-work classifier (IEBC Work Area Compliance Method).

Renovation / adaptive-reuse projects are governed by the **International Existing Building Code**, not the
new-construction path of the IBC. The IEBC's Work Area Compliance Method classifies a project's *scope of
work* — Repair · Alteration Level 1 / 2 / 3 · Change of Occupancy · Addition — and that classification
drives which chapters/provisions apply. This module owns only the **facts of law**: the classification
decision tree and the published section/chapter numbers (copyright-safe, exactly like [[codes]] /
CODE-1/2/3) — never the copyrighted code prose. Every result carries an AHJ-verify note and a "preliminary
classification, not a determination" disclaimer.

The classifier is a pure function of a structured scope (fully unit-testable); `from_model` derives a
first-guess scope from the model's phasing (`Massing_Phasing.Status` — existing vs new/demolish) and hands
it to `classify`, which the caller can then override with the real scope.

Section numbering follows the IEBC's stable structure (consistent across the 2015 / 2018 / 2021 editions):
Chapter 5 *Classification of Work* (§502 Repairs · §503 Alteration—Level 1 · §504 Alteration—Level 2 ·
§505 Alteration—Level 3 · §506 Change of Occupancy · §507 Additions), with the detailed requirements for
each classification in the Work-Area-Method chapters 6–13. These are facts (numbers + thresholds); the
requirement text lives in the code itself — deep-link, don't reproduce.
"""
from __future__ import annotations

from typing import Any

from . import codes

# Compliance methods the IEBC offers (IEBC §301.1). Facts: the three named methods + where each lives.
COMPLIANCE_METHODS = [
    {"key": "prescriptive", "name": "Prescriptive Compliance Method", "cite": "IEBC §301.1.1 / Chapter 4",
     "gist": "Treats alterations/additions largely under the IBC with limited existing-building relief."},
    {"key": "work-area", "name": "Work Area Compliance Method", "cite": "IEBC §301.1.2 / Chapters 5–13",
     "gist": "Classifies the scope of work (Repair · Alteration 1/2/3 · Change of Occupancy · Addition); "
             "requirements scale with the classification and the work-area ratio. The method used here."},
    {"key": "performance", "name": "Performance Compliance Method", "cite": "IEBC §301.1.3 / Chapter 14",
     "gist": "A scored evaluation of the whole building against fire-safety / means-of-egress / general "
             "safety parameters."},
]

# The Work-Area-Method classifications: classification-section (Ch 5) + the requirements chapter, as facts.
_CLASS = {
    "repair": {"label": "Repair", "class_cite": "IEBC §502", "req_cite": "IEBC Chapter 6",
               "gist": "Restoration/patching/replacement of damaged materials/elements to a pre-damage "
                       "condition; not covered by an alteration classification."},
    "alteration_1": {"label": "Alteration — Level 1", "class_cite": "IEBC §503", "req_cite": "IEBC Chapter 7",
                     "gist": "Removal and replacement or covering of existing materials/elements/equipment "
                             "with new that serve the same purpose (no reconfiguration)."},
    "alteration_2": {"label": "Alteration — Level 2", "class_cite": "IEBC §504", "req_cite": "IEBC Chapter 8",
                     "gist": "Reconfiguration of space, adding/eliminating any door or window, "
                             "reconfiguring/extending any system, or installing additional equipment — with "
                             "a work area at or below 50% of the building area. Applies Level 1 + Level 2."},
    "alteration_3": {"label": "Alteration — Level 3", "class_cite": "IEBC §505", "req_cite": "IEBC Chapter 9",
                     "gist": "Alteration work whose work area exceeds 50% of the aggregate building area. "
                             "Applies Level 1 + Level 2 + Level 3."},
    "change_occupancy": {"label": "Change of Occupancy", "class_cite": "IEBC §506", "req_cite": "IEBC Chapter 10",
                         "gist": "A change in the use/occupancy classification of a building or portion; can "
                                 "compound with an alteration level and trigger conformance to the new use."},
    "addition": {"label": "Addition", "class_cite": "IEBC §507", "req_cite": "IEBC Chapter 11",
                 "gist": "An increase in building area, aggregate floor area, height, or number of stories; "
                         "the addition itself is governed as new construction under the IBC."},
}

_WORK_AREA_THRESHOLD = 50.0  # percent of aggregate building area separating Level 2 from Level 3 (IEBC §505)

_DISCLAIMER = ("Preliminary scope classification for planning — not a code determination. The Authority "
               "Having Jurisdiction classifies the work and selects the compliance method; a project can "
               "combine classifications (e.g. an addition with a Level 2 alteration and a change of "
               "occupancy). Verify with the AHJ and a licensed design professional.")


def pathways() -> dict[str, Any]:
    """Reference catalog (facts): the three compliance methods + the Work-Area classifications and their
    citations. Feeds a UI picker and documents the decision space without reproducing code text."""
    return {
        "code": {"family": "IEBC", "name": codes.CODE_FAMILIES["IEBC"]["name"]},
        "methods": COMPLIANCE_METHODS,
        "classifications": [dict(key=k, **v) for k, v in _CLASS.items()],
        "work_area_threshold_pct": _WORK_AREA_THRESHOLD,
        "verify": codes._VERIFY,
        "disclaimer": _DISCLAIMER,
    }


def _cite(key: str) -> dict[str, str]:
    c = _CLASS[key]
    return {"classification": c["label"], "section": c["class_cite"], "requirements": c["req_cite"]}


def classify(
    *,
    jurisdiction: str | None = None,
    adds_area: bool = False,
    changes_occupancy: bool = False,
    reconfigures_space: bool = False,
    alters_openings: bool = False,        # adds/eliminates any door or window
    alters_systems: bool = False,         # reconfigures or extends any system (MEP, etc.)
    adds_equipment: bool = False,
    replaces_same_purpose: bool = False,  # removal & replacement/covering with same-purpose new
    repair_only: bool = False,            # restoration of damaged to pre-damage condition
    work_area_pct: float | None = None,   # work area ÷ aggregate building area, 0–100
) -> dict[str, Any]:
    """Classify an existing-building scope of work under the IEBC Work Area Compliance Method.

    Returns the **primary** classification plus every applicable classification (they nest: a Level 3
    alteration also carries Level 1 + Level 2), the driving citations, the inputs that triggered it, and
    the resolved IEBC edition for the jurisdiction. Pure and deterministic — the testable core."""
    # Resolve the adopted IEBC edition. States that pin the IBC generally pin the matching IEBC cycle;
    # otherwise fall back to the documented national baseline (codes.resolve carries the same logic).
    seeded = codes._ADOPTIONS.get((jurisdiction or "").strip().upper())
    edition = seeded["IBC"] if (seeded and "IBC" in seeded) else codes.BASELINE.get("IEBC")

    wa = None if work_area_pct is None else max(0.0, min(100.0, float(work_area_pct)))
    level2_triggers = {
        "reconfigures_space": reconfigures_space,
        "alters_openings": alters_openings,
        "alters_systems": alters_systems,
        "adds_equipment": adds_equipment,
    }
    fired = [k for k, v in level2_triggers.items() if v]

    applies: list[str] = []
    notes: list[str] = []

    # An alteration level is determined first (it can coexist with addition / change-of-occupancy).
    alteration: str | None = None
    if fired:
        if wa is not None and wa > _WORK_AREA_THRESHOLD:
            alteration = "alteration_3"
            applies = ["alteration_1", "alteration_2", "alteration_3"]
            notes.append(f"Work area {wa:.0f}% exceeds the {_WORK_AREA_THRESHOLD:.0f}% threshold → Level 3 "
                         "(applies Levels 1–3).")
        else:
            alteration = "alteration_2"
            applies = ["alteration_1", "alteration_2"]
            if wa is None:
                notes.append("No work-area ratio given — assumed at or below 50% (Level 2). Provide the "
                             "work-area/building-area ratio to distinguish Level 2 from Level 3.")
    elif replaces_same_purpose:
        alteration = "alteration_1"
        applies = ["alteration_1"]
    elif repair_only:
        alteration = None  # a pure repair is not an alteration

    # Choose the PRIMARY classification (the one that generally governs the heaviest requirements).
    primary: str
    if adds_area:
        primary = "addition"
        if alteration:
            notes.append(f"Also involves an alteration ({_CLASS[alteration]['label']}) to the existing "
                         "building beyond the addition — both apply.")
        if changes_occupancy:
            notes.append("Also a change of occupancy — Chapter 10 provisions apply.")
    elif changes_occupancy:
        primary = "change_occupancy"
        if alteration:
            notes.append(f"The change of occupancy is accompanied by an alteration "
                         f"({_CLASS[alteration]['label']}) — both apply.")
    elif alteration:
        primary = alteration
    elif repair_only:
        primary = "repair"
        applies = ["repair"]
    else:
        return {
            "ok": False,
            "classification": None,
            "reason": "No scope classified. Set at least one scope attribute (repair, a same-purpose "
                      "replacement, a Level-2 trigger, a change of occupancy, or an addition).",
            "code": {"family": "IEBC", "edition": edition, "jurisdiction": (jurisdiction or None)},
            "methods": COMPLIANCE_METHODS,
            "verify": codes._VERIFY,
            "disclaimer": _DISCLAIMER,
        }

    # Assemble the applicable set (primary + any nested alteration levels + co-occurring classifications).
    applicable_keys: list[str] = []
    for k in applies:
        if k not in applicable_keys:
            applicable_keys.append(k)
    for k in (primary, "change_occupancy" if changes_occupancy else None,
              "addition" if adds_area else None):
        if k and k not in applicable_keys:
            applicable_keys.append(k)

    triggered = list(fired)
    if replaces_same_purpose:
        triggered.append("replaces_same_purpose")
    if repair_only and primary == "repair":
        triggered.append("repair_only")
    if changes_occupancy:
        triggered.append("changes_occupancy")
    if adds_area:
        triggered.append("adds_area")

    return {
        "ok": True,
        "method": "Work Area Compliance Method",
        "method_cite": "IEBC §301.1.2",
        "classification": _CLASS[primary]["label"],
        "classification_key": primary,
        "gist": _CLASS[primary]["gist"],
        "applies": [_cite(k) for k in applicable_keys],
        "citations": [_cite(primary)],
        "triggers": triggered,
        "work_area_pct": wa,
        "code": {"family": "IEBC", "edition": edition, "name": codes.CODE_FAMILIES["IEBC"]["name"],
                 "jurisdiction": (jurisdiction or None),
                 "adoption_resolved": bool(seeded)},
        "methods": COMPLIANCE_METHODS,
        "notes": notes,
        "verify": codes._VERIFY,
        "disclaimer": _DISCLAIMER,
    }


def from_model(model, *, jurisdiction: str | None = None, **overrides) -> dict[str, Any]:
    """Derive a first-guess IEBC scope from the model's phasing and classify it. Existing elements make it
    an existing-building project; new/demolish elements alongside existing imply reconfiguration (a Level-2
    trigger), and their share of the model estimates the work-area ratio. Every inferred field is
    overridable via keyword args (the real scope always beats the geometry guess). Returns the `classify`
    result plus the `inferred` scope and a `basis` explanation."""
    from .edit import phase_summary

    summ = phase_summary(model)
    c = summ.get("counts", {})
    existing = int(c.get("EXISTING", 0))
    new = int(c.get("NEW", 0))
    demo = int(c.get("DEMOLISH", 0))
    worked = new + demo
    denom = existing + worked

    inferred: dict[str, Any] = {}
    basis: list[str] = []
    if existing == 0 and worked == 0:
        basis.append("No elements are phased (Massing_Phasing.Status) — cannot infer a scope from the "
                     "model; supply the scope explicitly.")
    else:
        if existing > 0 and worked > 0:
            inferred["reconfigures_space"] = True
            basis.append(f"{existing} existing + {worked} new/demolished element(s) → an alteration with "
                         "reconfiguration (Level-2 trigger).")
            if denom > 0:
                pct = round(100.0 * worked / denom, 1)
                inferred["work_area_pct"] = pct
                basis.append(f"Estimated work-area ratio ≈ {pct:.0f}% (worked ÷ total elements) — a rough "
                             "proxy for area; override with the true work-area/building-area ratio.")
        elif existing > 0 and worked == 0:
            inferred["repair_only"] = True
            basis.append(f"{existing} existing element(s), no new/demolished work → treated as a repair; "
                         "set the real scope if it's an alteration.")

    scope = {**inferred, **overrides}  # explicit overrides beat the phasing guess
    result = classify(jurisdiction=jurisdiction, **scope)
    result["inferred"] = inferred
    result["basis"] = basis
    result["phase_counts"] = c
    return result
