"""Code-compliance endpoints — applicable code sections from a project description (LLM/rules), and a
computed occupancy-load + egress-capacity pre-check over the model (W9-2)."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import audit, codecheck
from ..db import get_db
from ..models import Project, Topic
from ..rbac import current_user, require_role
from ..throttle import rate_limited

router = APIRouter()
_throttle = rate_limited("draft", 30)          # LLM call when a key is set


@router.get("/codes/families")
def code_families(_: str = Depends(current_user)):
    """CODE-1: the model-code family + edition catalog (IBC/IRC/IECC/… on their 3-year cycle) plus the
    documented national baseline. Reference facts — not jurisdiction-specific."""
    from aec_data import codes  # type: ignore

    return codes.families()


@router.get("/codes/adoptions")
def code_adoptions(jurisdiction: str = "", _: str = Depends(current_user)):
    """CODE-1: resolve a jurisdiction (USPS state code, e.g. `CA`) to its adopted code editions — falls
    back to the national baseline when not seeded. Always carries a 'verify with the AHJ' note; adoption
    facts change each cycle. Pass no jurisdiction for the baseline; the seed list is at `/codes/seeded`."""
    from aec_data import codes  # type: ignore

    return codes.resolve(jurisdiction)


@router.get("/codes/seeded")
def code_seeded(_: str = Depends(current_user)):
    """CODE-1: the USPS state codes that have a specific adoption seed (everything else → baseline)."""
    from aec_data import codes  # type: ignore

    return {"jurisdictions": codes.seeded_jurisdictions()}


@router.get("/codes/ids")
def codes_ids(description: str = "", edition: str = "", title: str = "", download: bool = False,
              _: str = Depends(current_user)):
    """CODE-5: the applicable code requirements as a buildingSMART **IDS 1.0** file (the machine-checkable
    subset) from a project description — validate an IFC against it in any IDS checker. `download=true`
    returns the `.ids` XML attachment; otherwise JSON with the fired code topics + `ids_xml`."""
    out = codecheck.code_ids(description, edition or None, title)
    if download:
        from fastapi import Response
        return Response(out["ids_xml"], media_type="application/xml",
                        headers={"Content-Disposition": 'attachment; filename="code-requirements.ids"'})
    return out


@router.post("/projects/{pid}/codecheck")
async def code_check(pid: str, description: str = Body("", embed=True),
                     context: str | None = Body(None, embed=True),
                     _: str = Depends(require_role("viewer")), __: None = Depends(_throttle)):
    """Applicable IBC/ADA/IECC provisions (code + section + requirement) for the described project.
    Claude when an API key is set; a deterministic IBC checklist otherwise. Always confirm with the AHJ."""
    return await run_in_threadpool(codecheck.check, description, context)


@router.get("/projects/{pid}/codecheck/egress")
def codecheck_egress(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W9-2: COMPUTED occupancy load (IBC 1004) + egress capacity (IBC 1005) from the model's
    IfcSpaces/IfcDoors — the depth layer above the presence-only /elements/code-check. Reads spaces
    straight from the source IFC (they aren't in the physical-element index). Pre-check assist with
    cited IBC sections; NOT a certified review."""
    from aec_data.ifc_loader import open_model  # type: ignore

    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc:
        raise HTTPException(409, "no source IFC — occupancy/egress needs a model with IfcSpaces")
    return codecheck.egress_from_model(open_model(p.source_ifc))


@router.get("/projects/{pid}/codecheck/analysis")
def code_analysis(pid: str, occupancy_group: str = "", construction_type: str = "",
                  sprinklered: bool = False, jurisdiction: str = "", db: Session = Depends(get_db),
                  _: str = Depends(require_role("viewer"))):
    """W11 D1: the IBC **code-analysis summary** for the G-series code sheet — occupancy classification,
    construction type, gross area + stories, computed occupant load + egress, and the governing sections
    for allowable area/height and fire ratings. Pre-check assist; verify allowable area with the AHJ."""
    from aec_data.ifc_loader import open_model  # type: ignore

    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc:
        raise HTTPException(409, "no source IFC — the code analysis needs a model with IfcSpaces")
    return codecheck.code_analysis(open_model(p.source_ifc), occupancy_group, construction_type,
                                   sprinklered, jurisdiction)


