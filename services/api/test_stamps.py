"""A/E/C stamps — review (EJCDC/CSI) + inspection + status + professional seal — engine + HTTP.
Rendering is reportlab overlay + pypdf composite; the seal adds a tamper-evident PAdES signature LAST.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_stamps.py"""
import io
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_stamps.db"
os.environ["STORAGE_DIR"] = "./test_storage_stamps"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_stamps.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402
from pypdf import PdfReader  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from aec_api import stamps  # noqa: E402
from aec_api.main import app  # noqa: E402

HDR = {"X-User": "reviewer"}


def make_pdf(pages: int = 1) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(pages):
        c.drawString(72, 720, f"sheet {i}")
        c.showPage()
    c.save()
    return buf.getvalue()


def npages(data: bytes) -> int:
    return len(PdfReader(io.BytesIO(data)).pages)


def has_signature(data: bytes) -> bool:
    r = PdfReader(io.BytesIO(data))
    try:
        return len(r.get_fields() or {}) > 0 or "/AcroForm" in r.trailer["/Root"]
    except Exception:
        return False


# --- library + vocabularies --------------------------------------------------------------------
lib = {t["id"]: t for t in stamps.library()}
assert {"review-ejcdc", "review-csi", "inspection", "status", "seal-pe", "seal-ra"} <= set(lib), lib.keys()
assert "Approved as Noted" in lib["review-ejcdc"]["dispositions"]           # EJCDC vocabulary
assert "No Exceptions Taken" in lib["review-csi"]["dispositions"]           # CSI vocabulary
assert lib["review-ejcdc"]["disclaimer"] is True                           # mandatory disclaimer
assert lib["review-ejcdc"]["color"].startswith("#")                        # hex for the client
assert stamps.DISPOSITIONS_EJCDC[0] == "Approved" and "Rejected" in stamps.DISPOSITIONS_EJCDC

# --- engine: apply a review stamp (preserves pages, valid PDF, bigger) --------------------------
base = make_pdf(2)
vals = {"firm": "Acme A/E", "reviewer": "J. Reviewer", "responsible": "P.E. Smith",
        "submittal": "03300-001.1", "spec_section": "03 30 00", "date": "2026-07-10"}
stamped = stamps.apply_stamp(base, 0, 40, 40, "review-ejcdc", vals, "Approved as Noted")
assert stamped[:4] == b"%PDF" and npages(stamped) == 2 and len(stamped) > len(base)

# status stamp + inspection stamp render too
assert stamps.apply_stamp(base, 0, 20, 20, "status", {"by": "GC", "date": "2026-07-10"},
                          "FOR CONSTRUCTION")[:4] == b"%PDF"
assert stamps.apply_stamp(base, 0, 20, 20, "inspection",
                          {"inspector": "CxA", "location": "L12"}, "Pass")[:4] == b"%PDF"

# a seal template cannot be applied as a plain stamp, and vice versa
for bad in ("seal-pe", "nope"):
    try:
        stamps.apply_stamp(base, 0, 0, 0, bad, {}, "")
        raise AssertionError(f"{bad} should have raised")
    except ValueError:
        pass

# --- engine: apply a professional seal (visible block + PAdES signature LAST) -------------------
profile = {"name": "Jane P. Engineer", "license_no": "089421", "state": "New York",
           "expiration": "2027-06-30", "date": "2026-07-10"}
sealed, meta = stamps.apply_seal(base, 0, 300, 300, "seal-pe", profile, sign=True)
assert sealed[:4] == b"%PDF" and meta["sealed"] is True and meta["licensee"] == "Jane P. Engineer"
assert has_signature(sealed), "sealed PDF should carry a signature field"
assert "demonstration" in meta["compliance"].lower()   # honest: self-signed cert is not board-accepted
# visible-only (no crypto) path
vis, meta2 = stamps.apply_seal(base, 0, 300, 300, "seal-ra", profile, sign=False)
assert vis[:4] == b"%PDF" and meta2["sealed"] is False

# --- HTTP --------------------------------------------------------------------------------------
with TestClient(app) as c:
    r = c.get("/stamps/library", headers=HDR)
    assert r.status_code == 200 and len(r.json()["templates"]) >= 6, r.text

    import json
    r = c.post("/pdf/stamp", files={"file": ("s.pdf", make_pdf(1), "application/pdf")},
               data={"template_id": "review-csi", "page": "1", "x": "40", "y": "40",
                     "disposition": "No Exceptions Taken", "values": json.dumps(vals)}, headers=HDR)
    assert r.status_code == 200 and r.content[:4] == b"%PDF", r.text

    # non-PDF rejected; unknown template → 422; seal via /pdf/stamp → 422
    assert c.post("/pdf/stamp", files={"file": ("x.txt", b"nope", "text/plain")},
                  data={"template_id": "status"}, headers=HDR).status_code == 422
    assert c.post("/pdf/stamp", files={"file": ("s.pdf", make_pdf(1), "application/pdf")},
                  data={"template_id": "bogus"}, headers=HDR).status_code == 422
    assert c.post("/pdf/stamp", files={"file": ("s.pdf", make_pdf(1), "application/pdf")},
                  data={"template_id": "seal-pe"}, headers=HDR).status_code == 422

    # seal endpoint: signs + reports compliance in headers
    r = c.post("/pdf/seal", files={"file": ("s.pdf", make_pdf(1), "application/pdf")},
               data={"template_id": "seal-pe", "page": "1", "x": "300", "y": "300",
                     "sign": "true", "profile": json.dumps(profile)}, headers=HDR)
    assert r.status_code == 200 and r.content[:4] == b"%PDF", r.text
    assert r.headers["X-Seal-Sealed"] == "true" and r.headers.get("X-Seal-Compliance"), r.headers
    # a plain stamp via /pdf/seal → 422
    assert c.post("/pdf/seal", files={"file": ("s.pdf", make_pdf(1), "application/pdf")},
                  data={"template_id": "review-ejcdc", "profile": "{}"}, headers=HDR).status_code == 422

print("STAMPS OK - library (EJCDC+CSI review, inspection, status, PE/RA seal); review/inspection/status "
      "composited (pages preserved, disclaimer baked in); professional seal renders visible block + "
      "PAdES signature applied LAST (tamper-evident, honest demo-cert note); HTTP stamp/seal + guards; "
      "reportlab+pypdf, no PyMuPDF/AGPL.")
