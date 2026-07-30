"""2D documentation endpoints (Revit-style plans/sections, openBIM). Returns SVG generated
from the project source IFC by the data service."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from .. import audit, drawingset, issuance, pdfops, sheetgen
from ..db import get_db
from ..deps import source_ifc_path as _source_ifc
from ..models import Project
from ..rbac import require_identified, require_role
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


@router.get("/projects/{pid}/drawing-set/references")
def get_detail_references(pid: str, db: Session = Depends(get_db),
                          _: str = Depends(require_role("viewer"))):
    """The section↔detail cross-reference graph, with its two defects reported separately.

    `dangling` = a callout points at a detail that does not exist (the reader follows it and finds
    nothing); `orphans` = a detail nothing points at. They are split further by reason because the fix
    differs — an unknown sheet is a typo or an unissued sheet, while a known sheet missing the detail
    number is almost always a renumber that was not propagated.
    """
    from .. import detail_refs
    return detail_refs.graph(db, pid)


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


# PERF-1: pypdf work runs off the event loop (a 200-page set would otherwise block every request in
# the process). Mirrors pdf_stamp/pdf_seal below, which already thread-pool.
@router.post("/pdf/info")
async def pdf_info(file: UploadFile = File(...), _: str = Depends(require_identified)):
    """Page count + flags for an uploaded PDF."""
    from starlette.concurrency import run_in_threadpool
    data = await _read_pdf(file)
    return await run_in_threadpool(pdfops.info, data)


@router.post("/pdf/merge")
async def pdf_merge(files: list[UploadFile] = File(...), _: str = Depends(require_identified)):
    """Concatenate several uploaded PDFs into one (order = upload order)."""
    from starlette.concurrency import run_in_threadpool
    if len(files) < 2:
        raise HTTPException(422, "merge needs at least 2 PDFs")
    datas = [await _read_pdf(f) for f in files]
    out = await run_in_threadpool(pdfops.merge, datas)
    return Response(out, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="merged.pdf"'})


@router.post("/pdf/split")
async def pdf_split(file: UploadFile = File(...), _: str = Depends(require_identified)):
    """Split an uploaded PDF into one PDF per page, returned as a .zip."""
    from starlette.concurrency import run_in_threadpool
    data = await _read_pdf(file)
    stem = (file.filename or "doc").rsplit(".", 1)[0]
    zipped = await run_in_threadpool(lambda: pdfops.zip_bytes(pdfops.split(data), stem=stem))
    return Response(zipped, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="pages.zip"'})


@router.post("/pdf/extract")
async def pdf_extract(file: UploadFile = File(...), pages: str = Form(...),
                      _: str = Depends(require_identified)):
    """A new PDF of just the given pages (`pages` = '1,3,5-7', 1-based)."""
    from starlette.concurrency import run_in_threadpool
    sel = pdfops.parse_pages(pages)
    if not sel:
        raise HTTPException(422, "no valid page numbers (e.g. '1,3,5-7')")
    data = await _read_pdf(file)
    out = await run_in_threadpool(pdfops.extract, data, sel)
    return Response(out, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="extract.pdf"'})


@router.post("/pdf/rotate")
async def pdf_rotate(file: UploadFile = File(...), angle: int = Form(90), pages: str = Form(""),
                     _: str = Depends(require_identified)):
    """Rotate pages by `angle` (multiple of 90). `pages` (1-based, '1,3-5') limits it; blank = all."""
    from starlette.concurrency import run_in_threadpool
    sel = pdfops.parse_pages(pages) or None
    data = await _read_pdf(file)
    out = await run_in_threadpool(pdfops.rotate, data, angle, sel)
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


# Gated alongside the /pdf ops rather than left on `current_user`: both callers are already
# authenticated flows (PDF markup, Report Center's stamp tool), and if you cannot stamp there is
# no reason to enumerate the stamp catalogue. Deliberate, not incidental to the /pdf change.
@router.get("/stamps/library")
def stamps_library(_: str = Depends(require_identified)):
    """The A/E/C stamp template library — review (EJCDC + CSI), inspection, status, and seal templates.
    The client renders the picker and preview from this; the server is the source of truth."""
    from .. import stamps
    return {"templates": stamps.library()}


@router.post("/pdf/stamp")
async def pdf_stamp(file: UploadFile = File(...), template_id: str = Form(...),
                    page: int = Form(1), x: float = Form(36), y: float = Form(36),
                    disposition: str = Form(""), values: str = Form(""),
                    _: str = Depends(require_identified)):
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


# Escape hatch for an operator who still drives sealing with a caller-supplied identity. OFF by
# default, so the safe behaviour is the one you get by doing nothing — the whole defect class here was
# a plausible default. Turning it on re-opens seal-in-someone-else's-name and is audited as such.
_SEAL_ALLOW_PROFILE = os.environ.get("AEC_SEAL_ALLOW_PROFILE") == "1"


@router.post("/pdf/seal")
async def pdf_seal(file: UploadFile = File(...), template_id: str = Form(...),
                   step_up: str = Form(""),
                   page: int = Form(1), x: float = Form(36), y: float = Form(36),
                   sign: bool = Form(True),
                   license_id: str | None = Form(None), profile: str | None = Form(None),
                   db: Session = Depends(get_db),
                   actor: str = Depends(require_identified)):
    """Render a *visible* professional seal + signature block, then apply a tamper-evident PAdES
    signature LAST (unless `sign=false`). The self-signed platform cert is demonstration /
    tamper-evidence, not board-accepted sealing.

    **A seal is not an authorisation, it is a personal legal attestation** that a named licensed human
    was in responsible charge of the work. Responsible charge cannot be delegated to software, and a
    licensee whose seal is applied to work they did not supervise is the specific thing state boards
    discipline. So this route deliberately asks more than "is this request authenticated?":

    1. `step_up` — a fresh, single-action assertion from `POST /auth/step-up` that the account
       password was just re-proved. A bearer token cannot answer this: any process holding one can
       replay it, so an automation driving this API with a user's token would emit documents under
       that user's seal and the audit row would faithfully record a human act that never happened.
    2. The `api-key` identity is refused outright — a machine credential has no person behind it.
    3. `license_id` selects one of the CALLER'S OWN verified licences (`GET /licenses/mine`) and the
       seal text is built server-side from that row. An expired licence refuses with 409.

    History, because the shape recurs: this route originally guarded with `Depends(current_user)`,
    which identifies without authorising — an anonymous caller could upload any PDF and receive it
    bearing a rendered PE or RA seal with a name and licence number of their choosing, verified end to
    end. Gating it fixed anonymity but not impersonation, because `profile` was still free text; and
    binding to the account would still not have fixed automation, because a token is not a person.
    Each fix looked complete and left the next layer open.
    """
    from datetime import date

    from starlette.concurrency import run_in_threadpool

    from .. import auth as _auth
    from .. import rbac as _rbac
    from .. import stamps
    from ..models import ProfessionalLicense, User

    # Single-operator mode (RBAC off / LOCAL_MODE desktop) has no accounts, no passwords and no login
    # at all — so there is nothing for a step-up to re-prove and no account for a licence to hang on.
    # Demanding either there would be theatre in front of an app that is unauthenticated by design,
    # and it would break the desktop build outright. The control applies where identities exist; this
    # mirrors how require_platform_admin and require_admin_user already treat LOCAL_MODE.
    multi_user = _rbac.RBAC_ON and not _rbac.LOCAL_MODE

    if multi_user:
        if actor == "api-key":
            raise HTTPException(403, "sealing requires a personal account with a step-up; the API key "
                                     "has no person behind it and cannot hold responsible charge")
        u = db.get(User, actor)
        if not u or not u.password_hash:
            raise HTTPException(403, "sealing requires an account with a local password")
        if _auth.verify_stepup_token(step_up, "pdf.seal", u.password_hash) != actor:
            # One status for every failure mode (absent / wrong act / expired / another user's / stale
            # after a password change) so the response cannot be used to probe which one it was.
            raise HTTPException(403, "a fresh step-up assertion for 'pdf.seal' is required — "
                                     "POST /auth/step-up")

    if license_id:
        lic = db.get(ProfessionalLicense, license_id)
        # Checked as "belongs to the caller" rather than "exists": otherwise any licence id in the
        # system would seal, which is the impersonation hole wearing a different hat.
        if not lic or lic.user != actor:
            raise HTTPException(403, "that licence is not on record for this account")
        if lic.expiration:
            try:
                lapsed = date.fromisoformat(lic.expiration) < date.today()
            except ValueError:
                lapsed = False          # unparseable stored date: don't refuse on a data defect
            if lapsed:
                raise HTTPException(409, f"licence {lic.license_no} ({lic.state}) expired "
                                         f"{lic.expiration}")
        prof = {"name": lic.name_on_seal, "license_no": lic.license_no, "state": lic.state,
                "expiration": lic.expiration or "", "date": date.today().isoformat()}
        via, lic_ref = "license", lic.id
    elif profile and (not multi_user or _SEAL_ALLOW_PROFILE):
        # Single-operator: the one person at the machine IS the licensee, and there is no account for
        # a licence row to belong to, so the free-text profile stays the only workable path there.
        prof = _json_form(profile)
        via, lic_ref = ("profile:local" if not multi_user else "profile:legacy"), None
    elif profile:
        raise HTTPException(403, "caller-supplied seal identities are disabled: pass `license_id` "
                                 "naming one of your own verified licences (GET /licenses/mine). "
                                 "Set AEC_SEAL_ALLOW_PROFILE=1 to re-enable the legacy field.")
    else:
        raise HTTPException(422, "license_id is required (GET /licenses/mine)")

    data = await _read_pdf(file)
    try:
        # pyHanko signing calls asyncio.run internally — run off the event loop.
        out, meta = await run_in_threadpool(stamps.apply_seal, data, page - 1, x, y, template_id,
                                            prof, sign)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    # Recorded AFTER the seal succeeds: a row for an attempt that raised would claim a document was
    # sealed when none was. `via` is what makes the trail readable later — a row sealed from a verified
    # licence and one sealed from the legacy free-text field are different kinds of evidence, and
    # without this field they are indistinguishable.
    audit.record(db, action="pdf.seal", actor=actor, method="POST", path="/pdf/seal",
                 detail={"template_id": template_id, "signed": bool(meta.get("sealed")),
                         "via": via, "license_id": lic_ref, "step_up": True,
                         "seal_name": str(prof.get("name") or "")[:120],
                         "license_no": str(prof.get("license_no") or "")[:60],
                         "state": str(prof.get("state") or "")[:16]})
    db.commit()
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
         by_discipline: bool = False, pins: bool = False,
         db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Schematic plan (SVG) cut at `elevation + cut_height`. VIEW-RANGE: pass `view_depth` (metres below
    the cut) to also draw the footprint of anything under the cut but within that depth — foundations/
    footings show as dashed hidden lines, the Revit Top/Cut/Bottom/View-Depth model rather than one cut_z.
    DISC-poché: `by_discipline=true` strokes each element's linework with its discipline color + legend."""
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    _m = open_model(_source_ifc(db, pid))
    svg = drawings.plan_svg(_m, elevation, cut_height, title,
                            rooms=rooms, callouts=callouts, view_depth=view_depth,
                            by_discipline=by_discipline,
                            pins=_plan_pins(db, pid, elevation, cut_height, _m) if pins else None)
    return _svg(svg)


