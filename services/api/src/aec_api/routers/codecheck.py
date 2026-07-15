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
