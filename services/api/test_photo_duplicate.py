"""R37-TESTED-UNWIRED — one photo filed against two elements is now caught on the upload path.

## What was wrong

`photo_cv.duplicate_of` names its own reason for existing: *"one photo uploaded against thirty
elements to clear a checklist. That is not a rare abuse, it is the path of least resistance for someone
under time pressure, and it silently destroys the evidence value of the whole verification set."* It
was built, unit-tested in `test_photo_cv.py`, and **called by nothing.**
`routers/verification.py::upload_photo` ran `photo_quality` and `compare_photos` and never this. The
upload is the only moment the abuse can be observed, so it was unguarded exactly where it happens.

`test_photo_cv.py` already proves the function works. This file exists for the other half — that a
request reaches it — which is the half `beside`, `read_p6xml_all` and now this one were all missing.

## Three things that would each make the wiring useless while looking correct

1. **Flagging a retake.** Re-photographing the SAME element is the ordinary corrective path, and a
   check that fired on it would be turned off within a day. The query excludes `v.guid`.
2. **A duplicate reported by REFUSING the upload.** Two elements can legitimately share a frame, and
   the person reviewing the set can tell that from checklist-clearing where the server cannot. Worse,
   a refusal teaches whoever wanted to defeat it to take one step left, and then there is no record at
   all. The photo is stored either way — asserted below, not argued.
3. **A clean result that means "nothing was compared".** Photos uploaded before v0.3.1115 have no
   fingerprint and the column is not backfilled, so `duplicate: {guid: null}` on a project of three
   hundred unhashed photos would read as "checked three hundred". `compared_against` is the count that
   makes the two distinguishable, and it is checked here against a project where it is deliberately 0.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_photo_duplicate.py
"""
from __future__ import annotations

import io
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_photo_duplicate.db"
os.environ["STORAGE_DIR"] = "./test_storage_photo_duplicate"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_photo_duplicate.db",):
    if os.path.exists(_f):
        os.remove(_f)

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402
from sqlalchemy import select  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import ElementVerification  # noqa: E402

HDR = {"X-User": "engineer"}
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


def enc(img: Image.Image, fmt: str = "PNG", **kw) -> bytes:
    b = io.BytesIO()
    img.save(b, fmt, **kw)
    return b.getvalue()


# Broadband noise, as in `test_photo_cv.py`: a flat or gradient fixture reads as blurred however sharp
# it is, which would make the quality half of the response pass for the wrong reason.
RNG = np.random.default_rng(20260827)
SCENE = Image.fromarray(RNG.integers(40, 200, (400, 400, 3)).astype("uint8"), "RGB")
OTHER = Image.fromarray(RNG.integers(0, 255, (400, 400, 3)).astype("uint8"), "RGB")

#: GUIDs are 22-char IFC GlobalIds in the wild; any stable string works here, and the point of using
#: them rather than row ids is the non-negotiable at the top of CLAUDE.md — the identity that survives
#: a re-conversion is the one a reviewer is handed.
A, B, C = "1Ab$cDeFgHiJkLmNoPqRsT", "2Bc$dEfGhIjKlMnOpQrStU", "3Cd$eFgHiJkLmNoPqRsTuV"


