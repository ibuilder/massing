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


def achieved_lod(e: dict) -> str:
    """Inferred LOD for one element from its LOIN facet count (caps at LOD 400)."""
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
        "note": "Achieved LOD inferred from LOIN facet completeness; capped at LOD 400 (LOD 500 is a "
                "verified as-built assertion, not a model read).",
    }
