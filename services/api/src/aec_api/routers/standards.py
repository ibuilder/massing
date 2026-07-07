"""ISO 19650 / openBIM standards endpoints — CDE container discipline + requirements register."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import bim_kpi, cde, ids_authoring, mcp_tools, openbim_quality, standards_expert
from ..db import get_db
from ..models import Project
from ..rbac import current_user

router = APIRouter()


def _project(db: Session, pid: str) -> Project:
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    return p


@router.get("/projects/{pid}/cde/status")
def cde_status(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """CDE container rollup (ISO 19650): state distribution WIP/Shared/Published/Archived,
    suitability spread, and CDE-discipline metrics (revision control, approval-status coverage,
    metadata completeness)."""
    _project(db, pid)
    return cde.status(db, pid)


@router.get("/projects/{pid}/info-requirements/register")
def requirements_register(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """The information-requirements register (OIR/AIR/PIR/EIR/BEP/MIDP/TIDP) with issued/draft
    counts and core-document coverage (EIR, BEP, AIR)."""
    _project(db, pid)
    return cde.requirements(db, pid)


@router.get("/projects/{pid}/openbim/quality")
def openbim_quality_scan(pid: str, use_case: str | None = None, db: Session = Depends(get_db),
                         _: str = Depends(current_user)):
    """openBIM quality of the loaded model: LOIN per element, IFC export health, bSDD alignment, and
    (when ?use_case= names an IDS use case) IDS rule-compliance scoring. Needs a loaded model."""
    _project(db, pid)
    from .properties import _INDEX, _ensure_loaded
    _ensure_loaded(pid)
    idx = _INDEX.get(pid)
    if not idx:
        raise HTTPException(404, "no properties index for project — load a model first")
    specs = ids_authoring.specs_for_use_case(use_case) if use_case else None
    out = openbim_quality.summary(idx, specs)
    out["use_case"] = use_case
    return out


@router.get("/projects/{pid}/lod/matrix")
def lod_matrix(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """The target LOD matrix (stage x discipline x element category -> LOD 100..500), or the RIBA/AIA
    stage defaults when the register carries none."""
    _project(db, pid)
    from .. import lod
    return lod.matrix(db, pid)


@router.get("/projects/{pid}/lod/assessment")
def lod_assessment(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Achieved-LOD assessment of the loaded model (inferred from LOIN facet completeness) against the
    target matrix. Returns targets only when no model is loaded."""
    _project(db, pid)
    from .. import lod
    from .properties import _INDEX, _ensure_loaded
    try:
        _ensure_loaded(pid)
    except Exception:                     # noqa: BLE001 — no model loaded is a valid (targets-only) state
        pass
    return lod.assess(db, pid, _INDEX.get(pid))


@router.get("/projects/{pid}/naming/conventions")
def naming_conventions(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """The document/container filename + drawing sheet-ID naming conventions the validator enforces."""
    _project(db, pid)
    from .. import naming
    return naming.conventions()


@router.get("/projects/{pid}/naming/validate")
def naming_validate(pid: str, name: str, kind: str = "container",
                    db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Validate a single name against the convention. kind = container | sheet."""
    _project(db, pid)
    from .. import naming
    return naming.validate(name, kind)


@router.get("/projects/{pid}/naming/audit")
def naming_audit(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Audit the CDE containers + drawing register for naming-convention compliance."""
    _project(db, pid)
    from .. import naming
    return naming.audit(db, pid)


def _idx_for(pid: str):
    from .properties import _INDEX, _ensure_loaded
    try:
        _ensure_loaded(pid)
    except Exception:                     # noqa: BLE001 — no model is a valid (empty-result) state
        pass
    return _INDEX.get(pid)


@router.get("/projects/{pid}/model/query/views")
def model_query_views(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """The saved model-analytics views (count by discipline / class / storey / type)."""
    _project(db, pid)
    from .. import model_query
    return {"views": model_query.saved_views()}


@router.get("/projects/{pid}/model/query")
def model_query_run(pid: str, view: str | None = None, group_by: str = "ifc_class", agg: str = "count",
                    quantity: str | None = None, db: Session = Depends(get_db),
                    _: str = Depends(current_user)):
    """Analytics query over the loaded model — a saved ?view=, or ad-hoc group_by / agg=sum&quantity=."""
    _project(db, pid)
    from .. import model_query
    idx = _idx_for(pid)
    return model_query.run_saved(idx, view) if view else model_query.query(idx, group_by, agg, quantity)


@router.get("/projects/{pid}/model/export.csv")
def model_export_csv(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Export the model element table as CSV (columnar, one row per element)."""
    _project(db, pid)
    from .. import model_query
    return Response(model_query.to_csv(_idx_for(pid)), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="model-{pid}.csv"'})


@router.get("/projects/{pid}/model/export.jsonld")
def model_export_jsonld(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Export the model elements as a JSON-LD graph (bSDD-style vocab, GlobalId as @id)."""
    _project(db, pid)
    from .. import model_query
    return model_query.to_jsonld(_idx_for(pid))


@router.get("/projects/{pid}/bim-kpi/scorecard")
def bim_kpi_scorecard(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """The 10-category BIM KPI scorecard, graded from the CDE, model quality and the issue / asset /
    closeout records (categories with no inputs show 'n/a')."""
    _project(db, pid)
    return bim_kpi.scorecard(db, pid)


@router.get("/projects/{pid}/handover/acceptance")
def handover_acceptance(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Handover data-drop acceptance gate — the owner's checklist against the AIR (requirements,
    asset tags, as-builts, O&M, accepted completion certificate)."""
    _project(db, pid)
    return bim_kpi.handover_acceptance(db, pid)


@router.get("/projects/{pid}/standards/check")
def standards_check(pid: str, standard: str = "iso19650", db: Session = Depends(get_db),
                    _: str = Depends(current_user)):
    """Standards-compliance check (iso19650 | cobie | ids | uniclass) against the project's own data:
    findings with the clause each references, recommendations, and a 0–100 readiness score."""
    _project(db, pid)
    return standards_expert.check(db, pid, standard)


@router.get("/mcp/tools")
def mcp_tool_catalog(_: str = Depends(current_user)):
    """The tool catalog the MCP server exposes to external AI agents (name, description, input
    schema). The stdio server (services/api/mcp_server.py) drives these against a project."""
    return {"tools": mcp_tools.catalog(), "server": "services/api/mcp_server.py",
            "note": "Run the stdio MCP server and point Claude Desktop / Cursor at it to drive the "
                    "project by natural language. The MCP SDK (pip install 'mcp[cli]') is optional."}

