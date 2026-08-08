"""LOD (Level of Development) — the target matrix + an achieved-LOD assessment of the loaded model.

The target matrix is authored in the `lod_target` register (stage x discipline x element-category ->
target LOD 100..500); when it is empty the RIBA/AIA stage defaults apply.

Achieved LOD is read from the element's **geometry**, along the five ISO 7817-1 aspects — detail,
dimensionality, location, appearance, parametric behavior. A band requires ALL of them, so the
result is a minimum and never an average. Where an aspect cannot be read from the served index it
widens the CEILING rather than lowering the band, and the assessment reports both: the gap between
them is unread model, not missing model.

Until v0.3.901 this scored LOIN facet completeness instead and reported the answer as a geometry
band — a well-tagged bounding box came out at LOD 350. That reading survives under its own name
(`information_score`), because it was a useful measurement wearing the wrong label.

LOD 500 (a field-verified as-built condition) is never inferred: it is read from the verification
stamp, and an element measured outside tolerance is a finding rather than a handover.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import classification
from . import modules as me
from .openbim_quality import LOIN_FACETS, _facets

LOD_BANDS = ["LOD 100", "LOD 200", "LOD 300", "LOD 350", "LOD 400", "LOD 500"]
#: DELETED in v0.3.901, and named here rather than silently dropped because it is the defect:
#: `_FACETS_TO_LOD = {0: "LOD 100", ..., 4: "LOD 350", 5: "LOD 400"}` turned a count of LOIN facets
#: into a geometry band. A well-tagged bounding box scored LOD 350 by it. Nothing maps a count to a
#: band any more — see `aspects()`. Left as a comment so a future reader searching for the old
#: behaviour finds why it went rather than an absence.
_LOD_RANK = {b: i for i, b in enumerate(LOD_BANDS)}

# RIBA / AIA stage progression used when the register carries no explicit targets.
_DEFAULT_MATRIX = [
    {"phase": "Concept / SD", "target_lod": "LOD 200"},
    {"phase": "Design Development", "target_lod": "LOD 300"},
    {"phase": "Construction Docs", "target_lod": "LOD 350"},
    {"phase": "Construction", "target_lod": "LOD 400"},
    {"phase": "As-built", "target_lod": "LOD 500"},
]


def _d(r: dict) -> dict:
    return r.get("data") or r


def matrix(db: Session, pid: str) -> dict[str, Any]:
    """The target LOD matrix from the register, or the stage defaults when none are authored."""
    rows = me.list_records(db, "lod_target", pid, limit=100000) if "lod_target" in me.TABLES else []
    # LOD-ELEMENT-TABLE: `ifc_class` and `uniformat` are what make a target ADDRESSABLE to an
    # element. Projected here as well as stored, because `target_for` reads this list — a field the
    # register accepts and this projection drops is a field the user can fill in and nothing uses.
    targets = [{"element_category": _d(r).get("element_category", ""), "discipline": _d(r).get("discipline", ""),
                "ifc_class": _d(r).get("ifc_class", ""), "uniformat": _d(r).get("uniformat", ""),
                "phase": _d(r).get("phase", ""), "target_lod": _d(r).get("target_lod", ""),
                "state": r.get("workflow_state", "")} for r in rows]
    return {
        "targets": targets, "default": _DEFAULT_MATRIX, "using_default": not targets,
        "note": "Target LOD by stage / discipline / element category. With no targets registered the "
                "RIBA/AIA stage defaults apply (SD LOD200 -> DD LOD300 -> CD LOD350 -> Construction "
                "LOD400 -> As-built LOD500).",
    }


# --- LOD-ELEMENT-TABLE ------------------------------------------------------------------------
# A target matrix nothing could be COMPARED TO. `lod_target` records carried
# {element_category, discipline, phase, target_lod} — `element_category` is free text, so no target
# could be joined to an element, and `assess()` returned the targets and the achieved distribution
# side by side without ever putting them together. A team could author "curtain wall reaches LOD 350
# at CD", press assess, and be told a distribution that could not answer the question they asked.
#
# The industry practice the 2025 spec's Part II encodes is a MODEL ELEMENT TABLE: one row per
# element type keyed to a classification, with a target at each milestone. So targets become
# addressable — by IFC class, by Uniformat code, or by discipline — and resolution is
# MOST-SPECIFIC-WINS, because that is the whole reason per-element targets exist: at CD a curtain
# wall is expected at 350 while an interior partition is expected at 300, and one number for the
# stage makes both wrong.
#
# NOTHING FROM THE BIMForum TABLE IS SHIPPED. Part II is CC BY-NC and says its own rows are
# "examples ... intended to be customized by the user". The platform provides the structure; the
# project authors the content.
_TARGET_SPECIFICITY = ("ifc_class", "uniformat", "discipline")


def target_for(e: dict, targets: list[dict], phase: str) -> dict | None:
    """The most specific authored target that applies to one element at one stage, or None.

    Returns the whole target row rather than just its band so a caller can say WHICH rule decided —
    "short of the curtain-wall rule" is actionable where "short of target" is not.
    """
    ifc = (e.get("ifc_class") or "").strip().lower()
    uni = str(e.get("classification") or "").strip().lower()
    code = classification.discipline_of_ifc_class(e.get("ifc_class") or "")
    disc = (classification.discipline_name(code) if code else "").strip().lower()
    best: dict | None = None
    best_rank = len(_TARGET_SPECIFICITY)
    for t in targets:
        if (t.get("phase") or "").strip() != phase:
            continue
        for rank, key in enumerate(_TARGET_SPECIFICITY):
            want = str(t.get(key) or "").strip().lower()
            if not want:
                continue
            got = {"ifc_class": ifc, "uniformat": uni, "discipline": disc}[key]
            # Uniformat is matched by PREFIX: a target on "B2010" covers "B2010.10", which is how
            # the classification tree is meant to be read. Exact-only matching would silently skip
            # every element carrying a more precise code than the rule was written at.
            hit = got.startswith(want) if key == "uniformat" else got == want
            if hit and rank < best_rank:
                best, best_rank = t, rank
    return best


# ── LOD 500: the field-verification bridge ───────────────────────────────────────────────────────
# `edit_asbuilt.verify_asbuilt` stamps `Massing_AsBuilt` onto elements, and `asbuilt_summary` counted
# them — but the LOD assessment never read it, so a model with every element field-verified still
# reported "LOD 400, capped". The assertion existed and the reader ignored it.
#
# BIMForum is explicit on two points this encodes:
#   1. LOD 500 is NOT "more detail than 400". It is a *field-verified as-built* condition, and it
#      applies to what exists rather than to what was designed. So it is not earned by adding
#      geometry; it is earned by someone going and looking.
#   2. The accuracy of an LOD 500 element "must be specified by some means other than LOD 100-400" —
#      the LOD number itself says nothing about how closely the model matches the building. A
#      verification with no stated accuracy is therefore an *incomplete* assertion, and this reports
#      it as such rather than counting it as a pass.
ASBUILT_PSET = "Massing_AsBuilt"
ASBUILT_DIM_PSET = "Massing_AsBuiltDim"


def verification(e: dict) -> dict[str, Any]:
    """Read one element's as-built verification from the served index.

    Two readings of accuracy, deliberately separate. `accuracy_stated` is the weaker one that
    callers already depend on: a recorded measurement is evidence of accuracy for the dimension it
    measured, and a bare "VERIFIED" flag is not. `accuracy_grade` is the standard's actual
    requirement — "declared" only when the element carries a level label AND a tolerance a
    downstream reader can act on, "derived" when a deviation is computable but nobody said to what
    accuracy the survey was performed, "none" otherwise.
    """
    psets = e.get("psets") if isinstance(e.get("psets"), dict) else {}
    ab = psets.get(ASBUILT_PSET) or {}
    dims = psets.get(ASBUILT_DIM_PSET) or {}
    verified = str(ab.get("Status") or "").upper() == "VERIFIED"
    tol = str(dims.get("WithinTolerance") or "").lower()
    # LOD-500-LOA. The LOD 500 definition requires that the element's accuracy "shall be noted or
    # attached to the Model Element" — the LOD number itself says nothing about how closely the
    # model matches the building. BIMForum points at USIBD's Level of Accuracy specification for
    # the purpose.
    #
    # WHAT IS RECORDED HERE, AND WHY IT IS NOT A LOOKUP TABLE. The declared level is free text: the
    # project's BEP names its own scale, and USIBD's tolerance ranges are theirs to license, not
    # ours to embed. So a declaration is only accepted as an accuracy statement when it carries a
    # NUMBER a downstream reader can act on — a level label alone is a name, and "LOA30" means
    # nothing to a system that cannot resolve it. Requiring the tolerance makes the claim
    # self-contained and sidesteps the licence question entirely.
    loa = str(dims.get("LOA") or ab.get("LOA") or "").strip() or None
    try:
        tol_mm = float(dims.get("Tolerance_mm") or ab.get("Tolerance_mm") or 0) or None
    except (TypeError, ValueError):
        tol_mm = None
    measured = any(str(k).endswith("_Measured") for k in dims)
    if loa and tol_mm and tol_mm > 0:
        grade = "declared"       # the spec's requirement, met
    elif measured:
        grade = "derived"        # a deviation is computable, but no level was stated
    else:
        grade = "none"
    return {
        "verified": verified,
        "method": str(ab.get("Method") or "") or None,
        "verified_by": str(ab.get("VerifiedBy") or "") or None,
        "verified_date": str(ab.get("VerifiedDate") or "") or None,
        # UNCHANGED semantics, deliberately: a recorded measurement is evidence of accuracy for the
        # dimension it measured, and callers already depend on that reading. The stronger claim the
        # standard asks for is `accuracy_grade`, added beside it rather than folded into it.
        "accuracy_stated": measured,
        "loa_level": loa,
        "loa_tolerance_mm": tol_mm,
        "accuracy_grade": grade,
        "within_tolerance": None if tol not in ("true", "false") else (tol == "true"),
    }


# --- LOD-ASPECTS ------------------------------------------------------------------------------
# LOD is a claim about GEOMETRY. Until v0.3.901 this module inferred it from LOIN facet
# completeness - geometry / type / classification / properties / quantities - and nothing on that
# path looked at a shape. Measured before the fix: a generic IfcWall box carrying a classification,
# a Pset and a Qto scored **LOD 350**; strip the property and quantity sets, changing not one
# vertex, and the same box scored **LOD 200**. Two bands on tagging alone, on a number that goes
# into contracts and BIM execution plans. (`_facets` also returns `geometry: True` unconditionally,
# so one of its five was a constant.)
#
# The 2025 LOD Specification states each band against **ISO 7817-1 Part 1** aspects - Detail,
# Dimensionality, Location, Appearance, Parametric Behavior - and is explicit that requirements are
# minimums, are cumulative, and must ALL be met: an accurately detailed element located
# approximately "can be no higher than LOD 200". So a band is the MINIMUM across the aspects, never
# an average and never a count.
#
# WHAT THIS DELIBERATELY DOES NOT DO. It does not encode a band-to-aspect-value table. The BIMForum
# document is CC BY-NC-ND (Part I) / CC BY-NC (Part II) and cannot be reproduced or adapted here.
# What is used is what is not BIMForum's to license: the aspect NAMES from ISO 7817-1 and the AIA
# band numbers. Every threshold below is derived from IFC's own representation vocabulary.
ASPECTS = ("detail", "dimensionality", "location", "appearance", "parametric_behavior")

#: Representation types that can only stand for a placeholder, whatever else is true of the element.
_PLACEHOLDER_REPS = {"BoundingBox", "Box", "Point", "Curve2D", "GeometricCurveSet", "Annotation2D"}
#: Representation types that describe a resolved, buildable solid rather than a swept profile.
_RESOLVED_REPS = {"Brep", "AdvancedBrep", "Clipping", "CSG", "Tessellation", "SurfaceModel"}
#: Representation types that describe real 3D extent but not resolved detail.
_SOLID_REPS = {"SweptSolid", "AdvancedSweptSolid", "MappedRepresentation", "SolidModel"}


def _aspect(supported: str, cap: str | None, why: str) -> dict[str, Any]:
    """One aspect's reading.

    `supported` is what the evidence POSITIVELY demonstrates. `cap` is a limit the evidence PROVES —
    `None` means "no evidence of a limit", which is emphatically not the same as "no limit".

    Keeping those apart is the whole correction. The first draft of this module folded them into one
    `supported` value and took the minimum across all five aspects; because Location and
    Dimensionality accuracy are unreadable from the index, both sat at LOD 200 forever and **every
    element in every model scored LOD 200**. A scorer that returns one answer is not a scorer. An
    aspect nobody can read must not drag the floor down — it must widen the CEILING and say so.
    """
    return {"supported": supported, "cap": cap, "why": why, "decidable": cap is not None}


def aspects(e: dict) -> dict[str, dict[str, Any]]:
    """The five ISO 7817-1 aspects for one element.

    The honest limit, stated once: the index carries how a shape is BUILT, not how ACCURATE it is.
    Nothing here distinguishes an approximately-placed wall from a precisely-placed one — so Location
    and Dimensionality report a cap only when the evidence PROVES one (no placement at all; extents
    that are a box and nothing else) and otherwise decline to constrain the band.
    """
    reps = {str(t) for t in (e.get("rep_types") or [])}
    unknown_shape = not reps

    # DETAIL — the axis IFC answers directly, and the one that DRIVES the band. A bounding box is a
    # placeholder; a swept solid conveys design intent; a Brep/Clipping/Tessellation is resolved.
    if unknown_shape:
        detail = _aspect("LOD 100", None, "no readable shape representation")
    elif reps & _RESOLVED_REPS:
        detail = _aspect("LOD 350", None,
                         "resolved solid (" + ", ".join(sorted(reps & _RESOLVED_REPS)) + ")")
    elif reps & _SOLID_REPS:
        detail = _aspect("LOD 300", "LOD 350",
                         "swept/mapped solid (" + ", ".join(sorted(reps & _SOLID_REPS)) + ")")
    elif reps & _PLACEHOLDER_REPS:
        # A box is a placeholder BY CONSTRUCTION — the one aspect decidable DOWNWARD with certainty,
        # and what stops a well-tagged box claiming a coordination band.
        detail = _aspect("LOD 200", "LOD 200",
                         "placeholder representation (" + ", ".join(sorted(reps & _PLACEHOLDER_REPS)) + ")")
    else:
        detail = _aspect("LOD 200", None,
                         "unrecognised representation type (" + ", ".join(sorted(reps)) + ")")

    # DIMENSIONALITY — a box-only shape PROVES approximate extents. Anything else is unreadable.
    if unknown_shape:
        dim = _aspect("LOD 100", None, "no readable shape representation")
    elif (reps & _PLACEHOLDER_REPS) and not (reps & (_SOLID_REPS | _RESOLVED_REPS)):
        dim = _aspect("LOD 200", "LOD 200", "approximate extents only")
    else:
        dim = _aspect("LOD 300", None, "3D solid present; accuracy is not readable from the index")

    # LOCATION — a MISSING placement proves a limit. A present one proves only presence.
    if not e.get("placed"):
        loc = _aspect("LOD 100", "LOD 100", "no object placement")
    else:
        loc = _aspect("LOD 300", None, "placed; accuracy is not readable from the index")

    # APPEARANCE — a material association is evidence, never a cap: an element can be accurately
    # represented and carry its material somewhere this index does not look.
    app = (_aspect("LOD 300", None, "material associated") if e.get("has_material")
           else _aspect("LOD 200", None, "no material association read"))

    # PARAMETRIC BEHAVIOR — the aspect definitions expect none below LOD 400 unless a keynote
    # defines it, so this aspect never constrains the lower bands. Reported, not scored.
    par = _aspect("LOD 400", None, "not required below LOD 400 by the aspect definitions")

    return {"detail": detail, "dimensionality": dim, "location": loc,
            "appearance": app, "parametric_behavior": par}


def achieved_lod(e: dict) -> str:
    """The band an element's evidence SUPPORTS - the minimum across the aspects, not a count.

    Reaches **LOD 500** only on a field-verified element, because that is what LOD 500 means; every
    other element caps at LOD 400 no matter how rich its geometry, since no amount of modelling can
    assert that something matches the building as built. An element measured and found *outside*
    tolerance is not promoted: it has been verified as WRONG, which is a finding, not a handover.
    """
    v = verification(e)
    if v["verified"] and v["within_tolerance"] is not False:
        return "LOD 500"
    a = aspects(e)
    # DETAIL sets the level; the other aspects can only PULL IT DOWN, and only when their evidence
    # proves a cap. That is the spec's "requirements are minimums and must all be met" without
    # inventing a limit out of an aspect nobody can read.
    ranks = [_LOD_RANK[a["detail"]["supported"]]]
    ranks += [_LOD_RANK[x["cap"]] for x in a.values() if x["cap"]]
    return LOD_BANDS[min(ranks)]


def lod_ceiling(e: dict) -> str:
    """The highest band the evidence COULD support - equal to `achieved_lod` only when every aspect
    is decidable. The gap between the two IS the unread part of the model, and reporting it is the
    difference between "this is LOD 300" and "this is at least LOD 300 and we cannot see higher"."""
    a = aspects(e)
    caps = [_LOD_RANK[x["cap"]] for x in a.values() if x["cap"]]
    # With no proven cap the ceiling is LOD 400 — the highest a model read can reach, since 500 is
    # a field assertion. The GAP between this and `achieved_lod` is the unread part of the model.
    return LOD_BANDS[min(caps) if caps else _LOD_RANK["LOD 400"]]


def information_score(e: dict) -> int:
    """LOIN facet completeness, 0-5 - what `achieved_lod` used to be computed from.

    Kept and RENAMED rather than deleted: it is a real, useful reading of how completely an element
    is described, and the defect was never the measurement, it was the label. Reported beside the
    LOD band so the two cannot be confused again.
    """
    fac = _facets(e)
    return sum(1 for f in LOIN_FACETS if fac[f])


def assess(db: Session, pid: str, idx: dict[str, dict] | None) -> dict[str, Any]:
    """Achieved-LOD assessment of the loaded model: overall distribution + a per-discipline average,
    alongside the target matrix. Returns targets only (model_scored False) when no model is loaded."""
    m = matrix(db, pid)
    if not idx:
        return {"model_scored": False, "elements": 0, "distribution": {}, "by_discipline": [],
                "targets": m["targets"], "default": m["default"], "using_default": m["using_default"],
                "note": "No model loaded — showing the target matrix only. Load a model to assess "
                        "achieved LOD."}
    dist = dict.fromkeys(LOD_BANDS, 0)
    ceil_dist = dict.fromkeys(LOD_BANDS, 0)
    limiting = dict.fromkeys(ASPECTS, 0)
    undecidable = 0
    no_shape = 0
    info_sum = 0
    by_disc: dict[str, dict[str, int]] = {}
    for e in idx.values():
        lod = achieved_lod(e)
        dist[lod] += 1
        ceil_dist[lod_ceiling(e)] += 1
        info_sum += information_score(e)
        if not (e.get("rep_types") or []):
            no_shape += 1
        a = aspects(e)
        # Which aspect PROVED the cap that decided the band. A distribution says a model is at
        # LOD 200 without saying why, and "why" is the only part anyone can act on. Only aspects
        # with a proven cap can be blamed — an unreadable one is reported separately, below.
        band = _LOD_RANK[lod]
        for akey, x in a.items():
            if x["cap"] and _LOD_RANK[x["cap"]] == band:
                limiting[akey] += 1
        if any(x["cap"] is None for x in a.values()):
            undecidable += 1
        code = classification.discipline_of_ifc_class(e.get("ifc_class") or "")
        name = classification.discipline_name(code) if code else None
        key = name or "Unclassified"
        d = by_disc.setdefault(key, {"count": 0, "rank_sum": 0})
        d["count"] += 1
        d["rank_sum"] += _LOD_RANK[lod]
    by_discipline = [{"discipline": name, "elements": d["count"],
                      "avg_lod": LOD_BANDS[round(d["rank_sum"] / d["count"])]}
                     for name, d in sorted(by_disc.items())]
    # LOD-ELEMENT-TABLE: achieved vs TARGET, per authored stage. Computed here rather than in a
    # second pass so the element loop stays single — and reported per stage because a project asks
    # "are we there for CD?", not "are we there in general".
    phases = sorted({(t.get("phase") or "").strip() for t in m["targets"] if (t.get("phase") or "").strip()})
    compliance = {}
    for ph in phases:
        met = short = untargeted = 0
        worst: dict[str, int] = {}
        for e in idx.values():
            t = target_for(e, m["targets"], ph)
            if not t:
                untargeted += 1
                continue
            want = _LOD_RANK.get(str(t.get("target_lod") or "").strip())
            if want is None:
                untargeted += 1
                continue
            if _LOD_RANK[achieved_lod(e)] >= want:
                met += 1
            else:
                short += 1
                label = (t.get("element_category") or t.get("ifc_class")
                         or t.get("uniformat") or t.get("discipline") or "(unlabelled rule)")
                worst[label] = worst.get(label, 0) + 1
        scored = met + short
        compliance[ph] = {
            "meeting_target": met, "short_of_target": short,
            # An element no rule addresses is NOT counted as compliant. A model element table that
            # covers a third of the model and reports 100% is the failure this whole item exists to
            # remove, so the uncovered count sits beside the percentage rather than inside it.
            "no_target": untargeted,
            "pct_meeting": round(100.0 * met / scored, 1) if scored else None,
            "short_by_rule": dict(sorted(worst.items(), key=lambda kv: -kv[1])[:10]),
        }

    n = len(idx)
    return {
        "model_scored": True, "elements": n, "distribution": dist,
        "compliance": compliance,
        # The CEILING is the other half of an honest reading: `distribution` is what the model
        # demonstrably reaches, this is what it could reach if the aspects the index cannot see
        # turned out to be met. A wide gap means UNREAD, not under-modelled — a distinction the old
        # single number could not express and therefore never made.
        "ceiling_distribution": ceil_dist,
        "limited_by": limiting,
        "elements_with_an_undecidable_aspect": undecidable,
        "elements_without_readable_geometry": no_shape,
        # The OLD number, kept under its true name. It is a real reading of how completely elements
        # are described; it was only ever wrong as a label for a geometry band.
        "avg_information_score": round(info_sum / n, 2) if n else 0.0,
        "information_score_max": len(LOIN_FACETS),
        "by_discipline": by_discipline, "targets": m["targets"], "default": m["default"],
        "using_default": m["using_default"],
        "note": "Achieved LOD is the MINIMUM across the five ISO 7817-1 aspects (detail, "
                "dimensionality, location, appearance, parametric behavior) — a band requires ALL "
                "of them, so this is never an average and never a facet count. "
                "`ceiling_distribution` is how high the same elements could reach if the aspects "
                "the index cannot read were met; the gap is unread model, not missing model. "
                "LOD 500 is read from the field-verification stamp — no amount of modelling earns "
                "it. `avg_information_score` is LOIN facet completeness, which this assessment "
                "reported AS the LOD band until v0.3.901.",
    }


# What stands between an element and a defensible LOD 500 assertion, in the order a team would fix it.
# Each reason names the next action, because "62% ready" tells a project nothing it can act on.
_GAP_ACTIONS = {
    "not_verified": "send it to the field — LOD 500 needs someone to look, not more modelling",
    "no_accuracy": "record the measured dimension; a bare VERIFIED flag states no accuracy",
    # LOD-500-LOA: measured but never GRADED. The deviation is computable and nobody has said what
    # accuracy the survey was performed to, which is the half of the definition that is usually
    # skipped — and the half a receiving party needs in order to rely on the number.
    "no_loa_level": "state the level of accuracy (label + tolerance in mm); a measurement without a "
                    "stated accuracy is a number nobody downstream can rely on",
    "out_of_tolerance": "resolve the deviation — measured outside tolerance is a finding, not handover",
    "thin_information": "add type / classification / properties / quantities before turnover",
}


def handover_readiness(db: Session, pid: str, idx: dict[str, dict] | None,
                       limit: int = 200) -> dict[str, Any]:
    """How far the model is from an LOD 500 handover, and **what to do next per element**.

    `asbuilt_summary` already reports a verified percentage. A percentage cannot be worked: it says
    a project is 62% ready without saying which 38% or why. This returns the gap as a work list,
    grouped by reason and by discipline, so the remaining effort is schedulable.
    """
    if not idx:
        return {"model_scored": False, "elements": 0, "lod500": 0, "readiness_pct": 0.0,
                "gaps": [], "by_reason": {}, "by_discipline": [], "truncated": 0,
                "note": "No model loaded — load one to assess LOD 500 handover readiness."}

    gaps: list[dict[str, Any]] = []
    by_reason: dict[str, int] = dict.fromkeys(_GAP_ACTIONS, 0)
    by_disc: dict[str, dict[str, int]] = {}
    lod500 = 0
    for guid, e in idx.items():
        v = verification(e)
        code = classification.discipline_of_ifc_class(e.get("ifc_class") or "")
        disc = (classification.discipline_name(code) if code else None) or "Unclassified"
        d = by_disc.setdefault(disc, {"elements": 0, "lod500": 0})
        d["elements"] += 1

        if not v["verified"]:
            reason = "not_verified"
        elif v["within_tolerance"] is False:
            reason = "out_of_tolerance"
        elif not v["accuracy_stated"]:
            reason = "no_accuracy"
        elif v["accuracy_grade"] != "declared":
            # Ordered AFTER `no_accuracy` on purpose: an element with no measurement at all needs a
            # survey, not a form field, and naming the cheaper fix first would send someone to type
            # a tolerance for a measurement that was never taken.
            reason = "no_loa_level"
        else:
            fac = _facets(e)
            reason = None if sum(1 for f in LOIN_FACETS if fac[f]) >= 4 else "thin_information"

        if reason is None:
            lod500 += 1
            d["lod500"] += 1
            continue
        by_reason[reason] += 1
        gaps.append({"guid": guid, "ifc_class": e.get("ifc_class"), "discipline": disc,
                     "reason": reason, "action": _GAP_ACTIONS[reason],
                     "method": v["method"], "verified_by": v["verified_by"]})

    total = len(idx)
    # the newest-first cap pattern: show a bounded slice but say how much was withheld, so a caller
    # never reads a truncated list as the whole remaining scope
    shown = gaps[:limit]
    return {
        "model_scored": True, "elements": total, "lod500": lod500,
        "readiness_pct": round(100.0 * lod500 / total, 1) if total else 0.0,
        "by_reason": {k: n for k, n in by_reason.items() if n},
        "actions": _GAP_ACTIONS,
        "by_discipline": [{"discipline": k, "elements": v["elements"], "lod500": v["lod500"],
                           "readiness_pct": round(100.0 * v["lod500"] / v["elements"], 1)}
                          for k, v in sorted(by_disc.items())],
        "gaps": shown, "truncated": max(0, len(gaps) - len(shown)),
        "note": "LOD 500 is a field-verified as-built assertion (BIMForum): it is earned by "
                "verification, never by adding geometry. An element measured outside tolerance is "
                "NOT promoted — it has been verified as wrong, which is a finding. A verification "
                "carrying no measured dimension states no accuracy, which the 2024 specification "
                "requires to be expressed by means other than the LOD number itself.",
    }
