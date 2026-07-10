"""PDF manipulation via pypdf (merge/split/rotate/extract) — engine + HTTP endpoints. No PyMuPDF.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_pdfops.py"""
import io
import os
import zipfile

os.environ["DATABASE_URL"] = "sqlite:///./test_pdfops.db"
os.environ["STORAGE_DIR"] = "./test_storage_pdfops"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_pdfops.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient        # noqa: E402
from pypdf import PdfReader                       # noqa: E402
from reportlab.pdfgen import canvas               # noqa: E402

from aec_api import pdfops                         # noqa: E402
from aec_api.main import app                       # noqa: E402

HDR = {"X-User": "drafter"}


def make_pdf(pages: int, text: str = "p") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(pages):
        c.drawString(72, 720, f"{text}{i}")
        c.showPage()
    c.save()
    return buf.getvalue()


def npages(data: bytes) -> int:
    return len(PdfReader(io.BytesIO(data)).pages)


# --- engine ------------------------------------------------------------------------------------
assert pdfops.info(make_pdf(3))["pages"] == 3
assert npages(pdfops.merge([make_pdf(2), make_pdf(1)])) == 3
parts = pdfops.split(make_pdf(3))
assert len(parts) == 3 and all(npages(p) == 1 for p in parts)
assert npages(pdfops.extract(make_pdf(5), [1, 3, 5])) == 3
assert npages(pdfops.extract(make_pdf(5), [9, 10])) == 0            # out-of-range skipped
rot = pdfops.rotate(make_pdf(2), 90)
assert PdfReader(io.BytesIO(rot)).pages[0].rotation == 90
assert pdfops.parse_pages("1,3,5-7") == [1, 3, 5, 6, 7]

# --- HTTP endpoints ----------------------------------------------------------------------------
with TestClient(app) as c:
    a, b = make_pdf(2, "a"), make_pdf(1, "b")
    # info
    r = c.post("/pdf/info", files={"file": ("a.pdf", a, "application/pdf")}, headers=HDR)
    assert r.status_code == 200 and r.json()["pages"] == 2, r.text
    # merge (2 files → 3 pages)
    r = c.post("/pdf/merge", files=[("files", ("a.pdf", a, "application/pdf")),
                                    ("files", ("b.pdf", b, "application/pdf"))], headers=HDR)
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and npages(r.content) == 3, r.status_code
    assert c.post("/pdf/merge", files=[("files", ("a.pdf", a, "application/pdf"))], headers=HDR).status_code == 422
    # non-PDF rejected
    assert c.post("/pdf/info", files={"file": ("x.txt", b"hello", "text/plain")}, headers=HDR).status_code == 422
    # split → zip of per-page PDFs
    r = c.post("/pdf/split", files={"file": ("doc.pdf", make_pdf(3), "application/pdf")}, headers=HDR)
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert len(zf.namelist()) == 3, zf.namelist()
    # extract pages 1,3 → 2 pages
    r = c.post("/pdf/extract", files={"file": ("doc.pdf", make_pdf(5), "application/pdf")},
               data={"pages": "1,3"}, headers=HDR)
    assert r.status_code == 200 and npages(r.content) == 2, r.status_code
    # rotate all pages 90
    r = c.post("/pdf/rotate", files={"file": ("doc.pdf", make_pdf(2), "application/pdf")},
               data={"angle": "90"}, headers=HDR)
    assert r.status_code == 200 and PdfReader(io.BytesIO(r.content)).pages[0].rotation == 90, r.status_code

print("PDFOPS OK - merge(2+1)->3, split(3)->3 one-page PDFs (zip), extract(1,3,5)->3, rotate 90°, "
      "page-range parse '1,3,5-7'; HTTP merge/info/split/extract/rotate + non-PDF rejected; all pypdf "
      "(BSD), no PyMuPDF/AGPL.")
