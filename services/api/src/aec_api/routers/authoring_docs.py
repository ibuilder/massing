"""Documentation & provenance endpoints (REL-3 leaf split of `authoring.py`): the drawing set
(plan/sheet/schedule SVG · CSV · PDF), the spec manual, detailing/keynote QA, and the document graph.
URLs are unchanged — `authoring.py` includes this router, so callers and tests see the same paths."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..rbac import require_role
from .authoring_shared import project_with_source as _project
from .authoring_shared import safe_filename as _safe_filename

router = APIRouter()


@router.get("/projects/{pid}/drawings/plan.svg")
def plan_svg(pid: str, storey: str | None = None, scale: int = 100, db: Session = Depends(get_db),
             _: str = Depends(require_role("viewer"))):
    """W11 C1: a schematic **plan drawing** (SVG) generated from element footprints — the first slice of
    the construction-document set. `storey` limits to one level; `scale` is the drawing scale (1:scale).
    Class-styled poché so a stylesheet controls linework."""
    from aec_data import drawing  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    result = drawing.plan_svg(open_model(p.source_ifc), storey=storey, scale=int(scale))
    return Response(content=result["svg"], media_type="image/svg+xml",
                    headers={"X-Plan-Elements": str(result["elements"])})


@router.get("/projects/{pid}/drawings/sheet.svg")
def sheet_svg(pid: str, storey: str | None = None, scale: int = 100, number: str = "A-101",
              title: str = "FLOOR PLAN", db: Session = Depends(get_db),
              _: str = Depends(require_role("viewer"))):
    """W11 C3: an issuable **sheet** — ARCH-D border + titleblock (project name, sheet number, scale,
    north arrow) with the plan placed in a scaled viewport. The construction-document deliverable."""
    from aec_data import drawing  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    result = drawing.sheet_svg(open_model(p.source_ifc), storey=storey, scale=int(scale),
                               project=p.name or "Project", number=number, title=title)
    return Response(content=result["svg"], media_type="image/svg+xml",
                    headers={"X-Sheet-Number": result["number"]})


@router.get("/projects/{pid}/drawings/schedules")
def drawing_schedules(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W11 C4: computed door / window / room schedules from the model (marks, sizes, types, levels, areas)
    — the tabular half of a CD set."""
    from aec_data import drawing  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return drawing.schedules(open_model(p.source_ifc))


@router.get("/projects/{pid}/drawings/schedule.svg")
def schedule_svg(pid: str, kind: str = "doors", db: Session = Depends(get_db),
                 _: str = Depends(require_role("viewer"))):
    """W11 C4: one schedule (doors|windows|rooms) rendered as an SVG table."""
    from aec_data import drawing  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    try:
        result = drawing.schedule_svg(open_model(p.source_ifc), kind=kind)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return Response(content=result["svg"], media_type="image/svg+xml",
                    headers={"X-Schedule-Rows": str(result["rows"])})