@router.get("/projects/{pid}/codecheck/approvability")
def approvability(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W11 D8: a **plan-reviewer pre-flight checklist** — egress traced, doors at clear width, occupancy
    classified, fire-rated assemblies substantiated — with a readiness score. Pre-check assist; NOT a
    certified review. Needs a source IFC."""
    from aec_data.ifc_loader import open_model  # type: ignore

    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc:
        raise HTTPException(409, "no source IFC — the approvability check needs a model")
    return codecheck.approvability(open_model(p.source_ifc))


@router.get("/projects/{pid}/permit/readiness")
def permit_readiness(pid: str, occupancy_group: str = "", construction_type: str = "",
                     sprinklered: bool = False, jurisdiction: str = "",
                     db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """PERMIT-CHECK: permit-submission readiness — the intake report a permit tech would produce.
    Composes the computed egress check (rejection-grade), the approvability pre-flight, the code-analysis
    summary (jurisdiction edition), and the drawing register's required sheet series into one checklist +
    ranked deficiency list with a READY / NOT-READY verdict. Pre-check assist; the AHJ rules."""
    from aec_data.ifc_loader import open_model  # type: ignore

    from .. import permit_check
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc:
        raise HTTPException(409, "no source IFC — permit readiness needs a model")
    return permit_check.readiness(db, pid, open_model(p.source_ifc),
                                  occupancy_group=occupancy_group,
                                  construction_type=construction_type,
                                  sprinklered=sprinklered, jurisdiction=jurisdiction)


@router.get("/projects/{pid}/rfi/readiness")
def rfi_readiness(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """RFI-0: the **decision-readiness audit** — the proactive inverse of the RFI. Scans the model for the
    information gaps a builder would have to ask about (failed code checks, missing details/keynotes,
    model-data gaps, open clashes), ranked, as one resolve-before-issue list. Composes the approvability
    pre-flight + detail-rule validator + model-hygiene + clash coordination. Needs a source IFC."""
    from aec_data.ifc_loader import open_model  # type: ignore

    from .. import rfi_prevention
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc:
        raise HTTPException(409, "no source IFC — the readiness audit needs a model")
    return rfi_prevention.decision_readiness(db, pid, open_model(p.source_ifc))


@router.post("/projects/{pid}/rfi/qa")
def rfi_qa_ask(pid: str, body: dict, db: Session = Depends(get_db),
               _: str = Depends(require_role("viewer"))):
    """RFI-0 NL-QA: ask a plain-language question and get a **cited** answer from the model's own data —
    'what governs <element>?', 'what's blocking approval?', 'what is spec section 05 12 00?'. Routes to
    the doc-graph / decision-readiness; every claim carries a citation (GUID · spec section · document
    sheet). Body: {question}. Needs a source IFC."""
    from aec_data.ifc_loader import open_model  # type: ignore

    from .. import rfi_qa
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc:
        raise HTTPException(409, "no source IFC — NL-QA needs a model")
    question = (body or {}).get("question", "")
    if not str(question).strip():
        raise HTTPException(400, "a 'question' is required")
    return rfi_qa.ask(db, pid, open_model(p.source_ifc), str(question))


@router.get("/codes/ebc/pathways")
def ebc_pathways(_: str = Depends(current_user)):
    """CODE-EBC: the IEBC existing-building reference catalog — the three compliance methods and the
    Work-Area classifications (Repair · Alteration 1/2/3 · Change of Occupancy · Addition) with citations.
    Facts of law; verify the edition + classification with the AHJ."""
    from aec_data import ebc  # type: ignore

    return ebc.pathways()


@router.get("/projects/{pid}/codecheck/ebc")
def codecheck_ebc(
    pid: str,
    jurisdiction: str = "",
    infer: bool = False,
    adds_area: bool | None = None,
    changes_occupancy: bool | None = None,
    reconfigures_space: bool | None = None,
    alters_openings: bool | None = None,
    alters_systems: bool | None = None,
    adds_equipment: bool | None = None,
    replaces_same_purpose: bool | None = None,
    repair_only: bool | None = None,
    work_area_pct: float | None = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_role("viewer")),
):
    """CODE-EBC: classify an existing-building scope under the IEBC Work Area Compliance Method →
    Repair · Alteration Level 1/2/3 · Change of Occupancy · Addition, with the driving citations and the
    jurisdiction's adopted IEBC edition. Pass explicit scope flags; with `infer=true` the scope is
    first-guessed from the model's phasing (existing vs new/demolish) and any flags you pass override the
    guess. Preliminary classification — the AHJ makes the determination."""
    from aec_data import ebc  # type: ignore

    scope = {k: v for k, v in {
        "adds_area": adds_area, "changes_occupancy": changes_occupancy,
        "reconfigures_space": reconfigures_space, "alters_openings": alters_openings,
        "alters_systems": alters_systems, "adds_equipment": adds_equipment,
        "replaces_same_purpose": replaces_same_purpose, "repair_only": repair_only,
        "work_area_pct": work_area_pct,
    }.items() if v is not None}

    if infer:
        from aec_data.ifc_loader import open_model  # type: ignore

        p = db.get(Project, pid)
        if not p:
            raise HTTPException(404, "project not found")
        if not p.source_ifc:
            raise HTTPException(409, "no source IFC — phasing inference needs a model (or pass infer=false)")
        return ebc.from_model(open_model(p.source_ifc), jurisdiction=(jurisdiction or None), **scope)

    return ebc.classify(jurisdiction=(jurisdiction or None), **scope)


@router.post("/projects/{pid}/codecheck/egress/bcf")
def egress_to_bcf(pid: str, db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """W9-2b: promote the computed egress/code findings to **BCF topics** — so a below-min door or an
    egress shortfall becomes a trackable issue that round-trips with clashes/RFIs (keyed by GlobalId).
    Idempotent-ish: re-running adds fresh topics, so run once per review."""
    from aec_data.ifc_loader import open_model  # type: ignore

    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc:
        raise HTTPException(409, "no source IFC")
    model = open_model(p.source_ifc)
    r = codecheck.egress_from_model(model)

    # a GUID -> world XYZ (metres) lookup so topics get a 3D anchor and appear in the Issues panel
    import ifcopenshell.util.placement as up  # type: ignore
    import ifcopenshell.util.unit as uu  # type: ignore
    scale = uu.calculate_unit_scale(model)

    def _anchor(guid: str) -> dict | None:
        try:
            el = model.by_guid(guid)
            m = up.get_local_placement(el.ObjectPlacement)
            return {"x": float(m[0][3]) * scale, "y": float(m[2][3]) * scale, "z": float(-m[1][3]) * scale}
        except Exception:  # noqa: BLE001
            return None

    center = None
    for s in r["spaces"]:
        if s.get("load"):
            center = _anchor(s["guid"])
            if center:
                break

    # idempotent refresh: clear prior code-check topics so re-running doesn't pile up duplicates
    db.query(Topic).filter(Topic.project_id == pid, Topic.type == "codecheck").delete()

    created: list[Topic] = []
    for guid in r["doors"]["fail_guids"]:
        created.append(Topic(
            project_id=pid, type="codecheck", status="open", priority="high",
            title="Egress door below 32 in clear width (IBC 1010.1.1)",
            description="Door clear width is below the 32 in (0.81 m) minimum required for egress.",
            element_guids=[guid], anchor=_anchor(guid) or center, labels=["code", "egress"], author=actor))
    if r["egress"]["adequate"] is False:
        created.append(Topic(
            project_id=pid, type="codecheck", status="open", priority="high",
            title=f"Egress width short — {r['egress']['provided_width_in']} in provided "
                  f"< {r['egress']['required_width_in']} in required (IBC 1005.3)",
            description=f"Building occupant load {r['building']['occupant_load']} requires "
                        f"{r['egress']['required_width_in']} in of egress width; the model provides "
                        f"{r['egress']['provided_width_in']} in of egress-capable doors.",
            anchor=center, labels=["code", "egress"], author=actor))
    for s in r["spaces"]:
        if s.get("needs_2_exits"):
            created.append(Topic(
                project_id=pid, type="codecheck", status="open",
                title=f"Two exits required — {s.get('name') or 'space'} load {s['load']} > 49 (IBC 1006.2)",
                description=f"Occupant load {s['load']} exceeds 49; two exits/exit accesses are required.",
                element_guids=[s["guid"]], anchor=_anchor(s["guid"]) or center,
                labels=["code", "egress"], author=actor))
    for t in created:
        db.add(t)
    audit.record(db, action="codecheck.create_topics", actor=actor, method="POST",
                 path=f"/projects/{pid}/codecheck/egress/bcf", detail={"created": len(created)})
    db.commit()
    return {"created": len(created), "topics": [t.id for t in created]}


@router.post("/projects/{pid}/rfi/readiness/bcf")
def readiness_to_bcf(pid: str, db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """RFI-0: promote the **decision-readiness gaps** to BCF topics — every information gap a builder would
    otherwise have to raise an RFI about (failed code checks, missing details, model-data holes, open
    clashes) becomes a trackable, GUID-anchored issue that round-trips with clashes/RFIs. One topic per gap,
    priority from the gap's severity. Idempotent: re-running clears prior readiness topics first."""
    from aec_data.ifc_loader import open_model  # type: ignore

    from .. import rfi_prevention
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc:
        raise HTTPException(409, "no source IFC — the readiness audit needs a model")
    model = open_model(p.source_ifc)
    audit_r = rfi_prevention.decision_readiness(db, pid, model)

    import ifcopenshell.util.placement as up  # type: ignore
    import ifcopenshell.util.unit as uu  # type: ignore
    scale = uu.calculate_unit_scale(model)

    def _anchor(guid: str) -> dict | None:
        try:
            el = model.by_guid(guid)
            m = up.get_local_placement(el.ObjectPlacement)
            return {"x": float(m[0][3]) * scale, "y": float(m[2][3]) * scale, "z": float(-m[1][3]) * scale}
        except Exception:  # noqa: BLE001
            return None

    # idempotent refresh: clear prior readiness topics so re-running doesn't pile up duplicates
    db.query(Topic).filter(Topic.project_id == pid, Topic.type == "readiness").delete()

    created: list[Topic] = []
    for g in audit_r["gaps"]:
        guids = [x for x in (g.get("guids") or []) if x]
        detail = g.get("detail", "") or ""
        fix = g.get("fix", "") or ""
        cite = g.get("citation")
        desc = detail + (f"  Fix: {fix}." if fix else "") + (f"  ({cite})" if cite else "")
        labels = ["readiness", g["category"]]
        created.append(Topic(
            project_id=pid, type="readiness", status="open",
            priority="high" if g["severity"] == "high" else "normal",
            title=g["title"][:200],
            description=desc.strip(),
            element_guids=guids or None,
            anchor=(_anchor(guids[0]) if guids else None),
            labels=labels, author=actor))
    for t in created:
        db.add(t)
    audit.record(db, action="readiness.create_topics", actor=actor, method="POST",
                 path=f"/projects/{pid}/rfi/readiness/bcf",
                 detail={"created": len(created), "ready": audit_r.get("ready")})
    db.commit()
    return {"created": len(created), "topics": [t.id for t in created],
            "ready": audit_r.get("ready"), "high_severity": audit_r.get("high_severity")}