#: How far above/below the cut a pin can sit and still belong to this plan. A storey's worth either
#: way — an issue tagged at ceiling height is still an issue on that floor's sheet.
_PIN_BAND_M = 2.0


def _plan_pins(db: Session, pid: str, elevation: float, cut_height: float, model=None) -> list[dict]:
    """Pins for this plan, as plain dicts for the drawing engine.

    The engine never learns what a Topic or a record is — `aec_data` may not import `aec_api`, and a
    drawing module has no business knowing about the issue tracker. It receives positions and labels.

    Resolution is shared with the viewer (`aec_api.pins`), so one issue means the same thing on the
    sheet and in 3D. Pins are filtered to the storey by Z against the cut, so a tall building does not
    print every issue in the project onto the ground floor. A pin with no Z is **kept**: it is
    genuinely located in plan and we do not know its level, and showing it on the sheet asked for
    beats hiding it on every sheet. A pin with no position at all is kept too, unplaced — the engine
    counts it in a note rather than letting the sheet under-report.
    """
    from .. import pins as pin_engine
    rows = pin_engine.resolve_pins(db, pid, model=model)
    lo, hi = elevation - _PIN_BAND_M, elevation + cut_height + _PIN_BAND_M
    out: list[dict] = []
    for p in rows:
        z = p.get("z")
        if z is not None and not (lo <= float(z) <= hi):
            continue
        out.append({"x": p.get("x"), "y": p.get("y"), "kind": p.get("kind"),
                    "label": p.get("label") or "", "guid": p.get("guid")})
    return out