@router.get("/projects/{pid}/drawings/schedule.csv")
def schedule_csv(pid: str, kind: str = "", db: Session = Depends(get_db),
                 _: str = Depends(require_role("viewer"))):
    """W10-6: the computed schedule(s) as a CSV download — `kind` (doors|windows|rooms) for one, or omit
    for all three. For spreadsheets / procurement / submittals."""
    from aec_data import drawing  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    csv_text = drawing.schedule_csv(open_model(p.source_ifc), kind=kind or None)
    fn = f"schedule-{kind or 'all'}.csv"
    return Response(content=csv_text, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@router.get("/projects/{pid}/drawings/schedule.pdf")
def schedule_pdf(pid: str, kinds: str = "doors,windows,rooms", number: str = "A-601",
                 title: str = "SCHEDULES", db: Session = Depends(get_db),
                 _: str = Depends(require_role("viewer"))):
    """W11 C6: the computed schedules laid out on an issuable ARCH-D **sheet** (border + titleblock) as a
    submittable PDF. `kinds` is a comma list of doors|windows|rooms."""
    from aec_data import drawing  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    want = [k.strip() for k in kinds.split(",") if k.strip() in ("doors", "windows", "rooms")]
    pdf = drawing.schedule_pdf(open_model(p.source_ifc), kinds=want or None,
                               project=p.name or "Project", number=number, title=title)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{_safe_filename(number)}.pdf"'})


@router.get("/projects/{pid}/drawings/sheet.pdf")
def sheet_pdf(pid: str, storey: str | None = None, scale: int = 100, number: str = "A-101",
              title: str = "FLOOR PLAN", db: Session = Depends(get_db),
              _: str = Depends(require_role("viewer"))):
    """W11 C3b: the issuable sheet rendered to **PDF** (reportlab) — the submittable construction-document
    deliverable. ARCH-D border + titleblock + plan poché + dimensions + keynote legend."""
    from aec_data import drawing  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    data = drawing.sheet_pdf(open_model(p.source_ifc), storey=storey, scale=int(scale),
                             project=p.name or "Project", number=number, title=title)
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{_safe_filename(number)}.pdf"'})


@router.get("/projects/{pid}/spec/manual")
def spec_manual(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W11 D6: the 3-part MasterFormat **project manual** seeded from the model — elements grouped into CSI
    divisions → sections, each in SectionFormat Part 1/2/3 (Products from element types+materials, Execution
    from attached install docs). The spec book that accompanies the drawings."""
    from aec_data import specmanual  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return specmanual.project_manual(open_model(p.source_ifc))


@router.get("/projects/{pid}/spec/manual.txt")
def spec_manual_text(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W11 D6: the project manual rendered as a downloadable plain-text spec outline."""
    from aec_data import specmanual  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    text = specmanual.manual_text(open_model(p.source_ifc), project=p.name or "Project")
    return Response(content=text, media_type="text/plain",
                    headers={"Content-Disposition": f'attachment; filename="{_safe_filename(pid, "manual")}-manual.txt"'})


@router.get("/projects/{pid}/detailing/rules/validate")
def validate_detailing(pid: str, db: Session = Depends(get_db),
                       _: str = Depends(require_role("viewer"))):
    """W11 D3: IDS-style QA — for every element a seed rule applies to, report the ones missing their
    required keynote/spec code (the 'components missing a keynote' pre-flight). Read-only."""
    from aec_data import rules  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return rules.validate_rules(open_model(p.source_ifc))


@router.get("/projects/{pid}/detailing/{guid}")
def element_detailing(pid: str, guid: str, db: Session = Depends(get_db),
                      _: str = Depends(require_role("viewer"))):
    """W11 Track D: one element's attached carriers — classification codes (UniFormat/MasterFormat/
    OmniClass keynote+spec codes) and documents (details/installation instructions). Written by the
    `classify` and `attach_document` recipes; consumed by keynote/schedule/spec/drawing generation."""
    from aec_data import detailing  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    try:
        return detailing.element_detailing(open_model(p.source_ifc), guid)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(404, f"element {guid} not found") from e


@router.get("/projects/{pid}/doc-graph")
def doc_graph(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W9-4 (harder half): the document / specification graph — spec sections (classification codes) and
    attached documents (with sheet refs) linked to the elements they govern. The cited-source layer."""
    from aec_data import docgraph  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return docgraph.build(open_model(p.source_ifc))


@router.get("/projects/{pid}/elements/{guid}/sources")
def element_sources(pid: str, guid: str, db: Session = Depends(get_db),
                    _: str = Depends(require_role("viewer"))):
    """The cited provenance of one element — its governing spec sections, attached documents (with sheet
    refs), and spatial container. Every fact tagged with its source; the substrate for RFI-0 NL-QA."""
    from aec_data import docgraph  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return docgraph.element_sources(open_model(p.source_ifc), guid)


@router.get("/projects/{pid}/drawings/layout/presets")
def layout_presets(_: str = Depends(require_role("viewer"))):
    """SHEET-VIEWPORTS: the named paper-space viewport arrangements (fraction rects) a client can start
    from — override any field per viewport before posting to layout.svg/.pdf."""
    from aec_data import sheet_layout  # type: ignore

    return {name: sheet_layout.presets(name) for name in ("key", "quad", "plan-pair")}


@router.post("/projects/{pid}/drawings/layout.svg")
def layout_svg(pid: str, viewports: list[dict] = Body(..., embed=True),
               meta: dict | None = Body(default=None, embed=True),
               page: str = Body(default="A1", embed=True),
               db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """SHEET-VIEWPORTS: compose paper-space viewports — each with its view (plan/section/elevation), an
    optional FIXED drawing scale (true 1:N on paper, geometry clipped to the viewport rect — crop, not
    shrink), and an optional per-viewport class freeze — rendered through the shared titleblock."""
    from aec_data import sheet_layout  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    m = {"project": p.name or "Project", "number": "A-100", "title": "LAYOUT", **(meta or {})}
    svg = sheet_layout.layout_sheet(open_model(p.source_ifc), viewports, m, page=page, fmt="svg")
    return Response(content=svg, media_type="image/svg+xml")


@router.post("/projects/{pid}/drawings/layout.pdf")
def layout_pdf(pid: str, viewports: list[dict] = Body(..., embed=True),
               meta: dict | None = Body(default=None, embed=True),
               page: str = Body(default="A1", embed=True),
               db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """SHEET-VIEWPORTS: the paper-space viewport sheet as a submittable PDF."""
    from aec_data import sheet_layout  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    m = {"project": p.name or "Project", "number": "A-100", "title": "LAYOUT", **(meta or {})}
    pdf = sheet_layout.layout_sheet(open_model(p.source_ifc), viewports, m, page=page, fmt="pdf")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'inline; filename="{_safe_filename(str(m.get("number") or "layout"))}.pdf"'})
