"""2D documentation endpoints (Revit-style plans/sections, openBIM). Returns SVG generated
from the project source IFC by the data service."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from .. import drawingset, issuance, pdfops, sheetgen
from ..db import get_db
from ..deps import source_ifc_path as _source_ifc
from ..models import Project
from ..rbac import current_user, require_role
from ..throttle import rate_limited

_DATA_SRC = Path(__file__).resolve().parents[4] / "data" / "src"
if str(_DATA_SRC) not in sys.path:
    sys.path.insert(0, str(_DATA_SRC))

router = APIRouter()

# Whole-model triangulation (glTF export) is the heaviest geometry op here — cap per caller.
_export_throttle = rate_limited("model_export", 10)


@router.get("/projects/{pid}/drawing-set/qa")
def drawing_set_qa(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """QA-AGENT: the drawing-set QA review — set integrity (duplicates/gaps/titleblock), issuance
    hygiene, and model cross-checks (plans-per-storey, schedule-vs-model counts, discipline coverage),
    every finding cited to its sheet. Computed from the structured register + model source — no raster
    interpretation. Runs without a model (register checks only) and adds the cross-checks when one exists."""
    from aec_data.ifc_loader import open_model  # type: ignore

    from .. import drawing_qa
    model = None
    try:
        model = open_model(_source_ifc(db, pid))
    except Exception:  # noqa: BLE001 — no model → register-only review (the report says so)
        model = None
    return drawing_qa.review(db, pid, model)


@router.get("/projects/{pid}/drawing-set")
def get_drawing_set(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Controlled drawing-set register from the `drawing` records: current set (latest revision per
    sheet), superseded revisions, sheet index + discipline rollup + issuance (new vs revised)."""
    return drawingset.drawing_set(db, pid)


@router.get("/projects/{pid}/drawing-set/transmittal.pdf")
def drawing_set_transmittal(pid: str, to: str = "", note: str = "", db: Session = Depends(get_db),
                            _: str = Depends(require_role("viewer"))):
    """A transmittal PDF of the controlled current set (recipients via `to`, comma-separated)."""
    reg = drawingset.drawing_set(db, pid)
    p = db.get(Project, pid)
    recipients = [r.strip() for r in to.split(",") if r.strip()]
    pdf = drawingset.transmittal_pdf(reg, p.name if p else pid, recipients, note)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="drawing-transmittal.pdf"'})


def _hero_key(pid: str) -> str:
    return f"{pid}/hero.png"


@router.put("/projects/{pid}/hero")
async def put_hero(pid: str, file: UploadFile = File(...), db: Session = Depends(get_db),
                   _: str = Depends(require_role("editor"))):
    """3D-HERO: pin a captured viewer screenshot (PNG/JPEG) as the project's hero image — it becomes
    page 2 of the client project package. 10 MB cap; magic-byte checked."""
    from .. import storage
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "hero image too large (10 MB cap)")
    if not (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:2] == b"\xff\xd8"):
        raise HTTPException(400, "expected a PNG or JPEG image")
    storage.put(_hero_key(pid), data)
    return {"stored": True, "bytes": len(data)}


@router.get("/projects/{pid}/hero")
def get_hero(pid: str, _: str = Depends(require_role("viewer"))):
    """The project's hero image (404 when none captured)."""
    from .. import storage
    key = _hero_key(pid)
    if not storage.exists(key):
        raise HTTPException(404, "no hero image captured")
    data = storage.get(key)
    media = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    return Response(data, media_type=media)


@router.delete("/projects/{pid}/hero")
def delete_hero(pid: str, _: str = Depends(require_role("editor"))):
    from .. import storage
    key = _hero_key(pid)
    existed = storage.exists(key)
    if existed:
        storage.delete(key)
    return {"deleted": existed}


@router.get("/projects/{pid}/project-package/contents")
def project_package_contents(pid: str, db: Session = Depends(get_db),
                             _: str = Depends(require_role("viewer"))):
    """What the shareable project package will contain for this project (model / budget availability)."""
    from .. import package
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return package.package_contents(db, pid)


