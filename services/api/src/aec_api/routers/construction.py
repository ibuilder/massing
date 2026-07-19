"""Construction analytics — T&M (eTicket) cost rollup + the submittal register."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from .. import actions as actions_engine
from .. import changeorders as co_engine
from .. import closeout as closeout_engine
from .. import dailylog as dailylog_engine
from .. import distribution as dist_engine
from .. import precon as precon_engine
from .. import projecthealth as health_engine
from .. import quality as quality_engine
from .. import rfi as rfi_engine
from .. import safety as safety_engine
from .. import submittals as sub_engine
from .. import tm as tm_engine
from ..db import get_db
from ..rbac import require_role

router = APIRouter()


@router.get("/projects/{pid}/modules/{key}/{rid}/distribution")
def record_distribution(pid: str, key: str, rid: str, db: Session = Depends(get_db),
                        _: str = Depends(require_role("viewer"))):
    """Resolve a record's distribution (CC) field against the contact directory → recipients + emails."""
    return dist_engine.for_record(db, pid, key, rid)


@router.get("/projects/{pid}/stakeholders/analysis")
def stakeholder_analysis(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Power/interest (Mendelow) grid + stance read of the project's stakeholder register."""
    from .. import stakeholder
    return stakeholder.analysis(db, pid)


@router.get("/projects/{pid}/tm-summary")
def tm_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Time & Material (eTicket) cost rollup — labor/material/equipment, billed vs unbilled."""
    return tm_engine.tm_summary(db, pid)


@router.get("/projects/{pid}/tm-by-change-event")
def tm_by_change_event(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """T&M (eTicket) cost rolled up by the change event each ticket is linked to."""
    return tm_engine.by_change_event(db, pid)


@router.get("/projects/{pid}/change-orders/log")
def co_log(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Change-order log — CO value pipeline (pending/approved/executed), reason mix, schedule exposure."""
    return co_engine.co_log(db, pid)


@router.get("/projects/{pid}/action-items/tracker")
def action_tracker(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Meeting & action-item tracker — open/overdue by assignee & priority, completion, meeting log."""
    return actions_engine.action_tracker(db, pid)


@router.get("/projects/{pid}/specs/submittal-log")
def specs_submittal_log(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Spec-driven submittal log — required submittals derived per spec section vs the submittals
    actually logged, with missing-submittal gaps (the CSI Part 1 'Submittals' → log reconciliation)."""
    from .. import specs
    return specs.submittal_log(db, pid)


@router.post("/projects/{pid}/specs/extract-submittals")
def specs_extract_submittals(pid: str, body: dict = Body(...), db: Session = Depends(get_db),
                             actor: str = Depends(require_role("editor"))):
    """Extract a typed submittal list from pasted spec text (AI when configured, rules fallback offline).
    Body: {text, create?: bool}. With create=true, logs each item as a `submittal` record (and a
    `spec_section` if a section number is present), building the submittal log from the spec book."""
    from .. import ai, specs
    from .. import modules as me
    text = (body or {}).get("text") or ""
    res = ai.extract_submittals(text)
    if (body or {}).get("create") and res.get("items"):
        sec_no = specs.parse_section_number(text)
        created_subs = 0
        if sec_no and "spec_section" in me.TABLES:
            me.create_record(db, "spec_section", pid,
                             {"data": {"section_number": sec_no, "title": f"Section {sec_no}",
                                       "submittals_required": text[:4000]}}, actor, None)
        for it in res["items"]:
            data = {"title": it.get("title", "")[:160], "type": it.get("type") or "Product Data"}
            sec = it.get("section_number") or sec_no
            if sec:
                data["spec_section"] = sec
            me.create_record(db, "submittal", pid, {"data": data}, actor, None)
            created_subs += 1
        res["created_submittals"] = created_subs
    return res


@router.get("/projects/{pid}/feasibility")
def site_feasibility(pid: str, gfa: float | None = None, zoning_id: str | None = None,
                     db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Site feasibility / zoning envelope — max buildable GFA (binding min of FAR vs. the physical
    envelope), unit yield, parking demand + required open space, reconciled against the model's
    actual GFA. Pass ?gfa= to override the actual GFA, else it's read from the source IFC if present."""
    from .. import feasibility as feas_engine
    actual = gfa
    if actual is None:
        try:                                            # best-effort model GFA (no IFC -> skip)
            from aec_data import spaces as sp  # type: ignore
            from aec_data.ifc_loader import open_model  # type: ignore

            from ..deps import source_ifc_path
            model = open_model(source_ifc_path(db, pid))
            actual = round(sum(r["net_area"] for r in sp.space_schedule(model) if r.get("net_area")) * 10.7639, 1) or None
        except Exception:
            actual = None
    return feas_engine.feasibility(db, pid, actual_gfa_sf=actual, zoning_id=zoning_id)


@router.get("/projects/{pid}/feasibility/compare")
def feasibility_compare(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Scenario comparison — rank every zoning scheme by buildable yield (units, then GFA), with
    deltas vs. the top scheme. One zoning record = one scheme (e.g. 'Scheme A FAR 6' vs 'B FAR 8')."""
    from .. import feasibility as feas_engine
    return feas_engine.compare(db, pid)


@router.get("/projects/{pid}/precon/estimate-continuity")
def precon_estimate_continuity(pid: str, budget: float | None = None, db: Session = Depends(get_db),
                               _: str = Depends(require_role("viewer"))):
    """Preconstruction estimate continuity — per-milestone totals + $/SF, milestone-to-milestone cost
    drift, and the gap vs the project budget/GMP (pass ?budget= to override the GMP baseline)."""
    return precon_engine.estimate_continuity(db, pid, budget)


@router.get("/projects/{pid}/precon/decisions")
def precon_decisions(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Preconstruction decision log — by status/alignment + open cost & schedule exposure."""
    return precon_engine.decision_log(db, pid)


@router.get("/projects/{pid}/precon/assumptions")
def precon_assumptions(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Assumptions & clarifications register — by status/category + open allowance exposure."""
    return precon_engine.assumptions(db, pid)


@router.get("/projects/{pid}/precon/ve")
def precon_ve(pid: str, target: float | None = None, db: Session = Depends(get_db),
              _: str = Depends(require_role("viewer"))):
    """Value-engineering cycle — proposed/accepted/rejected savings; pass ?target= for gap-to-close."""
    return precon_engine.ve_log(db, pid, target)


@router.get("/projects/{pid}/precon/alignment")
def precon_alignment(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Calibrate-style preconstruction alignment — estimate-vs-budget, VE coverage of any gap,
    open decisions/assumptions — as per-domain RAG + an alignment score."""
    return precon_engine.alignment(db, pid)


@router.post("/projects/{pid}/precon/snapshot", status_code=201)
def precon_snapshot(pid: str, milestone: str = "SD", db: Session = Depends(get_db),
                    actor: str = Depends(require_role("editor"))):
    """One-click: price the current model (IFC takeoff × unit rates) and save it as an estimate set
    tagged with the given design milestone. 409 if the project has no source IFC yet."""
    from . import modules as me
    from .cost import estimate_from_model
    est = estimate_from_model(pid, db, actor)          # reuses the model estimator (409 if no IFC)
    total = est.get("total") or est.get("grand_total") or 0.0
    gsf = est.get("gfa_sf") or est.get("gsf") or 0.0
    data = {"title": f"{milestone} estimate (from model)", "milestone": milestone,
            "total": round(float(total), 2), "gsf": round(float(gsf), 1) if gsf else None,
            "basis": "ROM", "source": "Model takeoff"}
    rec = me.create_record(db, "estimate_set", pid,
                           {"data": {k: v for k, v in data.items() if v is not None}}, actor, None)
    return {"created": rec.get("id"), "ref": rec.get("ref"), "total": data["total"],
            "milestone": milestone}


@router.get("/projects/{pid}/health")
def project_health(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Executive project-health rollup — per-domain status, overall score, ranked attention items."""
    return health_engine.project_health(db, pid)


@router.get("/projects/{pid}/closeout/summary")
def closeout_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Closeout analytics — punchlist completion/ball-in-court, commissioning, certificates, warranties, O&M."""
    return closeout_engine.closeout_summary(db, pid)


@router.post("/projects/{pid}/cx/seed")
def cx_seed(pid: str, checklists: bool = True, db: Session = Depends(get_db),
            actor: str = Depends(require_role("editor"))):
    """CX-1: seed the commissioning registry from the published model — equipment classes become
    GUID-keyed asset_register records (deduped), and (with `checklists`, the default) every systemed
    asset gets its Pre-Functional + Functional commissioning records, the Functional stamped with
    the system's MEP expected values (FPT)."""
    from .. import audit, cx
    from .properties import _INDEX, _ensure_loaded
    try:
        _ensure_loaded(pid)
    except Exception:                                 # noqa: BLE001 — no model → seed reports it
        pass
    out = cx.seed_assets_from_model(db, pid, _INDEX.get(pid), actor)
    if checklists and out.get("model_scored"):
        out["checklists"] = cx.seed_checklists(db, pid, actor)
    audit.record(db, action="cx.seed", actor=actor, method="POST",
                 path=f"/projects/{pid}/cx/seed",
                 detail={"created": out.get("created", 0),
                         "checklists": (out.get("checklists") or {}).get("created", 0)})
    db.commit()
    return out


@router.get("/projects/{pid}/cx/matrix")
def cx_matrix(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """CX-1: the system × phase completion matrix (total/tested/accepted/pass/fail per cell)."""
    from .. import cx
    return cx.matrix(db, pid)


@router.get("/projects/{pid}/cx/dossier")
def cx_dossier(pid: str, system: str, db: Session = Depends(get_db),
               _: str = Depends(require_role("viewer"))):
    """CX-1: the per-system turnover dossier — assets, tests by phase, FPT expected values from the
    MEP register, and best-effort punch mentions."""
    from .. import cx
    return cx.dossier(db, pid, system)


@router.get("/projects/{pid}/safety/summary")
def safety_summary(pid: str, hours: float | None = None, db: Session = Depends(get_db),
                   _: str = Depends(require_role("viewer"))):
    """Safety analytics — OSHA TRIR/DART/LTIFR, observation mix, toolbox coverage, violations.
    Pass ?hours=<total worker-hours> for exact rates; otherwise estimated from daily-report manpower."""
    return safety_engine.safety_summary(db, pid, hours)


@router.get("/projects/{pid}/daily-reports/summary")
def field_log_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Field-log rollup — manpower trend, weather-impact lost-days, reporting coverage."""
    return dailylog_engine.field_log_summary(db, pid)


@router.get("/projects/{pid}/rfi/register")
def rfi_register(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """RFI register — ball-in-court, overdue, response turnaround, cost/schedule-impact exposure."""
    return rfi_engine.rfi_register(db, pid)


@router.get("/projects/{pid}/quality/summary")
def quality_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Quality dashboard — inspection pass-rate KPIs, NCR disposition/close loop, deficiency ball-in-court."""
    return quality_engine.quality_summary(db, pid)


@router.get("/projects/{pid}/submittals/register")
def submittal_register(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Spec-section submittal register — turnaround, ball-in-court, overdue flags."""
    return sub_engine.submittal_register(db, pid)
