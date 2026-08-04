"""Field verification & install-coverage — mark model elements installed/verified against design,
log deviations (photo-anchored), and report % coverage for the verified-handover to operations
(Argyle-style spatial QA, without AR hardware). Keyed by IFC GlobalId so it survives re-conversion."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import storage
from ..db import get_db
from ..models import ElementVerification
from ..rbac import require_role
from .properties import _INDEX, _ensure_loaded

router = APIRouter()

STATUSES = ("pending", "installed", "verified", "deviation")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public(v: ElementVerification) -> dict:
    return {"guid": v.guid, "ifc_class": v.ifc_class, "storey": v.storey, "status": v.status,
            "note": v.note, "has_photo": bool(v.photo_key), "verified_by": v.verified_by,
            "modified_at": v.modified_at.isoformat() if v.modified_at else None}


@router.get("/projects/{pid}/verification")
def list_verifications(pid: str, status: str | None = None, db: Session = Depends(get_db),
                       _: str = Depends(require_role("viewer"))):
    stmt = select(ElementVerification).where(ElementVerification.project_id == pid)
    if status:
        stmt = stmt.where(ElementVerification.status == status)
    return [_public(v) for v in db.execute(stmt).scalars()]


@router.get("/projects/{pid}/verification/coverage")
def coverage(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Install-coverage summary: of the model's elements, how many are installed/verified, plus the
    deviation count. `total` comes from the uploaded property index (0 if none yet)."""
    _ensure_loaded(pid)
    total = len(_INDEX.get(pid, {}))
    by_status = dict.fromkeys(STATUSES, 0)
    rows = list(db.execute(select(ElementVerification.status, ElementVerification.guid)
                           .where(ElementVerification.project_id == pid)).all())
    tracked_guids = set()
    for st, guid in rows:
        by_status[st] = by_status.get(st, 0) + 1
        tracked_guids.add(guid)
    # untracked elements count as pending against the model total
    tracked = len(tracked_guids)
    by_status["pending"] = max(by_status.get("pending", 0), (total - tracked) if total else by_status.get("pending", 0))
    verified = by_status.get("verified", 0)
    installed = verified + by_status.get("installed", 0)
    denom = total or tracked or 1
    return {
        "total_elements": total,
        "tracked": tracked,
        "by_status": by_status,
        "verified": verified,
        "installed": installed,
        "deviations": by_status.get("deviation", 0),
        "verified_pct": round(100 * verified / denom, 1),
        "installed_pct": round(100 * installed / denom, 1),
    }