@router.get("/projects/{pid}/project-package.pdf")
def project_package(pid: str, max_sheets: int = 8, db: Session = Depends(get_db),
                    _: str = Depends(require_role("viewer"))):
    """The **shareable project package** — one PDF a GC or architect hands to a client: a cover, a visual
    overview (plan · section · elevation), the drawing set, and a cost & feasibility summary (model-takeoff
    estimate by discipline + the developer budget's capital stack). Needs a source IFC."""
    from .. import package
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    src = _source_ifc(db, pid)                       # 409 if no accessible source IFC
    pdf = package.project_package_pdf(db, pid, p.name or pid, src, max_sheets=int(max_sheets))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{(p.name or pid)}-package.pdf"'})


@router.get("/projects/{pid}/drawing-set/compiled.pdf")
def drawing_set_compiled(pid: str, scale: int = 200, max_sheets: int = 16, schedules: bool = True,
                         db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The **whole drawing set compiled into one multi-page PDF** — a cover / sheet-index, a floor plan per
    storey (tall towers sample evenly, capped by `max_sheets`), and the door/window/room schedules. The
    single-file handover deliverable. Needs a source IFC."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    src = _source_ifc(db, pid)                       # raises 409 if no accessible source IFC
    pdf = drawingset.compiled_set_pdf(src, p.name or pid, scale=int(scale),
                                      max_sheets=int(max_sheets), include_schedules=bool(schedules))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{(p.name or pid)}-drawing-set.pdf"'})


# --- drawing issuance register (AIA/CD: what went out, when, for what purpose) -------------------
@router.get("/projects/{pid}/drawing-set/issuance-purposes")
def issuance_purposes(_: str = Depends(require_role("viewer"))):
    """The AIA/CD issuance purposes (SD/DD/CD/Permit/Bid/IFC/Addendum/Conformed/Record)."""
    return {"purposes": issuance.purposes()}


@router.get("/projects/{pid}/drawing-set/issuances")
def drawing_issuances(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The issuance history — every release, its purpose, date, sheet count, recipients."""
    return issuance.register(db, pid)


@router.post("/projects/{pid}/drawing-set/issue", status_code=201)
def issue_drawing_set(pid: str, body: dict = Body(default={}), db: Session = Depends(get_db),
                      _: str = Depends(require_role("editor"))):
    """Issue the current drawing set for a purpose — snapshots every current sheet + its revision.
    Body: `{purpose, date?, description?, recipients?, enforce?}`. The **pre-flight issuance gate**
    runs automatically and its verdict is stamped on the issuance record; with `enforce: true` a HOLD
    verdict blocks the issue (409 listing the blocking checks)."""
    purpose = str(body.get("purpose") or "").strip()
    if not purpose:
        from fastapi import HTTPException
        raise HTTPException(422, "purpose is required")
    pf = None
    try:                                    # the gate never breaks issuing unless enforcement asks it to
        from .. import preflight
        pf = preflight.summary(preflight.run(db, pid))
    except Exception:                       # noqa: BLE001 — a gate error is not an issuance error
        pf = None
    if body.get("enforce") and pf and not pf["ready"]:
        from fastapi import HTTPException
        raise HTTPException(409, "pre-flight HOLD — blocking checks: "
                                 + ", ".join(pf["blocking_checks"]) + " (see /preflight)")
    return issuance.issue(db, pid, purpose, body.get("date"),
                          str(body.get("description") or ""), str(body.get("recipients") or ""),
                          preflight=pf)


@router.get("/projects/{pid}/drawing-set/issuance-matrix")
def drawing_issuance_matrix(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The sheet-index × issuance grid — each sheet's revision in each issuance (the front-of-set matrix)."""
    return issuance.matrix(db, pid)


@router.get("/projects/{pid}/drawing-set/issuances/{iid}/transmittal.pdf")
def issuance_transmittal(pid: str, iid: str, db: Session = Depends(get_db),
                         _: str = Depends(require_role("viewer"))):
    """A transmittal PDF for one issuance, stamped with its purpose + date and the sheets released."""
    p = db.get(Project, pid)
    pdf = issuance.transmittal_pdf(db, pid, iid, p.name if p else pid)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="issuance-transmittal.pdf"'})


@router.get("/projects/{pid}/drawing-set/issuances/{iid}/sealed.pdf")
def issuance_sealed(pid: str, iid: str, name: str = "", db: Session = Depends(get_db),
                    user: str = Depends(require_role("editor"))):
    """The issuance transmittal digitally **sealed** (PAdES) by the professional of record — the
    tamper-evident electronic seal for permit/IFC submittal. Unsealed if e-sign isn't configured
    (X-Sealed: false)."""
    p = db.get(Project, pid)
    pdf, sealed = issuance.sealed_transmittal_pdf(db, pid, iid, p.name if p else pid, name or user)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="issuance-sealed.pdf"',
                             "X-Sealed": "true" if sealed else "false"})


