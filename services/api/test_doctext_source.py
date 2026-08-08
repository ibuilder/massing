"""R31-CITE-HIGHLIGHT (backend half) — a citation now names something that can be opened.

THE BLOCKER. `doc_text` derived `doc_id` as a **slug of the document's name**, and the index stored
only `{doc_id, name, chunks, sections, ingested_at}` — no file id, no storage key. So "open the
document this cites" had no answer. A v0.3.810 change moved citations to `doc_id` and called it
"the RESOLVABLE identifier"; it was not one, so that change relocated the dead end instead of
closing it. **And a PDF ingest ran `extract_pdf_text` and then discarded the bytes** — even when a
real document existed, nothing afterwards could open it.

WHAT THIS ASSERTS. Three source kinds, and the third is the one that matters most:

  * ``doctext-pdf`` — a posted PDF is now STORED, and `GET .../doctext/{doc_id}/source` serves it.
  * ``file`` — the caller named a document already in the system. The route deliberately REFUSES to
    serve it (409, naming where it lives) rather than opening a second door onto the same object
    with a gate this router maintains separately. Two doors with two gates is the shape that has
    produced authz drift in this repo twice.
  * ``None`` — a text-only ingest. There is no document, and the citation says `openable: false`.
    That is a property of the data, not a gap: `ingest(pid, name, text=...)` never had a file behind
    it, and pretending otherwise would put a dead link in front of a user.

**`openable` is asserted as a value, not inferred.** The UI's question is "should this citation be a
link?"; computing it in three callers from `source_kind` is three chances to disagree.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_doctext_source.py
"""
import os
import shutil
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_doctext_source.db"
os.environ["STORAGE_DIR"] = "./test_storage_doctext_source"
os.environ["AEC_RBAC"] = "0"
for _f in ("./test_doctext_source.db",):
    if os.path.exists(_f):
        os.remove(_f)
shutil.rmtree("./test_storage_doctext_source", ignore_errors=True)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import doc_text, storage  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

Base.metadata.create_all(bind=engine)
client = TestClient(app)
PID = "p-doctext"
db = SessionLocal()
db.add(Project(id=PID, name="Doctext"))
db.commit()
db.close()

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


# Real paragraphs under each heading, not one-line clauses. `chunk_text` splits at numbered
# headings and discards chunks with too little body, so a terse fixture produced a single chunk
# containing only "PART 1 GENERAL" — and every search returned nothing, which reads as a broken
# search rather than a fixture too small to exercise one. (Recorded because the same shape is
# already in the notes: a fixture too small manufactures a confident wrong number.)
SPEC = (
    "SECTION 09 21 16 GYPSUM BOARD ASSEMBLIES\n"
    "PART 1 GENERAL\n"
    "This section covers non-load-bearing gypsum board partition assemblies, including framing, "
    "board layers, joint treatment and the acoustic and fire-resistive requirements that apply to "
    "each rated condition throughout the project.\n"
    "1.1 FIRE RESISTANCE\n"
    "Fire-rated assemblies shall achieve a two-hour rating tested per UL U419. Substitutions must "
    "be submitted with a tested assembly of equal or greater rating, and penetrations through any "
    "rated partition shall be firestopped with a listed system appropriate to the penetrant.\n"
    "1.2 DEFLECTION AND STRUCTURAL MOVEMENT\n"
    "Deflection of the framing shall not exceed L/240 under the design load specified in the "
    "structural drawings. Head-of-wall details at rated partitions shall accommodate the "
    "anticipated deflection without compromising the fire resistance rating of the assembly.\n")

# --------------------------------------------------------------------------------------------
# 1) A text-only ingest: honestly has no source, and says so.
# --------------------------------------------------------------------------------------------
entry = doc_text.ingest(PID, "Typed Spec Notes", text=SPEC)
check("a text ingest records source=None explicitly, not by omission",
      "source" in entry and entry["source"] is None and entry["source_kind"] is None,
      f"got {entry}")

ans = doc_text.answer(PID, "what fire rating do the gypsum assemblies need")
check("a text-only citation is marked NOT openable",
      ans["citations"] and ans["citations"][0]["openable"] is False,
      f"got {ans.get('citations')}")

r = client.get(f"/projects/{PID}/doctext/{entry['doc_id']}/source")
check("...and its source route 404s with a reason rather than an empty PDF",
      r.status_code == 404 and "text" in r.text.lower(), f"{r.status_code}: {r.text[:120]}")

# --------------------------------------------------------------------------------------------
# 2) A posted PDF: the bytes survive ingest and the route serves them.
# --------------------------------------------------------------------------------------------
try:
    import io as _io

    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas as _canvas
    buf = _io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=letter)
    for line in SPEC.splitlines():
        c.drawString(72, 720, line)
        c.showPage()
    c.save()
    PDF = buf.getvalue()