@router.get("/projects/{pid}/verification/deviations")
def deviations(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The deviation log — elements flagged as not matching design (for the punch / ops handover)."""
    stmt = (select(ElementVerification)
            .where(ElementVerification.project_id == pid, ElementVerification.status == "deviation")
            .order_by(ElementVerification.modified_at.desc()))
    return [_public(v) for v in db.execute(stmt).scalars()]


@router.put("/projects/{pid}/verification/{guid}")
def set_status(pid: str, guid: str, body: dict = Body(...), db: Session = Depends(get_db),
               user: str = Depends(require_role("editor"))):
    """Set an element's field-verification status (installed / verified / deviation / pending).
    Upserts by (project, guid); stamps ifc_class/storey from the property index when available."""
    status = (body.get("status") or "").strip()
    if status not in STATUSES:
        raise HTTPException(422, f"status must be one of {', '.join(STATUSES)}")
    _ensure_loaded(pid)
    el = _INDEX.get(pid, {}).get(guid) or {}
    v = db.execute(select(ElementVerification).where(
        ElementVerification.project_id == pid, ElementVerification.guid == guid)).scalar_one_or_none()
    if v is None:
        v = ElementVerification(project_id=pid, guid=guid)
        db.add(v)
    v.status = status
    if "note" in body:
        v.note = body.get("note")
    v.ifc_class = el.get("ifc_class") or v.ifc_class
    v.storey = el.get("storey") or v.storey
    v.verified_by = user
    v.modified_at = _now()
    db.commit()
    return _public(v)


@router.post("/projects/{pid}/verification/{guid}/photo")
async def upload_photo(pid: str, guid: str, file: UploadFile = File(...), db: Session = Depends(get_db),
                       user: str = Depends(require_role("editor"))):
    """Attach a field photo to an element's verification (deviation evidence / install proof).

    R22-PHOTO-CV: the upload is also the only moment both photos exist, so it is where the analysis
    has to happen. `photo_key` is a single column — one photo per element — so replacing it is
    destructive, and comparing the incoming shot against the stored one *before* the overwrite is the
    only progress signal available without a schema change and a migration.

    Two results ride back on the response:

      * `quality` — a blurred or blown-out photo is stored anyway but reported as unusable. Refusing
        it outright would be wrong: a field engineer in a dark riser may have no better shot, and
        losing the evidence is worse than keeping a poor frame. Flagging it lets the app offer a
        retake while the person is still standing there, which is the only time a retake is cheap.
      * `change` — present only when this element already had a photo. Read `change.confidence`
        before believing `change_score`; see `photo_cv.compare_photos`.

    **Analysis never fails the upload — including when the bytes cannot be decoded at all.** The
    first version refused an undecodable file with a 400, on the reasoning that a non-image under a
    verification record destroys the record's evidence value. That was wrong twice over.

    It contradicted the paragraph above it: if a blurred frame is worth keeping because the engineer
    may have no better shot, an unparseable one is worth keeping for exactly the same reason. And it
    would have rejected the most likely real field photo on the platform — **iPhones shoot HEIC by
    default, and Pillow cannot decode HEIC without `pillow-heif`**, which is not a dependency here.
    A gate meant to protect evidence would have thrown away the evidence.

    So an undecodable upload is stored with `quality.analysed = False` and the decoder's complaint.
    The API cannot tell "corrupt" from "a format we lack a codec for", and between silently
    discarding a real photo and keeping one it could not read, keeping is the recoverable error.
    """
    import os
    import re

    from .. import photo_cv
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(file.filename or "photo")).lstrip(".") or "photo"
    key = f"verification/{pid}/{guid}/{safe}"
    data = await file.read()

    try:
        quality = photo_cv.photo_quality(data)
        quality["analysed"] = True
    except photo_cv.PhotoError as exc:
        # Store it regardless — see the docstring. HEIC lands here on an unpatched Pillow.
        #
        # The decoder's own text is deliberately NOT returned. It carries interpreter detail (Pillow
        # reports "cannot identify image file <_io.BytesIO object at 0x7f...>"), which CodeQL flags as
        # py/stack-trace-exposure — correctly, and it was flagged on this exact line. The address is
        # of no use to the person holding the phone either. A fixed sentence naming the likeliest
        # real cause is both safe and more actionable than the exception ever was.
        logging.getLogger("aec.verification").info(
            "photo for %s/%s could not be decoded: %s", pid, guid, exc)
        quality = {"analysed": False, "usable": None,
                   "reasons": ["could not be decoded — the format may not be supported "
                               "(iPhone HEIC cannot be read server-side); the photo was kept"]}

    v = db.execute(select(ElementVerification).where(
        ElementVerification.project_id == pid, ElementVerification.guid == guid)).scalar_one_or_none()

    # Compare against the outgoing photo while it is still the stored one.
    change = None
    if v is not None and v.photo_key:
        try:
            change = photo_cv.compare_photos(storage.get(v.photo_key), data)
        except Exception:  # noqa: BLE001 — a missing or unreadable prior photo must not block the upload
            change = None

    storage.put(key, data)
    if v is None:
        v = ElementVerification(project_id=pid, guid=guid, status="installed", verified_by=user)
        db.add(v)
    v.photo_key = key
    v.modified_at = _now()
    db.commit()
    return {"guid": guid, "has_photo": True, "quality": quality, "change": change}