# --- revision / delta register (AIA revision block) ---------------------------------------------
@router.post("/projects/{pid}/drawings/{drawing_id}/revise", status_code=201)
def revise_drawing(pid: str, drawing_id: str, body: dict = Body(default={}),
                   db: Session = Depends(get_db), user: str = Depends(require_role("reviewer"))):
    """Record a revision (delta) on a sheet — appends to its revision block, bumps the current
    revision, and optionally cites the driving change instrument (ASI/CCD/Addendum/Bulletin).
    Body: `{rev, description?, date?, instrument_type?, instrument_ref?}`."""
    rev = str(body.get("rev") or "").strip()
    if not rev:
        from fastapi import HTTPException
        raise HTTPException(422, "rev is required")
    return drawingset.revise_sheet(db, pid, drawing_id, rev, str(body.get("description") or ""),
                                   body.get("date"), str(body.get("instrument_type") or ""),
                                   str(body.get("instrument_ref") or ""), actor=user)


@router.get("/projects/{pid}/drawing-set/revisions")
def drawing_revisions(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The cross-sheet revision register — every delta on every sheet (newest first) with the driving
    change instrument. The 'what changed, when, why' log."""
    return drawingset.revisions(db, pid)


def _levels_and_series(db: Session, pid: str, disciplines: list[str] | None,
                       all_disciplines: bool, max_levels: int) -> tuple[list[str], list[str]]:
    """Building levels (storey names) + which discipline sheet series to emit, from the model. If the
    caller names disciplines, those win; else all series present in the model (always G/S/A) — or the
    full standard set when `all_disciplines`. Falls back to a single level if the model has no storeys
    (so the endpoint still produces a set for a thin model)."""
    level_names: list[str] = ["Level 1"]
    classes: set[str] = set()
    try:
        from aec_data import drawings as _dw  # type: ignore
        from aec_data.ifc_loader import open_model  # type: ignore
        model = open_model(_source_ifc(db, pid))
        storeys = _dw.storey_elevations(model)
        names = [s.get("name") or f"Level {i + 1}" for i, s in enumerate(storeys)]
        if names:
            level_names = names[:max(1, max_levels)]
        classes = {e.is_a() for e in model}
    except Exception:                          # noqa: BLE001 — thin/absent model still gets a set
        pass
    if disciplines:
        codes = sheetgen.normalize_codes(disciplines)
    elif all_disciplines:
        codes = sheetgen.DEFAULT_CODES
    else:
        codes = sheetgen.detect_series(classes)
    return level_names, (codes or sheetgen.DEFAULT_CODES)


@router.get("/projects/{pid}/drawing-set/plan")
def drawing_set_plan(pid: str, disciplines: str = "", all: bool = False, max_levels: int = 60,
                     db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Preview the discipline sheet set that would be generated (no records created): one series per
    discipline with NCS sheet numbers (M-/FA-/S-/…), a plan per level, plus sections/details/schedules.
    `disciplines` is a comma-separated list of designators or names; `all=true` forces the full set."""
    disc = [d.strip() for d in disciplines.split(",") if d.strip()]
    levels, codes = _levels_and_series(db, pid, disc or None, all, max_levels)
    sheets = sheetgen.plan_set(levels, codes)
    from collections import Counter
    return {"levels": len(levels), "series": codes, "sheet_count": len(sheets),
            "by_discipline": dict(Counter(s["discipline"] for s in sheets)), "sheets": sheets}


@router.post("/projects/{pid}/drawing-set/generate", status_code=201)
def generate_drawing_set(pid: str, body: dict = Body(default={}),
                         db: Session = Depends(get_db), _: str = Depends(require_role("editor"))):
    """Generate the discipline sheet set as `drawing` records — one sheet series per discipline with
    its own NCS designator (A-/S-/M-/E-/P-/FP-/FA-/T-/…), a plan per building level, and the usual
    sections/details/schedules. Body: `{disciplines?:[…], all?:bool, max_levels?:int}`. Idempotent —
    existing sheet numbers are skipped. Flows straight into the drawing-set register + transmittal."""
    disc = body.get("disciplines") or None
    levels, codes = _levels_and_series(db, pid, disc, bool(body.get("all")),
                                       int(body.get("max_levels") or 60))
    return sheetgen.generate(db, pid, levels, codes)


# --- PDF manipulation (pypdf; no PyMuPDF/AGPL) — merge/split/rotate/extract uploaded PDFs ---------
async def _read_pdf(f: UploadFile) -> bytes:
    data = await f.read()
    if data[:4] != b"%PDF":
        raise HTTPException(422, f"{f.filename or 'file'} is not a PDF")
    return data


@router.post("/pdf/info")
async def pdf_info(file: UploadFile = File(...), _: str = Depends(current_user)):
    """Page count + flags for an uploaded PDF."""
    return pdfops.info(await _read_pdf(file))


@router.post("/pdf/merge")
async def pdf_merge(files: list[UploadFile] = File(...), _: str = Depends(current_user)):
    """Concatenate several uploaded PDFs into one (order = upload order)."""
    if len(files) < 2:
        raise HTTPException(422, "merge needs at least 2 PDFs")
    out = pdfops.merge([await _read_pdf(f) for f in files])
    return Response(out, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="merged.pdf"'})


@router.post("/pdf/split")
async def pdf_split(file: UploadFile = File(...), _: str = Depends(current_user)):
    """Split an uploaded PDF into one PDF per page, returned as a .zip."""
    zipped = pdfops.zip_bytes(pdfops.split(await _read_pdf(file)),
                              stem=(file.filename or "doc").rsplit(".", 1)[0])
    return Response(zipped, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="pages.zip"'})


@router.post("/pdf/extract")
async def pdf_extract(file: UploadFile = File(...), pages: str = Form(...),
                      _: str = Depends(current_user)):
    """A new PDF of just the given pages (`pages` = '1,3,5-7', 1-based)."""
    sel = pdfops.parse_pages(pages)
    if not sel:
        raise HTTPException(422, "no valid page numbers (e.g. '1,3,5-7')")
    out = pdfops.extract(await _read_pdf(file), sel)
    return Response(out, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="extract.pdf"'})


@router.post("/pdf/rotate")
async def pdf_rotate(file: UploadFile = File(...), angle: int = Form(90), pages: str = Form(""),
                     _: str = Depends(current_user)):
    """Rotate pages by `angle` (multiple of 90). `pages` (1-based, '1,3-5') limits it; blank = all."""
    sel = pdfops.parse_pages(pages) or None
    out = pdfops.rotate(await _read_pdf(file), angle, sel)
    return Response(out, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="rotated.pdf"'})


def _json_form(raw: str) -> dict:
    import json
    if not raw:
        return {}
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else {}
    except (ValueError, TypeError) as e:
        raise HTTPException(422, "values/profile must be a JSON object") from e


@router.get("/stamps/library")
def stamps_library(_: str = Depends(current_user)):
    """The A/E/C stamp template library — review (EJCDC + CSI), inspection, status, and seal templates.
    The client renders the picker and preview from this; the server is the source of truth."""
    from .. import stamps
    return {"templates": stamps.library()}


@router.post("/pdf/stamp")
async def pdf_stamp(file: UploadFile = File(...), template_id: str = Form(...),
                    page: int = Form(1), x: float = Form(36), y: float = Form(36),
                    disposition: str = Form(""), values: str = Form(""),
                    _: str = Depends(current_user)):
    """Composite a review / inspection / status stamp onto a page (1-based). (x,y) = top-left of the
    stamp in PDF points from the page's top-left. `values` = JSON object of field values."""
    from .. import stamps
    try:
        out = stamps.apply_stamp(await _read_pdf(file), page - 1, x, y, template_id,
                                 _json_form(values), disposition)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return Response(out, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="stamped.pdf"'})


@router.post("/pdf/seal")
async def pdf_seal(file: UploadFile = File(...), template_id: str = Form(...),
                   page: int = Form(1), x: float = Form(36), y: float = Form(36),
                   sign: bool = Form(True), profile: str = Form(...),
                   _: str = Depends(current_user)):
    """Render a *visible* professional seal + signature block, then apply a tamper-evident PAdES
    signature LAST (unless `sign=false`). `profile` = JSON {name,license_no,state,expiration,date}.
    The self-signed platform cert is demonstration / tamper-evidence, not board-accepted sealing."""
    from starlette.concurrency import run_in_threadpool

    from .. import stamps
    data = await _read_pdf(file)
    prof = _json_form(profile)
    try:
        # pyHanko signing calls asyncio.run internally — run off the event loop.
        out, meta = await run_in_threadpool(stamps.apply_seal, data, page - 1, x, y, template_id,
                                            prof, sign)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return Response(out, media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="sealed.pdf"',
        "X-Seal-Sealed": str(meta["sealed"]).lower(),
        "X-Seal-Cert-Kind": meta.get("cert_kind", ""),
        "X-Seal-Compliance": meta.get("compliance", ""),
    })


def _svg(svg: str) -> Response:
    return Response(svg.encode("utf-8"), media_type="image/svg+xml")


def _safe_name(name: str, fallback: str = "drawing") -> str:
    """Whitelist a download filename segment ([A-Za-z0-9._-]) so a crafted axis/direction/number can't
    break out of the Content-Disposition quoting (defence-in-depth; the value is self-reflected only)."""
    import re as _re
    cleaned = _re.sub(r"[^A-Za-z0-9._-]", "", name or "")[:80]
    return cleaned or fallback


def _dxf(dxf_text: str, name: str) -> Response:
    return Response(dxf_text.encode("utf-8"), media_type="image/vnd.dxf",
                    headers={"Content-Disposition": f'attachment; filename="{_safe_name(name)}.dxf"'})


@router.get("/projects/{pid}/drawings/storeys")
def list_storeys(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    return drawings.storey_elevations(open_model(_source_ifc(db, pid)))


@router.get("/projects/{pid}/model/grid")
def model_grid(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Drafting reference frame: the grid (real IfcGrid axes, else derived from IfcColumn centres) +
    its snap intersections + the storey levels — for the web Draft panel to render and snap against."""
    from aec_data import grid as _grid  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    return _grid.grid_and_levels(open_model(_source_ifc(db, pid)))


@router.get("/projects/{pid}/drawings/plan.svg")
def plan(pid: str, elevation: float = 0.0, cut_height: float = 1.2, title: str = "PLAN",
         rooms: bool = True, callouts: bool = False, view_depth: float | None = None,
         by_discipline: bool = False,
         db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Schematic plan (SVG) cut at `elevation + cut_height`. VIEW-RANGE: pass `view_depth` (metres below
    the cut) to also draw the footprint of anything under the cut but within that depth — foundations/
    footings show as dashed hidden lines, the Revit Top/Cut/Bottom/View-Depth model rather than one cut_z.
    DISC-poché: `by_discipline=true` strokes each element's linework with its discipline color + legend."""
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    svg = drawings.plan_svg(open_model(_source_ifc(db, pid)), elevation, cut_height, title,
                            rooms=rooms, callouts=callouts, view_depth=view_depth,
                            by_discipline=by_discipline)
    return _svg(svg)


@router.get("/projects/{pid}/drawings/section.svg")
def section(pid: str, axis: str = "x", offset: float | None = None, title: str = "SECTION",
            db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Vertical section SVG. `offset` = world coordinate (m) of the cut on the axis perpendicular to
    `axis` (x|y); omit it to auto-centre the cut through the model."""
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    svg = drawings.section_svg(open_model(_source_ifc(db, pid)), axis, offset, title)
    return _svg(svg)


@router.get("/projects/{pid}/drawings/elevation.svg")
def elevation(pid: str, direction: str = "north", db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    svg = drawings.elevation(open_model(_source_ifc(db, pid)), direction,
                             f"{direction.upper()} ELEVATION")
    return _svg(svg)


@router.get("/projects/{pid}/drawings/plan.dxf")
def plan_dxf(pid: str, elevation: float = 0.0, cut_height: float = 1.2,
             db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Plan linework as a downloadable **DXF** (R12) for CAD interchange — any CAD tool opens it."""
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    return _dxf(drawings.plan_dxf(open_model(_source_ifc(db, pid)), elevation, cut_height), f"plan-{pid}")


@router.get("/projects/{pid}/drawings/section.dxf")
def section_dxf(pid: str, axis: str = "x", offset: float | None = None,
                db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Vertical section linework as a downloadable **DXF** (R12); omit `offset` to auto-centre the cut."""
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    return _dxf(drawings.section_dxf(open_model(_source_ifc(db, pid)), axis, offset), f"section-{axis}-{pid}")


@router.get("/projects/{pid}/drawings/elevation.dxf")
def elevation_dxf(pid: str, direction: str = "north",
                  db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Projected elevation outlines as a downloadable **DXF** (R12)."""
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    return _dxf(drawings.elevation_dxf(open_model(_source_ifc(db, pid)), direction), f"elevation-{direction}-{pid}")


@router.get("/projects/{pid}/model/export.gltf")
async def export_gltf(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer")),
                      __: None = Depends(_export_throttle)):
    """Export the model geometry as a self-contained glTF 2.0 file (interchange — Blender / Three.js /
    any DCC). Triangulated meshes merged per IFC class with per-class colours; Z-up→Y-up. The viewer
    itself streams Fragments — this is the portable geometry-out path. Geometry tessellation runs off
    the event loop."""
    from starlette.concurrency import run_in_threadpool

    from aec_data import gltf_export  # type: ignore
    path = _source_ifc(db, pid)
    p = db.get(Project, pid)
    data = await run_in_threadpool(gltf_export.export_gltf_bytes, path, (p.name if p else pid))
    return Response(data, media_type="model/gltf+json",
                    headers={"Content-Disposition": f'attachment; filename="model-{pid}.gltf"'})


@router.get("/projects/{pid}/model/export.glb")
async def export_glb(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer")),
                     __: None = Depends(_export_throttle)):
    """Export the model geometry as a binary **glTF (.glb)** — the compact single-file form Blender /
    three.js / game engines import directly (vs. the JSON `.gltf`). Same per-class meshes + colours;
    tessellation runs off the event loop."""
    from starlette.concurrency import run_in_threadpool

    from aec_data import gltf_export  # type: ignore
    path = _source_ifc(db, pid)
    p = db.get(Project, pid)
    data = await run_in_threadpool(gltf_export.export_glb_bytes, path, (p.name if p else pid))
    return Response(data, media_type="model/gltf-binary",
                    headers={"Content-Disposition": f'attachment; filename="model-{pid}.glb"'})


@router.get("/projects/{pid}/model/export.ifc")
def export_ifc(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """First-class **IFC re-export** — stream the project's current authored source IFC (edits republish
    it in place, so this is the live model), not only inside the closeout bundle zip. The GUID-stable
    source of truth a coordinator can round-trip through any openBIM tool."""
    from pathlib import Path as _P

    path = _source_ifc(db, pid)     # 409 if the project has no accessible source IFC
    data = _P(path).read_bytes()
    return Response(data, media_type="application/x-step",
                    headers={"Content-Disposition": f'attachment; filename="model-{pid}.ifc"'})


@router.get("/projects/{pid}/model/step-summary")
def model_step_summary(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Fast model summary — header + entity-type histogram from a streaming STEP scan, without a full
    ifcopenshell parse. Instant 'what's in this IFC' for large files."""
    from aec_data import step_scan  # type: ignore
    return step_scan.scan_file(_source_ifc(db, pid))


def _sheet_meta(db: Session, pid: str, sheet: str, purpose: str = "", rev: str = "") -> dict:
    from datetime import date

    p = db.get(Project, pid)
    return {"project": (p.name if p else "PROJECT").upper(), "sheet": sheet,
            "purpose": purpose, "revision": rev,
            "date": date.today().isoformat(), "drawn_by": "AEC Platform"}


@router.get("/projects/{pid}/drawings/sheet.svg")
def sheet_svg(pid: str, sheet: str = "A-101", page: str = "A3", purpose: str = "", rev: str = "",
              storey: str | None = None, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """A composed **key-plan sheet** (representative plans + section + elevation in a titleblock). `storey`
    renders one named level's sheet; omitted, it samples up to a few levels (a tall tower gets one sheet per
    level in the full set — cramming every plan on a page is neither fast nor legible)."""
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    svg = drawings.default_sheet(open_model(_source_ifc(db, pid)),
                                 _sheet_meta(db, pid, sheet, purpose, rev), page=page, fmt="svg", storey=storey)
    return _svg(svg)


@router.get("/projects/{pid}/drawings/sheet.pdf")
def sheet_pdf(pid: str, sheet: str = "A-101", page: str = "A3", purpose: str = "", rev: str = "",
              storey: str | None = None, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    pdf = drawings.default_sheet(open_model(_source_ifc(db, pid)),
                                 _sheet_meta(db, pid, sheet, purpose, rev), page=page, fmt="pdf", storey=storey)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{_safe_name(sheet)}.pdf"'})