@router.get("/projects/{pid}/drawings/section.svg")
def section(pid: str, axis: str = "x", offset: float | None = None, title: str = "SECTION",
            lod: str = "coarse", annotate: bool = True, hatch: bool = True,
            keynotes: bool = True,
            db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Vertical section SVG. `offset` = world coordinate (m) of the cut on the axis perpendicular to
    `axis` (x|y); omit it to auto-centre the cut through the model.

    Annotated by default — material hatch on cut material, level datums, grid bubbles and a
    floor-to-floor dimension chain. `lod` (coarse|fine|line) sets how much tone survives when an
    element is too thin to hatch; `hatch=false` falls back to flat poché tones; `annotate=false`
    returns bare linework for CAD hand-off.

    `keynotes` (default on) adds the assembly-annotation column: one leader per DISTINCT assembly,
    not per cut polygon, so a wall repeated at every storey is named once.
    """
    from fastapi import HTTPException

    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore
    if lod not in drawings.SECTION_LODS:
        raise HTTPException(400, f"lod must be one of {sorted(drawings.SECTION_LODS)}")
    svg = drawings.section_svg(open_model(_source_ifc(db, pid)), axis, offset, title,
                               lod=lod, annotate=annotate, hatch=hatch, keynotes=keynotes)
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

    from .. import licensing
    licensing.require_export("gltf", "glTF")   # Home+ when enforcement is on; no-op in open mode
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

    from .. import licensing
    licensing.require_export("glb", "GLB")   # Home+ when enforcement is on; no-op in open mode
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

    from .. import licensing
    licensing.require_export("ifc", "IFC")   # gate this side-door too (parity with /source.ifc)
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


@router.get("/projects/{pid}/drawings/sheet.dxf")
def sheet_dxf(pid: str, sheet: str = "A-101", page: str = "A3", purpose: str = "", rev: str = "",
              storey: str | None = None, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """DXF-EXPORT — the composed sheet (viewports + annotations + titleblock) as editable R12 CAD
    linework, not just paper. Same composition as sheet.svg/pdf; layers BORDER/VIEW-n/ANNO/TITLEBLOCK."""
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    text = drawings.default_sheet(open_model(_source_ifc(db, pid)),
                                  _sheet_meta(db, pid, sheet, purpose, rev), page=page, fmt="dxf", storey=storey)
    return _dxf(text, f"{sheet}")


@router.get("/projects/{pid}/drawings/sheet.pdf")
def sheet_pdf(pid: str, sheet: str = "A-101", page: str = "A3", purpose: str = "", rev: str = "",
              storey: str | None = None, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    pdf = drawings.default_sheet(open_model(_source_ifc(db, pid)),
                                 _sheet_meta(db, pid, sheet, purpose, rev), page=page, fmt="pdf", storey=storey)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{_safe_name(sheet)}.pdf"'})
