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


def _explicit_specs(body: dict) -> tuple[str, list[dict]]:
    """The `{title, specs:[...]}` half of the body — the half no engine wrapper covers.

    **R37-TESTED-UNWIRED CONSOLIDATE.** This used to handle the `use_case` half too, by looking the
    case up itself and calling the PRIVATE `ia._specs_for` — reimplementing `build_from_use_case` and
    `eir_for_use_case`, which is why both of those had no caller anywhere. The routes below now call
    them, so the duplication and the two orphans go together; what is left here is the genuinely
    router-side case, where the caller supplies specs and there is nothing to look up.
    """
    specs = body.get("specs") or []
    if not specs:
        raise HTTPException(422, "provide a use_case or a non-empty specs list")
    return body.get("title") or "Information requirements", specs


@router.post("/ids/build")
def build_ids(body: dict = Body(...), _: str = Depends(current_user)):
    """Build a standards-valid IDS 1.0 XML from a use case or explicit specs → downloadable .ids file."""
    try:
        if body.get("use_case"):
            xml = ia.build_from_use_case(
                body["use_case"], body.get("title") or "", ifc_version=body.get("ifc_version", "IFC4"),
                author=body.get("author", ""), purpose=body.get("purpose", ""))
        else:
            title, specs = _explicit_specs(body)
            xml = ia.build_ids(title, specs, ifc_version=body.get("ifc_version", "IFC4"),
                               author=body.get("author", ""), purpose=body.get("purpose", ""))
    except HTTPException:
        raise
    except Exception as e:                               # noqa: BLE001 — malformed spec input
        raise HTTPException(422, f"could not build IDS: {e}")
    return Response(xml, media_type="application/xml",
                    headers={"Content-Disposition": 'attachment; filename="requirements.ids"'})


@router.post("/ids/eir")
def build_eir(body: dict = Body(...), _: str = Depends(current_user)):
    """Generate an Exchange Information Requirements (EIR) markdown document for the BIM contract.

    An unknown use case is a 422 here because `eir_for_use_case` now raises `ValueError` like its
    sibling. It raised a bare `KeyError` until this route started calling it — so the consolidation
    had to fix that first, or it would have swapped a working 422 for a 500."""
    try:
        if body.get("use_case"):
            md = ia.eir_for_use_case(body["use_case"], body.get("title") or "",
                                     project=body.get("project", ""), author=body.get("author", ""))
        else:
            title, specs = _explicit_specs(body)
            md = ia.eir_markdown(title, specs, project=body.get("project", ""),
                                 author=body.get("author", ""))
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(422, str(e))
    return Response(md, media_type="text/markdown",
                    headers={"Content-Disposition": 'attachment; filename="EIR.md"'})
