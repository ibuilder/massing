"""Field verification & install coverage: set per-element status, report % coverage vs the model
total, and list deviations. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_verification.py"""
import json
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_verification.db"
os.environ["STORAGE_DIR"] = "./test_storage_verification"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_verification.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

PROPS = {"project": {"name": "Plant"}, "elements": [
    {"guid": "g1", "ifc_class": "IfcDuctSegment", "storey": "L1"},
    {"guid": "g2", "ifc_class": "IfcDuctSegment", "storey": "L1"},
    {"guid": "g3", "ifc_class": "IfcPipeSegment", "storey": "L2"},
    {"guid": "g4", "ifc_class": "IfcPipeSegment", "storey": "L2"},
]}

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Plant"}).json()["id"]
    c.post(f"/projects/{pid}/properties/index",
           files={"file": ("props.json", json.dumps(PROPS).encode(), "application/json")})

    # invalid status rejected
    assert c.put(f"/projects/{pid}/verification/g1", json={"status": "bogus"}).status_code == 422

    # mark statuses: g1 verified, g2 installed, g3 deviation, g4 untouched (pending)
    v1 = c.put(f"/projects/{pid}/verification/g1", json={"status": "verified"})
    assert v1.status_code == 200 and v1.json()["status"] == "verified", v1.text[:160]
    assert v1.json()["ifc_class"] == "IfcDuctSegment"            # stamped from the index
    c.put(f"/projects/{pid}/verification/g2", json={"status": "installed"})
    c.put(f"/projects/{pid}/verification/g3", json={"status": "deviation", "note": "elbow clashes joist"})

    cov = c.get(f"/projects/{pid}/verification/coverage").json()
    assert cov["total_elements"] == 4, cov
    assert cov["verified"] == 1 and cov["installed"] == 2, cov      # installed = verified + installed
    assert cov["deviations"] == 1, cov
    assert cov["verified_pct"] == 25.0 and cov["installed_pct"] == 50.0, cov
    assert cov["by_status"]["pending"] == 1, cov                    # g4 untracked → pending

    # deviation log
    dev = c.get(f"/projects/{pid}/verification/deviations").json()
    assert len(dev) == 1 and dev[0]["guid"] == "g3" and dev[0]["note"], dev

    # filtered list
    only_verified = c.get(f"/projects/{pid}/verification?status=verified").json()
    assert [v["guid"] for v in only_verified] == ["g1"], only_verified

    # re-verify g1 (upsert, not duplicate) then photo attach
    c.put(f"/projects/{pid}/verification/g1", json={"status": "installed"})
    again = c.get(f"/projects/{pid}/verification?status=verified").json()
    assert again == [], again                                       # status changed, no dup row
    # These bytes carry a JPEG magic number and are NOT a decodable JPEG. That is deliberate and it
    # is the regression guard for R22-PHOTO-CV: the photo-quality gate added at this route first
    # refused an undecodable upload with a 400, which turned this line red. Refusing was the wrong
    # call — an iPhone shoots HEIC, Pillow cannot decode HEIC without `pillow-heif`, and the gate
    # would have discarded the most likely genuine field photo on the platform. Evidence is kept and
    # flagged, never dropped.
    ph = c.post(f"/projects/{pid}/verification/g3/photo",
                files={"file": ("field.jpg", b"\xff\xd8\xff jpeg", "image/jpeg")})
    assert ph.status_code == 200 and ph.json()["has_photo"], ph.text[:160]
    q = ph.json()["quality"]
    assert q["analysed"] is False, q          # it admits it could not read the file...
    assert q["reasons"], q                    # ...and says why, rather than reporting a fake verdict
    # ...but says why in ITS OWN words. Returning the decoder's message leaked interpreter detail
    # ("cannot identify image file <_io.BytesIO object at 0x7f...>") and CodeQL flagged this exact
    # response line as py/stack-trace-exposure. The detail goes to the log; the caller gets a fixed
    # sentence. Asserted here because the natural way to write this handler is the leaky way.
    _blob = " ".join(q["reasons"])
    for _leak in ("0x", "BytesIO", "Traceback", "PIL.", "object at"):
        assert _leak not in _blob, f"decoder internals leaked to the client: {_blob!r}"

    # The twin: a photo it CAN read must actually be analysed, or the assertion above passes on a
    # gate that has quietly stopped analysing anything at all.
    import io as _io

    from PIL import Image as _Image
    _buf = _io.BytesIO()
    _Image.new("RGB", (64, 64), (120, 90, 60)).save(_buf, "PNG")
    ok = c.post(f"/projects/{pid}/verification/g3/photo",
                files={"file": ("real.png", _buf.getvalue(), "image/png")})
    assert ok.status_code == 200, ok.text[:160]
    oq = ok.json()["quality"]
    assert oq["analysed"] is True and "sharpness" in oq, oq

    # R22-PHOTO-CV Tier 2 must RIDE ALONG on this response, and must degrade rather than fail when
    # no model is configured — which is the default here and in CI, since neither onnxruntime nor
    # the exported .onnx ships with the repo. Asserted because a detector wired in and then quietly
    # dropped from the payload is indistinguishable from one that was never wired at all.
    det = ok.json()["detected"]
    assert det["available"] is False, det          # no model in CI...
    assert det["reasons"], det                     # ...and it says so
    assert det["detections"] == [], det            # never a missing key
    assert det["summary"]["people"] == 0, det      # a well-formed summary regardless
    # No change report here, and that is correct rather than a gap: the photo being REPLACED is the
    # undecodable one above, so there is nothing to compare against. Asserted explicitly because the
    # first version of this test expected a report and was wrong — a comparison needs two readable
    # frames, not merely two uploads.
    assert ok.json()["change"] is None, ok.json()

    # NOW the real twin: replace a readable photo with another readable one. Only this path exercises
    # compare_photos, and without it the change half of the feature is never executed by any test.
    _buf2 = _io.BytesIO()
    _Image.new("RGB", (64, 64), (10, 200, 30)).save(_buf2, "PNG")
    ok2 = c.post(f"/projects/{pid}/verification/g3/photo",
                 files={"file": ("real2.png", _buf2.getvalue(), "image/png")})
    ch = ok2.json()["change"]
    assert ch is not None, ok2.json()
    assert 0.0 <= ch["change_score"] <= 1.0, ch
    # A brown frame replaced by a green one is not the same shot, and the module must not claim it is.
    assert ch["near_identical"] is False, ch
    # Every result states which direction it can be trusted in — see photo_cv.compare_photos.
    assert ch["confidence"], ch

print("VERIFICATION OK - per-element status upserts (stamped from index); coverage 25% verified / 50% "
      "installed of 4; 1 deviation logged with note + photo; status filter + pending rollup correct")