def post(c, pid: str, guid: str, data: bytes, name: str = "shot.png") -> dict:
    return c.post(f"/projects/{pid}/verification/{guid}/photo",
                  files={"file": (name, data, "image/png")}, headers=HDR).json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Photo dup"}, headers=HDR).json()["id"]

    # ---- 1. the FIRST photo on an empty project compares against nothing, and says so -------------
    first = post(c, pid, A, enc(SCENE))
    check("the first upload flags no duplicate", first["duplicate"]["guid"] is None,
          str(first["duplicate"]))
    check("...and reports that it compared against ZERO photos, not silence",
          first["duplicate"]["compared_against"] == 0, str(first["duplicate"]["compared_against"]))
    check("...with a note saying only post-v0.3.1115 photos are fingerprinted",
          "v0.3.1115" in first["duplicate"]["note"], first["duplicate"]["note"][:70])

    # ---- 2. THE CASE THE FUNCTION EXISTS FOR ------------------------------------------------------
    # Re-encoded as JPEG at quality 70, because a byte-identical re-post would be caught by any
    # checksum and is not what the abuse looks like: it is the same shot off the same phone, saved
    # again. A perceptual hash is the whole reason this is not a hash-equality check.
    dup = post(c, pid, B, enc(SCENE, "JPEG", quality=70), "shot.jpg")
    check("the same shot filed against a SECOND element is caught", dup["duplicate"]["guid"] == A,
          str(dup["duplicate"]))
    check("...and it compared against the one photo on file", dup["duplicate"]["compared_against"] == 1,
          str(dup["duplicate"]["compared_against"]))
    check("...the note names the element it duplicates, so the flag is actionable",
          A in dup["duplicate"]["note"], dup["duplicate"]["note"][:80])

    # THE UPLOAD IS NOT REFUSED. Two elements can legitimately share a frame, and a refusal would
    # destroy the record of the attempt along with the photo.
    check("...and the photo is STORED anyway — flagged, not refused", dup["has_photo"] is True)
    with SessionLocal() as db:
        row = db.execute(select(ElementVerification).where(
            ElementVerification.project_id == pid, ElementVerification.guid == B)).scalar_one()
        check("...with a photo_key on the row", bool(row.photo_key), str(row.photo_key))
        check("...and a fingerprint, so IT can be compared against next time",
              bool(row.photo_phash) and len(row.photo_phash) == 16, str(row.photo_phash))

    # ---- 3. the twins — a check that fires on everything is not a check ---------------------------
    new = post(c, pid, C, enc(OTHER))
    check("a genuinely different photo is NOT flagged", new["duplicate"]["guid"] is None,
          str(new["duplicate"]))
    check("...having actually compared against the two on file",
          new["duplicate"]["compared_against"] == 2, str(new["duplicate"]["compared_against"]))

    # A RETAKE of the same element must not fire. This is the ordinary corrective path — the engineer
    # was told the first shot was blurred and went back — and a check that flagged it would be off
    # within a day.
    #
    # **Retake C, not A, and the first draft of this file got that wrong.** Retaking A reported a
    # duplicate and the code was right to: B holds the same shot, because that is what case 2 just
    # filed. The self-exclusion worked perfectly and a legitimate cross-element match landed on top of
    # it. *An exclusion can only be tested on an element whose shot is unique in the project* —
    # otherwise the assertion is about the other match, and a broken exclusion would look identical.
    retake = post(c, pid, C, enc(OTHER, "JPEG", quality=60), "retake.jpg")
    check("RE-photographing the same element is a retake, not a duplicate",
          retake["duplicate"]["guid"] is None, str(retake["duplicate"]))
    check("...and the retake still compared against the OTHER elements, so it was not skipped",
          retake["duplicate"]["compared_against"] == 2,
          str(retake["duplicate"]["compared_against"]))

    # ---- 4. project isolation --------------------------------------------------------------------
    # The same shot in a different project is a different job's evidence. Nothing in the response
    # would look wrong if the query leaked across projects — it would just quietly accuse a stranger.
    other_pid = c.post("/projects", json={"name": "Other job"}, headers=HDR).json()["id"]
    cross = post(c, other_pid, A, enc(SCENE))
    check("the same shot in ANOTHER project is not flagged", cross["duplicate"]["guid"] is None,
          str(cross["duplicate"]))
    check("...because the comparison set is that project's own, which is empty",
          cross["duplicate"]["compared_against"] == 0, str(cross["duplicate"]["compared_against"]))

    # ---- 5. an undecodable upload still lands, and stays OUT of every future comparison -----------
    # iPhone HEIC on an unpatched Pillow. The route's standing rule is that analysis never fails the
    # upload; the fingerprint must be NULL rather than a hash of nothing, or every later upload would
    # be compared against garbage.
    junk = post(c, pid, "4De$fGhIjKlMnOpQrStUvW", b"not an image at all", "shot.heic")
    check("an undecodable photo is still stored", junk["has_photo"] is True, str(junk)[:80])
    check("...and reports no duplicate rather than crashing", junk["duplicate"] is None,
          str(junk["duplicate"]))
    with SessionLocal() as db:
        row = db.execute(select(ElementVerification).where(
            ElementVerification.project_id == pid,
            ElementVerification.guid == "4De$fGhIjKlMnOpQrStUvW")).scalar_one()
        check("...with a NULL fingerprint — 'not hashed', not 'hashed and unlike everything'",
              row.photo_phash is None, str(row.photo_phash))
    after = post(c, pid, "5Ef$gHiJkLmNoPqRsTuVwX", enc(OTHER, "JPEG", quality=80), "x.jpg")
    check("...so it never joins a later comparison set", after["duplicate"]["compared_against"] == 3,
          str(after["duplicate"]["compared_against"]))
    check("...and that later upload IS matched against the real one it duplicates",
          after["duplicate"]["guid"] == C, str(after["duplicate"]))

for _f in ("./test_photo_duplicate.db",):
    if os.path.exists(_f):
        os.remove(_f)

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("PHOTO DUPLICATE OK - `duplicate_of` has a caller on the one path where the abuse it names can "
      "happen. The same shot filed against a second element is flagged and STORED (two elements can "
      "share a frame; a refusal would destroy the record of the attempt), a retake of the same "
      "element is not flagged, another project's photos are not in the comparison set, and an "
      "undecodable upload stores a NULL fingerprint so it never joins one. `compared_against` ships "
      "with every answer, because photos predating the column are not backfilled and a clean result "
      "over nothing must not read as a clean result over everything.")
