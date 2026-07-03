"""IDS authoring endpoints — templates, build a buildingSMART IDS 1.0 file, and generate an EIR.
Model compliance-checking against an IDS is the existing validate endpoint (/projects/{pid}/validate)."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Response

from .. import ids_authoring as ia
from ..rbac import current_user

router = APIRouter()


@router.get("/ids/templates")
def ids_templates(_: str = Depends(current_user)):
    """The authoring catalog: element requirement templates + use-case bundles."""
    return ia.templates()


def _specs_from(body: dict) -> tuple[str, list[dict]]:
    """Accept either {use_case} or {title, specs:[...]}."""
    if body.get("use_case"):
        uc = ia.USE_CASES.get(body["use_case"])
        if not uc:
            raise HTTPException(422, f"unknown use case {body['use_case']!r}")
        return body.get("title") or uc["label"], ia._specs_for(uc["groups"])
    specs = body.get("specs") or []
    if not specs:
        raise HTTPException(422, "provide a use_case or a non-empty specs list")
    return body.get("title") or "Information requirements", specs


@router.post("/ids/build")
def build_ids(body: dict = Body(...), _: str = Depends(current_user)):
    """Build a standards-valid IDS 1.0 XML from a use case or explicit specs → downloadable .ids file."""
    title, specs = _specs_from(body)
    try:
        xml = ia.build_ids(title, specs, ifc_version=body.get("ifc_version", "IFC4"),
                           author=body.get("author", ""), purpose=body.get("purpose", ""))
    except Exception as e:                               # noqa: BLE001 — malformed spec input
        raise HTTPException(422, f"could not build IDS: {e}")
    return Response(xml, media_type="application/xml",
                    headers={"Content-Disposition": 'attachment; filename="requirements.ids"'})


@router.post("/ids/eir")
def build_eir(body: dict = Body(...), _: str = Depends(current_user)):
    """Generate an Exchange Information Requirements (EIR) markdown document for the BIM contract."""
    title, specs = _specs_from(body)
    md = ia.eir_markdown(title, specs, project=body.get("project", ""), author=body.get("author", ""))
    return Response(md, media_type="text/markdown",
                    headers={"Content-Disposition": 'attachment; filename="EIR.md"'})
