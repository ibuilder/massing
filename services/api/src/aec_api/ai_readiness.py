"""AI / data-readiness scorecard — "can an agent act on this project's data yet?". The agentic-AI
research is blunt: the bottleneck isn't the model, it's the data (single source of truth, quality,
currency, controlled access). This grades a project 0–100 on four measurable dimensions from signals
we already compute, so a team knows what to fix before pointing an agent at it.

Guarded/read-only over the DB (+ optionally the source IFC). No new deps."""
from __future__ import annotations

from typing import Any

from . import cde
from . import modules as me

_BANDS = [(85, "ready"), (60, "partial"), (0, "not_ready")]


def _verdict(score: float) -> str:
    for thr, label in _BANDS:
        if score >= thr:
            return label
    return "not_ready"


def scorecard(db, pid: str, ifc_path: str | None = None) -> dict[str, Any]:
    """Four dimensions — single-source-of-truth, information completeness, model integrity, governance
    — each 0–100 with the sub-signals behind it and a recommendation. Overall = mean of the applicable
    dimensions. `ifc_path` (optional) enables the model-integrity dimension."""
    dims: dict[str, dict[str, Any]] = {}

    # 1. Single source of truth — one IFC-GUID-keyed model + federated discipline models
    from .models import Project, ProjectModel
    p = db.get(Project, pid)
    n_models = db.query(ProjectModel).filter_by(project_id=pid).count()
    has_ifc = bool(p and p.source_ifc)
    ssot = (60 if has_ifc else 20) + min(n_models, 2) * 20     # GUID-keyed by design; models add trust
    dims["single_source_of_truth"] = {
        "score": min(ssot, 100), "has_source_ifc": has_ifc, "federated_models": n_models,
        "advice": "Load a source IFC and federate discipline models — the shared GUID key is the join an agent needs."
        if ssot < 80 else "A GUID-keyed model of record is in place.",
    }

    # 2. Information completeness — CDE metadata + the requirements register (what the agent reads)
    st = cde.status(db, pid)
    reqs = cde.requirements(db, pid)
    meta = st["discipline"].get("metadata_completeness_pct") or 0.0
    core = reqs["core_coverage"]["complete"]
    completeness = round(0.7 * meta + (30 if core else 0), 1)
    dims["information_completeness"] = {
        "score": completeness, "metadata_completeness_pct": meta,
        "requirements_core_complete": core,
        "advice": "Fill container metadata (type/discipline/originator/suitability/revision) and issue the core "
                  "requirements (EIR/BEP/AIR)." if completeness < 80 else "Container metadata and core requirements are in good shape.",
    }

    # 3. Model integrity — clean geometry an agent can trust (only when an IFC is available)
    if ifc_path:
        try:
            import ifcopenshell  # type: ignore

            from . import model_qa
            q = model_qa.model_qa(ifcopenshell.open(ifc_path))
            issues, elems = q["total_issues"], max(q["element_count"], 1)
            integrity = round(max(0.0, 100 - (issues / elems) * 400), 1)   # penalize the defect ratio
            dims["model_integrity"] = {"score": integrity, "issues": issues, "elements": q["element_count"],
                                       "advice": "Resolve the model-QA issues (dup GUIDs / orphans / overlaps) before agents rely on the geometry."
                                       if integrity < 85 else "Model integrity is clean."}
        except Exception:       # noqa: BLE001 — integrity is optional; skip on any read failure
            pass

    # 4. Governance — is access controlled + is intent traceable (the security leg)
    cascade = cde.cascade(db, pid)
    resp = me.list_records(db, "responsibility", pid, limit=1)          # a responsibility matrix exists
    traced = cascade["coverage_pct"] or 0.0
    governance = round(0.5 * traced + (25 if resp else 0) + 25, 1)      # +25 baseline: RBAC + audit are always on
    dims["governance"] = {
        "score": min(governance, 100), "requirement_traceability_pct": traced,
        "responsibility_matrix": bool(resp),
        "advice": "Trace requirements up the OIR→EIR cascade and assign a responsibility matrix so actions have an accountable owner."
        if governance < 80 else "Access is controlled and intent is traceable.",
    }

    scores = [d["score"] for d in dims.values()]
    overall = round(sum(scores) / len(scores), 1) if scores else 0.0
    return {"overall": overall, "verdict": _verdict(overall), "dimensions": dims,
            "note": "Agent-readiness of the project data: single source of truth, information completeness, "
                    "model integrity, governance. Fix the low dimensions before relying on autonomous agents."}