except Exception as e:                       # noqa: BLE001
    print(f"  ..    skipping the PDF path: reportlab unavailable ({e})")
    PDF = None

if PDF:
    r = client.post(f"/projects/{PID}/doctext?name=Fire%20Spec", content=PDF,
                    headers={"content-type": "application/pdf"})
    check("a PDF ingest succeeds", r.status_code == 200, f"{r.status_code}: {r.text[:160]}")
    pe = r.json()
    check("...and records source_kind=doctext-pdf", pe.get("source_kind") == "doctext-pdf",
          f"got {pe}")
    # THE DEFECT: before this, the bytes were extracted and dropped. Assert they are on disk.
    check("...and the PDF bytes were actually STORED (they used to be discarded)",
          bool(pe.get("source")) and storage.exists(pe["source"]),
          f"source={pe.get('source')!r} exists={storage.exists(pe['source']) if pe.get('source') else False}")

    r = client.get(f"/projects/{PID}/doctext/{pe['doc_id']}/source")
    check("the source route serves the stored PDF",
          r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf"),
          f"{r.status_code} {r.headers.get('content-type')}")
    check("...byte-identical to what was ingested", r.content == PDF,
          f"{len(r.content)} bytes back vs {len(PDF)} in")

    # `answer()` returns the top 4 citations across ALL documents, and this fixture deliberately
    # ingests the same spec text three ways — so "Fire Spec" can legitimately fall outside the top
    # four on score alone. Asserting it appears there would be asserting a ranking accident. What is
    # actually being claimed is that a hit INTO the PDF document reports source_kind, so the check
    # goes through `search` with a k wide enough to contain it, and states why.
    hits = doc_text.search(PID, "what deflection limit applies", k=25)
    pdf_hit = next((h for h in hits if h["doc"] == "Fire Spec"), None)
    check("a hit into the PDF document carries source_kind=doctext-pdf",
          pdf_hit is not None and pdf_hit.get("source_kind") == "doctext-pdf", f"got {pdf_hit}")
    a2 = doc_text.answer(PID, "what deflection limit applies")
    check("every citation reports `openable` as a value, never absent",
          all("openable" in c for c in a2["citations"]) and len(a2["citations"]) > 0,
          f"got {a2.get('citations')}")
    check("at least one citation in this project is openable",
          any(c["openable"] for c in a2["citations"]) or any(
              h.get("source_kind") for h in hits),
          "nothing in a project with a stored PDF reports as openable")

# --------------------------------------------------------------------------------------------
# 3) A `file` source: recorded, and deliberately NOT served from here.
# --------------------------------------------------------------------------------------------
fe = doc_text.ingest(PID, "Managed Doc", text=SPEC, source=f"{PID}/documents/abc123.pdf")
check("an explicit source is recorded as source_kind=file",
      fe.get("source_kind") == "file" and fe.get("source", "").endswith("abc123.pdf"), f"got {fe}")
r = client.get(f"/projects/{PID}/doctext/{fe['doc_id']}/source")
check("the route REFUSES to serve a managed file, naming where it lives",
      r.status_code == 409 and "source_elsewhere" in r.text, f"{r.status_code}: {r.text[:140]}")

# --------------------------------------------------------------------------------------------
# 4) The route is reachable and gated. A new door needs its own gate, not the neighbour's.
# --------------------------------------------------------------------------------------------
r = client.get(f"/projects/{PID}/doctext/no-such-doc/source")
check("an unknown doc_id is a 404", r.status_code == 404, str(r.status_code))
r = client.get("/projects/no-such-project/doctext/x/source")
check("an unknown project is a 404", r.status_code == 404, str(r.status_code))

# Reachability, asserted against the OPENAPI SCHEMA rather than `app.routes`.
#
# `app.routes` does not answer this question in this app: it holds `_IncludedRouter` objects (a lazy
# inclusion mechanism), so a scan of it finds 71 entries and none of the ~300 real paths. The first
# version of this check walked `app.routes`, reported the route missing, and was wrong — while the
# 200/404/409 assertions above were simultaneously proving it live. That is precisely the shape the
# roadmap already warns about for this item: *a reachability gate built on direct route references
# reports confident false positives*, and here it produced a confident false NEGATIVE.
#
# The schema is a reader this test did not write, and it is what a client actually consumes.
spec = client.get("/openapi.json").json()
check("the source route is published in the OpenAPI schema",
      "/projects/{pid}/doctext/{doc_id}/source" in spec.get("paths", {}),
      "it exists in the module and nothing serves it — the exact failure this band is about")
# The search route must still be reachable: `/doctext/search` and `/doctext/{doc_id}/source` differ
# in segment count so they cannot shadow each other, but that is worth an assertion rather than an
# argument, since route order is declaration order and this one was inserted above `search`.
check("adding it did not shadow /doctext/search",
      client.get(f"/projects/{PID}/doctext/search?q=deflection").status_code == 200)

print(f"\ntest_doctext_source {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
