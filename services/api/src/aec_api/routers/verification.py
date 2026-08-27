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
    deviation count. `total` comes from the uploaded property index (0 if none yet).

    **Also reports EVIDENCE coverage, which is the half this endpoint was missing.** This module
    exists for the verified handover to operations, and its own docstring calls deviations
    "photo-anchored" — but until now `coverage` counted status flags only. "42 elements verified" with
    no idea how many carry a photo is a claim nobody downstream can audit, and the status flag is the
    cheapest thing in the system to set.

    `deviations_without_photo` is the number worth surfacing first: a deviation is an assertion that
    something does not match design, and one with no photo is that assertion with nothing behind it.
    That is what becomes contentious at handover, months later, when the person who logged it has
    left the project.

    Deliberately NOT reported: anything derived from what the photos *contain*. Object detection
    answers "what is in this frame", which is not the same question as "is this element documented",
    and mixing the two would put an inferred number where an auditable one belongs.
    """
    _ensure_loaded(pid)
    total = len(_INDEX.get(pid, {}))
    by_status = dict.fromkeys(STATUSES, 0)
    rows = list(db.execute(select(ElementVerification.status, ElementVerification.guid,
                                  ElementVerification.photo_key)
                           .where(ElementVerification.project_id == pid)).all())
    tracked_guids = set()
    photo_guids: set[str] = set()
    photo_by_status = dict.fromkeys(STATUSES, 0)
    for st, guid, photo_key in rows:
        by_status[st] = by_status.get(st, 0) + 1
        tracked_guids.add(guid)
        if photo_key:
            photo_guids.add(guid)
            photo_by_status[st] = photo_by_status.get(st, 0) + 1
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
        # --- evidence coverage -------------------------------------------------------------------
        # Percentages are against TRACKED elements, not the model total: an element nobody has looked
        # at yet is not missing evidence, it is simply not started. Dividing by `total` would blame
        # the field team for work that has not begun and make the number drift with model size.
        "with_photo": len(photo_guids),
        "photo_by_status": photo_by_status,
        "evidence_pct": round(100 * len(photo_guids) / tracked, 1) if tracked else 0.0,
        "verified_with_photo": photo_by_status.get("verified", 0),
        # The handover number. A deviation with no photo is an assertion with nothing behind it.
        "deviations_without_photo": by_status.get("deviation", 0) - photo_by_status.get("deviation", 0),
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
      * `duplicate` — **R37-TESTED-UNWIRED.** The same shot already filed against a DIFFERENT element
        in this project. `photo_cv.duplicate_of` was built and tested for exactly the abuse its
        docstring names — *one photo uploaded against thirty elements to clear a checklist* — and had
        no caller: this route ran `photo_quality` and `compare_photos` and never it. So the abuse was
        unguarded on the only path where it can happen.

    **The duplicate is reported, not refused, and that is the same judgement as `quality` above.**
    Two elements can legitimately share a frame — a wall and the conduit crossing it, an assembly
    photographed once. The system cannot tell that from checklist-clearing, and a person reviewing the
    verification set can. Refusing would also make the check adversarial: whoever wanted to defeat it
    would take one step to the left, and the record of what happened would be gone. Flagged, the shot
    is still on file and the pattern is visible across the set.

    **`duplicate.compared_against` rides with it, and is the load-bearing field.** The comparison can
    only see photos that were hashed, and nothing before v0.3.1115 was — the column is not backfilled.
    Without a count, "no duplicate" on a project with three hundred unhashed photos is indistinguishable
    from "checked all three hundred", and the second is the reading anybody makes. It is the same
    reasoning as `aec_jobs_stats_ok` in `metrics.render_queue`: the number that says whether the other
    number means anything.

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

    from .. import photo_cv, photo_detect
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

    # R37-TESTED-UNWIRED — the same shot already filed against a DIFFERENT element of this project.
    #
    # Keyed by GUID, never a row id: the identity that survives a re-conversion is the one a reviewer
    # will be handed. `v.guid` itself is excluded — re-photographing the SAME element is a retake, not
    # a duplicate, and flagging it would fire on the ordinary corrective path.
    #
    # Compared against the stored hashes, not the stored photos. Re-reading every verification photo
    # out of object storage per upload would be O(photos) network reads on a field device's request.
    #
    # **Two simultaneous uploads of the same shot can both miss it**, since each queries before either
    # commits. Detective, not preventive, and deliberately left so: a project-wide `pid_lock.mutating`
    # around every photo upload would serialise the whole field team to make an advisory flag exact.
    # The window is self-healing — whichever lands second is on file, so the next upload of that shot
    # flags it — and `compared_against` already says this answer is a floor, not a census.
    duplicate = None
    try:
        phash = photo_cv.perceptual_hash(data)
    except Exception:  # noqa: BLE001 — undecodable (HEIC) is already handled above; never fail here
        phash = None
    if phash is not None:
        known = {row_guid: int(h, 16) for row_guid, h in db.execute(
            select(ElementVerification.guid, ElementVerification.photo_phash).where(
                ElementVerification.project_id == pid,
                ElementVerification.guid != guid,
                ElementVerification.photo_phash.is_not(None))).all() if h}
        hit = photo_cv.duplicate_of(data, known)
        duplicate = {"guid": hit, "compared_against": len(known),
                     "note": (f"this photo is the same shot already filed against {hit}. Two elements "
                              "can legitimately share a frame; it is kept either way, and flagged so "
                              "a reviewer can tell that from a checklist cleared with one photo."
                              if hit else
                              "no element in this project has this shot on file. Only photos uploaded "
                              "since v0.3.1115 are fingerprinted, so this compares against "
                              f"{len(known)} of the project's photos, not all of them.")}

    # R22-PHOTO-CV Tier 2 — what is IN the frame: people, vehicles, plant. Returns a stated reason
    # instead of detections when no model is configured, which is the DEFAULT deployment: neither
    # onnxruntime nor the exported .onnx ships with the repo. Like the two analyses above, it can
    # never fail the upload — `photo_detect.detect` does not raise.
    detected = photo_detect.detect(data)

    storage.put(key, data)
    if v is None:
        v = ElementVerification(project_id=pid, guid=guid, status="installed", verified_by=user)
        db.add(v)
    v.photo_key = key
    # NULL when the bytes could not be decoded, so this row stays out of every future comparison
    # rather than joining it with a fingerprint of nothing.
    v.photo_phash = f"{phash:016x}" if phash is not None else None
    v.modified_at = _now()
    db.commit()
    return {"guid": guid, "has_photo": True, "quality": quality, "change": change,
            "duplicate": duplicate, "detected": detected}
