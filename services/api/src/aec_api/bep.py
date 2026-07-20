"""BEP-GEN (R15) — generate the project's **BIM Execution Plan** from its LIVE configuration, so the
BEP is never a stale side-document. ISO 19650-2 frames the BEP as the delivery team's response to the
appointing party's requirements; here every section is pulled from what the project *actually* has
configured right now — pinned information requirements + IDS, the CDE container state, the
responsibility (RACI) matrix, classification systems, the source model's schema/exchange formats, and
the model-quality acceptance gates.

Pure composition over the existing engines (``cde``, ``responsibility``, ``classification``,
``ids_authoring``) — each section degrades gracefully (``configured: False`` + a note) when its inputs
aren't set up yet, so a fresh project still yields a valid skeleton BEP that fills in as the team works.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:                                    # noqa: BLE001 — a missing input degrades the section
        return default


def generate(db: Session, pid: str) -> dict[str, Any]:
    """Compose the always-current BIM Execution Plan for ``pid``. Returns ``{project, sections,
    completeness, note}`` where each section is ``{id, title, configured, summary, items[]}``."""
    from .models import Project

    proj = db.get(Project, pid)
    if proj is None:
        return {"project": None, "sections": [], "completeness": {"configured": 0, "total": 0},
                "note": "project not found"}

    sections: list[dict[str, Any]] = []

    # 1 — Standards & references (always present: this platform is ISO 19650-native)
    from . import classification
    disc = _safe(lambda: classification.disciplines(), []) or []
    systems = _safe(lambda: list(classification.CLASSIFICATIONS.keys()), []) or []
    sections.append({
        "id": "standards", "title": "1. Standards & references", "configured": True,
        "summary": "ISO 19650 information-management framework; classification per the project's systems.",
        "items": [
            {"k": "Information management", "v": "ISO 19650-1 / -2 (concepts + delivery phase)"},
            {"k": "Classification systems", "v": ", ".join(systems) or "Uniformat / MasterFormat"},
            {"k": "Disciplines", "v": f"{len(disc)} NCS disciplines on the project spine"},
        ],
    })

    # 2 — Information requirements (EIR / BEP / AIR coverage) + IDS
    from . import cde
    reqs = _safe(lambda: cde.requirements(db, pid))
    ir_items, ir_ok = [], False
    if reqs:
        ir_ok = True
        core = reqs.get("core_coverage") or {}
        ir_items = [
            {"k": "Information requirements", "v": f"{reqs.get('total', 0)} registered"},
            {"k": "Core (EIR + BEP + AIR)",
             "v": "complete" if core.get("complete") else f"missing: {', '.join(core.get('missing') or []) or '—'}"},
        ]
        for t, n in (reqs.get("by_type") or {}).items():
            ir_items.append({"k": f"— {t}", "v": f"{n}"})
    sections.append({
        "id": "information_requirements", "title": "2. Information requirements", "configured": ir_ok,
        "summary": "The appointing-party requirements the delivery team responds to (EIR/PIR/AIR) + the "
                   "machine-checkable IDS.",
        "items": ir_items or [{"k": "Status", "v": "no information requirements registered yet"}],
    })

    # 3 — Roles & responsibilities (RACI)
    from . import responsibility
    mtx = _safe(lambda: responsibility.matrix(db, pid))
    role_items, role_ok = [], False
    if mtx and mtx.get("count"):
        role_ok = True
        s = mtx.get("summary") or {}
        role_items = [
            {"k": "Assignment mode", "v": mtx.get("mode", "RACI")},
            {"k": "Roles", "v": ", ".join(mtx.get("roles") or []) or "—"},
            {"k": "Activities mapped", "v": f"{s.get('activities', 0)}"},
            {"k": "Matrix validation", "v": "clean" if s.get("clean") else f"{s.get('issues', 0)} issue(s)"},
        ]
    sections.append({
        "id": "roles", "title": "3. Roles & responsibilities", "configured": role_ok,
        "summary": "The RACI responsibility matrix — who is Responsible / Accountable / Consulted / "
                   "Informed for each delivery activity.",
        "items": role_items or [{"k": "Status", "v": "responsibility matrix not populated yet"}],
    })

    # 4 — Common Data Environment
    cst = _safe(lambda: cde.status(db, pid))
    cde_items, cde_ok = [], False
    if cst and cst.get("total"):
        cde_ok = True
        by_state = cst.get("by_state") or {}
        dsc = cst.get("discipline") or {}
        cde_items = [
            {"k": "Containers", "v": f"{cst.get('total', 0)}"},
            {"k": "State (WIP→Shared→Published→Archived)",
             "v": " · ".join(f"{k}:{v}" for k, v in by_state.items())},
            {"k": "Metadata completeness", "v": f"{dsc.get('metadata_completeness_pct') or 0}%"},
            {"k": "Revision control", "v": f"{dsc.get('revision_control_pct') or 0}%"},
        ]
    sections.append({
        "id": "cde", "title": "4. Common Data Environment (CDE)", "configured": cde_ok,
        "summary": "ISO 19650 container states + metadata discipline of the shared information.",
        "items": cde_items or [{"k": "Status", "v": "no information containers registered yet"}],
    })

    # 5 — Exchange, formats & the model
    schema = None
    if proj.source_ifc:
        schema = _safe(lambda: __import__("aec_data.ifc_loader", fromlist=["open_model"])
                       .open_model(proj.source_ifc).schema)
    sections.append({
        "id": "exchange", "title": "5. Exchange information & formats", "configured": bool(proj.source_ifc),
        "summary": "The federated model exchange — openBIM IFC as the source of truth, with derived "
                   "exports.",
        "items": [
            {"k": "Source model", "v": (f"IFC ({schema})" if schema else "IFC") if proj.source_ifc
             else "no source model published yet"},
            {"k": "Primary exchange", "v": "IFC (openBIM source of truth)"},
            {"k": "Derived exports", "v": "IFC · IFCX · glTF/GLB · BCF · COBie · IDS · discipline subset"},
        ],
    })

    # 6 — Model quality / acceptance gates (what a container must pass to be accepted)
    sections.append({
        "id": "quality", "title": "6. Model quality & acceptance gates", "configured": True,
        "summary": "The automated checks every model increment is run through before acceptance.",
        "items": [
            {"k": "Normative conformance", "v": "NORM-VALID — header/schema/GlobalId/containment gauntlet"},
            {"k": "Authoring quality", "v": "Model QA — duplicate GUIDs, orphans, overlaps, blank names"},
            {"k": "Data completeness", "v": "IDS / LOIN required-property checks"},
            {"k": "Change control", "v": "version diff + quantity-drift (Model CI) + revision cost delta"},
        ],
    })

    configured = sum(1 for s in sections if s["configured"])
    return {
        "project": {"id": proj.id, "name": proj.name, "has_model": bool(proj.source_ifc)},
        "sections": sections,
        "completeness": {"configured": configured, "total": len(sections),
                         "pct": round(100.0 * configured / len(sections)) if sections else 0},
        "note": "Generated from the project's live configuration — the BEP reflects current state, not a "
                "point-in-time snapshot. Populate information requirements, the responsibility matrix and "
                "the CDE to complete the unconfigured sections.",
    }
