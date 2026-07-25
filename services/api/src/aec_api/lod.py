"""LOD (Level of Development) — the target matrix + an achieved-LOD assessment of the loaded model.

The target matrix is authored in the `lod_target` register (stage x discipline x element-category ->
target LOD 100..500); when it is empty the RIBA/AIA stage defaults apply. Achieved LOD is *inferred*
from LOIN facet completeness (geometry / type / classification / properties / quantities) — the same
facets the openBIM quality scorecard scores — so LOD tracking rides on data the model already carries.
LOD 500 (a verified as-built condition) cannot be inferred from the model alone, so inference caps at
LOD 400; reaching 500 is an explicit handover/turnover assertion, not a model read.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import classification
from . import modules as me
from .openbim_quality import LOIN_FACETS, _facets

LOD_BANDS = ["LOD 100", "LOD 200", "LOD 300", "LOD 350", "LOD 400", "LOD 500"]
_FACETS_TO_LOD = {0: "LOD 100", 1: "LOD 100", 2: "LOD 200", 3: "LOD 300", 4: "LOD 350", 5: "LOD 400"}
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
    targets = [{"element_category": _d(r).get("element_category", ""), "discipline": _d(r).get("discipline", ""),
                "phase": _d(r).get("phase", ""), "target_lod": _d(r).get("target_lod", ""),
                "state": r.get("workflow_state", "")} for r in rows]
    return {
        "targets": targets, "default": _DEFAULT_MATRIX, "using_default": not targets,
        "note": "Target LOD by stage / discipline / element category. With no targets registered the "
                "RIBA/AIA stage defaults apply (SD LOD200 -> DD LOD300 -> CD LOD350 -> Construction "
                "LOD400 -> As-built LOD500).",
    }


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

    `accuracy_stated` is the BIMForum requirement above: a measurement method that carries a
    tolerance or a recorded deviation states its accuracy; a bare "VERIFIED" flag does not.
    """
    psets = e.get("psets") if isinstance(e.get("psets"), dict) else {}
    ab = psets.get(ASBUILT_PSET) or {}
    dims = psets.get(ASBUILT_DIM_PSET) or {}
    verified = str(ab.get("Status") or "").upper() == "VERIFIED"
    tol = str(dims.get("WithinTolerance") or "").lower()
    return {
        "verified": verified,
        "method": str(ab.get("Method") or "") or None,
        "verified_by": str(ab.get("VerifiedBy") or "") or None,
        "verified_date": str(ab.get("VerifiedDate") or "") or None,
        # a recorded measurement is what states the accuracy — the flag alone never does
        "accuracy_stated": bool(any(str(k).endswith("_Measured") for k in dims)),
        "within_tolerance": None if tol not in ("true", "false") else (tol == "true"),
    }


def achieved_lod(e: dict) -> str:
    """Achieved LOD for one element.

    Reaches **LOD 500** only on a field-verified element, because that is what LOD 500 means; every
    other element caps at LOD 400 no matter how rich its geometry, since no amount of modelling can
    assert that something matches the building as built. An element measured and found *outside*
    tolerance is not promoted: it has been verified as WRONG, which is a finding, not a handover.
    """
    v = verification(e)
    if v["verified"] and v["within_tolerance"] is not False:
        return "LOD 500"
    fac = _facets(e)
    return _FACETS_TO_LOD[sum(1 for f in LOIN_FACETS if fac[f])]


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
    by_disc: dict[str, dict[str, int]] = {}
    for e in idx.values():
        lod = achieved_lod(e)
        dist[lod] += 1
        code = classification.discipline_of_ifc_class(e.get("ifc_class") or "")
        name = classification.discipline_name(code) if code else None
        key = name or "Unclassified"
        d = by_disc.setdefault(key, {"count": 0, "rank_sum": 0})
        d["count"] += 1
        d["rank_sum"] += _LOD_RANK[lod]
    by_discipline = [{"discipline": name, "elements": d["count"],
                      "avg_lod": LOD_BANDS[round(d["rank_sum"] / d["count"])]}
                     for name, d in sorted(by_disc.items())]
    return {
        "model_scored": True, "elements": len(idx), "distribution": dist,
        "by_discipline": by_discipline, "targets": m["targets"], "default": m["default"],
        "using_default": m["using_default"],
        "note": "Achieved LOD inferred from LOIN facet completeness, except LOD 500 which is read "
                "from the element's field-verification stamp — no amount of modelling earns it.",
    }


# What stands between an element and a defensible LOD 500 assertion, in the order a team would fix it.
# Each reason names the next action, because "62% ready" tells a project nothing it can act on.
_GAP_ACTIONS = {
    "not_verified": "send it to the field — LOD 500 needs someone to look, not more modelling",
    "no_accuracy": "record the measured dimension; a bare VERIFIED flag states no accuracy",
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
