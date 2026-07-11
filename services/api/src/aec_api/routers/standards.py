"""ISO 19650 / openBIM standards endpoints — CDE container discipline + requirements register."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import bim_kpi, bsdd, cde, ids_authoring, mcp_tools, openbim, openbim_quality, standards_expert
from ..db import get_db
from ..models import Project
from ..rbac import current_user, require_role

router = APIRouter()


def _project(db: Session, pid: str) -> Project:
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    return p


@router.get("/projects/{pid}/cde/status")
def cde_status(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """CDE container rollup (ISO 19650): state distribution WIP/Shared/Published/Archived,
    suitability spread, and CDE-discipline metrics (revision control, approval-status coverage,
    metadata completeness)."""
    _project(db, pid)
    return cde.status(db, pid)


@router.get("/projects/{pid}/info-requirements/register")
def requirements_register(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The information-requirements register (OIR/AIR/PIR/EIR/BEP/MIDP/TIDP) with issued/draft
    counts and core-document coverage (EIR, BEP, AIR)."""
    _project(db, pid)
    return cde.requirements(db, pid)


@router.get("/projects/{pid}/info-requirements/cascade")
def requirements_cascade(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The ISO 19650 requirement flow-down — OIR → PIR/AIR → EIR → MIDP/TIDP linked by each record's
    `derives_from` — as a tiered tree plus cascade health (orphans that don't trace up to
    organizational intent; links pointing the wrong way)."""
    _project(db, pid)
    return cde.cascade(db, pid)


@router.get("/projects/{pid}/openbim/quality")
def openbim_quality_scan(pid: str, use_case: str | None = None, db: Session = Depends(get_db),
                         _: str = Depends(require_role("viewer"))):
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
def lod_matrix(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The target LOD matrix (stage x discipline x element category -> LOD 100..500), or the RIBA/AIA
    stage defaults when the register carries none."""
    _project(db, pid)
    from .. import lod
    return lod.matrix(db, pid)


@router.get("/projects/{pid}/lod/assessment")
def lod_assessment(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
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
def naming_conventions(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The document/container filename + drawing sheet-ID naming conventions the validator enforces."""
    _project(db, pid)
    from .. import naming
    return naming.conventions()


@router.get("/projects/{pid}/naming/validate")
def naming_validate(pid: str, name: str, kind: str = "container",
                    db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Validate a single name against the convention. kind = container | sheet."""
    _project(db, pid)
    from .. import naming
    return naming.validate(name, kind)


@router.get("/projects/{pid}/naming/audit")
def naming_audit(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
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
def model_query_views(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The saved model-analytics views (count by discipline / class / storey / type)."""
    _project(db, pid)
    from .. import model_query
    return {"views": model_query.saved_views()}


@router.get("/projects/{pid}/model/query")
def model_query_run(pid: str, view: str | None = None, group_by: str = "ifc_class", agg: str = "count",
                    quantity: str | None = None, db: Session = Depends(get_db),
                    _: str = Depends(require_role("viewer"))):
    """Analytics query over the loaded model — a saved ?view=, or ad-hoc group_by / agg=sum&quantity=."""
    _project(db, pid)
    from .. import model_query
    idx = _idx_for(pid)
    return model_query.run_saved(idx, view) if view else model_query.query(idx, group_by, agg, quantity)


@router.get("/projects/{pid}/model/export.csv")
def model_export_csv(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Export the model element table as CSV (columnar, one row per element)."""
    _project(db, pid)
    from .. import model_query
    return Response(model_query.to_csv(_idx_for(pid)), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="model-{pid}.csv"'})


@router.get("/projects/{pid}/model/export.jsonld")
def model_export_jsonld(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Export the model elements as a JSON-LD graph (bSDD-style vocab, GlobalId as @id)."""
    _project(db, pid)
    from .. import model_query
    return model_query.to_jsonld(_idx_for(pid))


@router.get("/projects/{pid}/model/export.parquet")
def model_export_parquet(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Export the model element table as Apache Parquet (columnar analytics — DuckDB / pandas / Polars).

    Needs the optional `pyarrow` dependency; returns 503 with a clear message when it isn't installed."""
    _project(db, pid)
    from .. import model_query
    try:
        data = model_query.to_parquet(_idx_for(pid))
    except RuntimeError as exc:  # pyarrow not installed
        raise HTTPException(503, str(exc))
    return Response(data, media_type="application/vnd.apache.parquet",
                    headers={"Content-Disposition": f'attachment; filename="model-{pid}.parquet"'})


@router.get("/projects/{pid}/model/columnar/stats")
def model_columnar_stats(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Interning/columnar efficiency stats for the loaded model — dedup ratio + estimated RAM saved by
    the BimOpenSchema-style string-interned columnar form vs the per-element JSON index."""
    _project(db, pid)
    from .. import bim_columns
    return bim_columns.interning_stats(_idx_for(pid))


@router.get("/projects/{pid}/model/columnar/aggregate")
def model_columnar_aggregate(pid: str, group_by: str = "ifc_class",
                             db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Columnar count group-by over the element table via pyarrow compute (vectorised, no row loop)."""
    _project(db, pid)
    from .. import bim_columns
    try:
        return bim_columns.aggregate(_idx_for(pid), group_by)
    except RuntimeError as exc:      # pyarrow absent
        raise HTTPException(503, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/projects/{pid}/model/export/params.parquet")
def model_export_params_parquet(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Export the model's property/quantity set as an EAV Parquet table (the analytics-friendly store —
    query in DuckDB/pandas). Needs pyarrow; 503 if absent."""
    _project(db, pid)
    from .. import bim_columns
    try:
        data = bim_columns.params_parquet(_idx_for(pid))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return Response(data, media_type="application/vnd.apache.parquet",
                    headers={"Content-Disposition": f'attachment; filename="model-{pid}-params.parquet"'})


@router.get("/projects/{pid}/bim-kpi/scorecard")
def bim_kpi_scorecard(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The 10-category BIM KPI scorecard, graded from the CDE, model quality and the issue / asset /
    closeout records (categories with no inputs show 'n/a')."""
    _project(db, pid)
    return bim_kpi.scorecard(db, pid)


@router.get("/projects/{pid}/handover/acceptance")
def handover_acceptance(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Handover data-drop acceptance gate — the owner's checklist against the AIR (requirements,
    asset tags, as-builts, O&M, accepted completion certificate)."""
    _project(db, pid)
    return bim_kpi.handover_acceptance(db, pid)


@router.get("/projects/{pid}/standards/check")
def standards_check(pid: str, standard: str = "iso19650", db: Session = Depends(get_db),
                    _: str = Depends(require_role("viewer"))):
    """Standards-compliance check (iso19650 | cobie | ids | uniclass) against the project's own data:
    findings with the clause each references, recommendations, and a 0–100 readiness score."""
    _project(db, pid)
    return standards_expert.check(db, pid, standard)


@router.get("/bsdd/search")
def bsdd_search(q: str, dictionary: str | None = None, limit: int = 20,
                _: str = Depends(current_user)):
    """Free-text search the buildingSMART Data Dictionary for classes matching `q`
    (optionally scoped to one ?dictionary= URI). Reference-data lookup, not
    project-scoped. A bSDD outage surfaces as 502, not 500."""
    try:
        return {"classes": bsdd.search_classes(q, dictionary_uri=dictionary, limit=limit)}
    except RuntimeError as exc:
        raise HTTPException(502, "bSDD unavailable") from exc


@router.get("/bsdd/class")
def bsdd_class(uri: str, _: str = Depends(current_user)):
    """Fetch one bSDD class (with its properties) by full `uri`. 404 when the class
    isn't found; 502 when bSDD is unreachable."""
    try:
        cls = bsdd.get_class(uri)
    except RuntimeError as exc:
        raise HTTPException(502, "bSDD unavailable") from exc
    if cls is None:
        raise HTTPException(404, "class not found")
    return cls


@router.get("/openbim/capabilities")
def openbim_capabilities(_: str = Depends(current_user)):
    """The openBIM standards + version matrix this platform speaks — for each standard (IFC, BCF, IDS,
    bSDD, COBie, ISO 19650 CDE), which versions we can read and write. Derived from the live engines
    (BCF versions, IFC schemas), so it never drifts from what's actually implemented; a consumer/agent
    can ask 'do you read BCF 3.0?' without guessing."""
    return openbim.capabilities()


@router.get("/mcp/tools")
def mcp_tool_catalog(_: str = Depends(current_user)):
    """The tool catalog the MCP server exposes to external AI agents (name, description, input
    schema). The stdio server (services/api/mcp_server.py) drives these against a project."""
    return {"tools": mcp_tools.catalog(), "server": "services/api/mcp_server.py",
            "note": "Run the stdio MCP server and point Claude Desktop / Cursor at it to drive the "
                    "project by natural language. The MCP SDK (pip install 'mcp[cli]') is optional."}

