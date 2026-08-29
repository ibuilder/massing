"""`pdf_sanity` is a pre-ingest gate because it RUNS at ingest, not because it says so.

`supply_chain.pdf_sanity`'s docstring called it *"a fast pre-ingest gate that flags a PDF worth a
closer look"* while having **no runtime caller anywhere** — a role asserted in prose and held by
nothing, the same shape as `pid_lock.cross_process_status`, whose boot-guard comment named a `/health`
surface that did not exist (v0.3.1115).

It is now wired into `routers/drawings._read_pdf`, the single chokepoint every PDF tool
(`info`/`merge`/`split`/`extract`/`rotate`) reads through. That location matters twice over:

* `_read_pdf` was hand-rolling `data[:4] != b"%PDF"` — a weaker second copy of a check that already
  existed properly in `pdf_sanity`, which is the duplicated-derivation shape behind most of this
  phase's findings.
* These routes read the whole upload into memory and hand it to pypdf, and had **no size cap at all**.

Asserted by driving the real routes, not by reading the source: a substring check would pass on the
docstring that describes the wiring, which is exactly how the first version of
`test_r37_consolidate.py` fooled itself one release earlier.
"""
import io
import os
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

os.environ["DATABASE_URL"] = "sqlite:///./test_pdf_ingest_gate.db"
os.environ["STORAGE_DIR"] = "./test_storage_pdf_ingest_gate"
os.environ["AEC_LOCAL_MODE"] = "1"
for _f in ("./test_pdf_ingest_gate.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import supply_chain  # noqa: E402
from aec_api.main import app  # noqa: E402

checks = 0


def check(cond, msg):
    """Assert `cond`, counting it, so the summary reports how much was actually verified."""
    global checks
    assert cond, msg
    checks += 1


def minimal_pdf(extra: bytes = b"") -> bytes:
    """A genuinely valid one-page PDF, optionally carrying `extra` active-content bytes.

    Built with reportlab rather than hand-assembled: a hand-written PDF with no xref table is refused
    by pypdf (`startxref not found`), so the fixture would have failed for a reason unrelated to what
    this file is testing. `extra` is appended after `%%EOF` — `pdf_sanity` is a byte scan so it sees
    the token, and pypdf still reads the file because the xref is intact, which is precisely the case
    worth covering: a PDF that parses cleanly *and* carries active content.
    """
    from reportlab.pdfgen import canvas as _canvas
    buf = io.BytesIO()
    cv = _canvas.Canvas(buf)
    cv.drawString(72, 720, "massing test sheet")
    cv.save()
    return buf.getvalue() + extra


with TestClient(app) as c:
    # --- the gate refuses what it is supposed to refuse, THROUGH the route ---------------------
    r = c.post("/pdf/info", files={"file": ("x.txt", b"not a pdf at all", "application/pdf")})
    check(r.status_code == 422, f"a non-PDF must be refused: {r.status_code}")
    check("not a PDF" in r.text, r.text)

    r = c.post("/pdf/info", files={"file": ("empty.pdf", b"", "application/pdf")})
    check(r.status_code == 422, f"an empty upload must be refused: {r.status_code}")

    # Over the cap. Compressible bytes so the fixture stays cheap to build.
    big = b"%PDF-1.4\n" + zlib.decompress(zlib.compress(b"\0" * (51 * 1024 * 1024)))
    r = c.post("/pdf/info", files={"file": ("big.pdf", big, "application/pdf")})
    check(r.status_code == 413, f"an oversize PDF must be refused with 413, got {r.status_code}")
    check("50 MB" in r.text, r.text)
    del big

    # --- a good PDF still passes, and now carries its sanity report -----------------------------
    r = c.post("/pdf/info", files={"file": ("ok.pdf", minimal_pdf(), "application/pdf")})
    check(r.status_code == 200, f"a valid PDF must still be accepted: {r.status_code} {r.text[:200]}")
    body = r.json()
    check("sanity" in body, f"/pdf/info must report the pre-ingest check: {sorted(body)}")
    check(body["sanity"]["header_ok"] is True and body["sanity"]["size"] > 0, body["sanity"])
    check(body["sanity"]["active_content"] == [], body["sanity"])
    check("pages" in body, "the existing pdfops.info fields must survive")

    # --- active content is REPORTED, not refused ------------------------------------------------
    # Refusing would break CAD-exported drawings that legitimately carry an OpenAction, and the
    # value here is that a caller can SEE it — pypdf carries it into whatever this route returns.
    hostile = minimal_pdf(b"/OpenAction<</S/JavaScript/JS(app.alert\\(1\\))>>")
    r = c.post("/pdf/info", files={"file": ("active.pdf", hostile, "application/pdf")})
    check(r.status_code == 200, f"active content must not be refused: {r.status_code}")
    active = r.json()["sanity"]["active_content"]
    check("JavaScript" in active and "OpenAction" in active, f"must surface both tokens: {active}")

    # ...and the same file still flows through a tool route, unrefused.
    r = c.post("/pdf/rotate", files={"file": ("active.pdf", hostile, "application/pdf")},
               data={"angle": "90"})
    check(r.status_code == 200, f"a tool route must not refuse active content either: {r.status_code}")

    # --- EVERY tool route goes through the chokepoint, not just /pdf/info -----------------------
    # This is the assertion that would have failed if pdf_sanity were wired into one route and the
    # docstring generalised — the shape of the original defect.
    junk = {"file": ("x.txt", b"definitely not a pdf", "application/pdf")}
    for path, data in [("/pdf/info", None), ("/pdf/split", None),
                       ("/pdf/extract", {"pages": "1"}), ("/pdf/rotate", {"angle": "90"})]:
        r = c.post(path, files=junk, data=data)
        check(r.status_code == 422, f"{path} must refuse a non-PDF at ingest: {r.status_code}")
    r = c.post("/pdf/merge", files=[("files", ("a.pdf", minimal_pdf(), "application/pdf")),
                                    ("files", ("b.txt", b"not a pdf", "application/pdf"))])
    check(r.status_code == 422, f"/pdf/merge must refuse a non-PDF member: {r.status_code}")

    # --- a merge is bounded by the SET, not only by each member --------------------------------
    # `_read_pdf`'s per-file cap is one a merge multiplies: N files each just under it are N
    # acceptances, and every byte is held at once for pypdf. `MaxBodySizeMiddleware` bounds the whole
    # request, but its own docstring records the half it does not close — "it does not stop a handler
    # materialising the body it did receive". Raised in review on #374.
    one = minimal_pdf()
    too_many = [("files", (f"{i}.pdf", one, "application/pdf")) for i in range(60)]
    r = c.post("/pdf/merge", files=too_many)
    check(r.status_code == 422, f"a 60-file merge must be refused by count: {r.status_code}")
    check("at most" in r.text, r.text)
    # ...and two files that each pass individually can still exceed the set's budget.
    fat = one + b"%" + b"\0" * (150 * 1024 * 1024 // 1)
    check(len(fat) < 50 * 1024 * 1024 * 4, "fixture sanity")
    r = c.post("/pdf/merge", files=[("files", ("a.pdf", fat[:40 * 1024 * 1024], "application/pdf")),
                                    ("files", ("b.pdf", fat[:40 * 1024 * 1024], "application/pdf")),
                                    ("files", ("c.pdf", fat[:40 * 1024 * 1024], "application/pdf")),
                                    ("files", ("d.pdf", fat[:40 * 1024 * 1024], "application/pdf")),
                                    ("files", ("e.pdf", fat[:40 * 1024 * 1024], "application/pdf")),
                                    ("files", ("f.pdf", fat[:40 * 1024 * 1024], "application/pdf"))])
    check(r.status_code == 413, f"a merge over the total budget must be refused: {r.status_code}")
    check("in total" in r.text, r.text)
    del fat
    # A normal two-file merge still works.
    r = c.post("/pdf/merge", files=[("files", ("a.pdf", one, "application/pdf")),
                                    ("files", ("b.pdf", one, "application/pdf"))])
    check(r.status_code == 200, f"an ordinary merge must still succeed: {r.status_code}")

    # --- a missing %%EOF trailer is NOT a refusal, and that is measured, not assumed -------------
    # `pdf_sanity` looks for `%%EOF` in the last 1024 bytes, so appended data — incremental updates,
    # an embedded signature, scanner padding — trips the flag on a valid file. Review asked for a 422
    # here (#374); this asserts the opposite, because the file below is one pypdf reads happily and
    # refusing it would reject real drawings to prevent nothing.
    padded = minimal_pdf() + b"%" + b"A" * 2000 + b"\n"
    check("no %%EOF trailer" in supply_chain.pdf_sanity(padded)["flags"],
          "the fixture must actually trip the flag, or this proves nothing")
    r = c.post("/pdf/info", files={"file": ("padded.pdf", padded, "application/pdf")})
    check(r.status_code == 200, f"a readable PDF past the EOF window must be accepted: {r.status_code}")
    check(r.json()["pages"] >= 1, "...and pypdf reads its pages, which is why refusing it would be wrong")

# --- the engine itself still behaves as its own tests expect -----------------------------------
check(supply_chain.pdf_sanity(b"")["ok"] is False, "empty is not ok")
check(supply_chain.pdf_sanity(minimal_pdf())["ok"] is True, supply_chain.pdf_sanity(minimal_pdf()))

print(f"PDF-INGEST OK — {checks} checks. pdf_sanity now runs at the one chokepoint every PDF tool "
      "reads through, so the 'pre-ingest gate' in its docstring is a fact rather than a claim. "
      "Asserted by driving the real routes: header, empty and a 50 MB cap (there was none) are "
      "refused; active content is reported through /pdf/info and deliberately not refused.")
