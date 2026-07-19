"""W9-4 harder half: spec/code document text ingestion → cited extractive answers.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_doc_text.py"""
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_doc_text.db"
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="doctext_store_")
os.environ["IFC_DIR"] = tempfile.mkdtemp(prefix="doctext_ifc_")
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_doc_text.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import doc_text  # noqa: E402

SPEC = """SECTION 09 21 16 - GYPSUM BOARD ASSEMBLIES
Provide 5/8 inch Type X gypsum board at all rated partitions.
Fasteners at 12 inches on center maximum at panel edges.

SECTION 07 92 00 - JOINT SEALANTS
Sealant joints at exterior curtain wall shall use silicone sealant
with a movement capability of plus or minus 50 percent.
"""

# --- chunking: section headers split, titles + pages captured ---------------------------------------
chunks = doc_text.chunk_text(SPEC)
assert len(chunks) == 2, [c.get("section") for c in chunks]
assert chunks[0]["section"] == "09 21 16" and "GYPSUM" in (chunks[0]["title"] or ""), chunks[0]
assert "Type X" in chunks[0]["text"] and "silicone" in chunks[1]["text"]

# headerless text falls back to paragraph chunks (still citable by page)
plain = doc_text.chunk_text("First paragraph about concrete curing over several lines of text. " * 8
                            + "\n\n\n" + "Second paragraph about formwork removal criteria. " * 8)
assert len(plain) >= 2 and all(c["section"] is None for c in plain), len(plain)

# --- ingest + catalog + search ----------------------------------------------------------------------
PID = "docproj"
entry = doc_text.ingest(PID, "Project Spec Div 07-09", text=SPEC)
assert entry["chunks"] == 2 and entry["sections"] == 2, entry
assert doc_text.catalog(PID)["documents"][0]["doc_id"] == "project-spec-div-07-09"

# a section-number query surfaces THAT section first (boosted)
hits = doc_text.search(PID, "what does 07 92 00 require?")
assert hits and hits[0]["section"] == "07 92 00", hits[:1]
# a content query finds the right chunk with doc+page cites
hits2 = doc_text.search(PID, "gypsum fastener spacing")
assert hits2 and hits2[0]["section"] == "09 21 16" and hits2[0]["page"] == 1, hits2[:1]

# --- extractive answers: the document's own words, cited; no match is honest ------------------------
a = doc_text.answer(PID, "what sealant movement capability is required at the curtain wall?")
assert a["answer"] and "50 percent" in a["answer"], a["answer"]
assert "§07 92 00" in a["answered_from"] and a["citations"], a["answered_from"]
none = doc_text.answer(PID, "helicopter landing pad striping")
assert none["answer"] is None and "ingest" in none["note"], none

# re-ingesting a name replaces (never duplicates)
doc_text.ingest(PID, "Project Spec Div 07-09", text=SPEC)
assert len(doc_text.catalog(PID)["documents"]) == 1

# --- PDF path + endpoints ---------------------------------------------------------------------------
import io  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from aec_api.main import app  # noqa: E402

buf = io.BytesIO()
cv = canvas.Canvas(buf, pagesize=letter)
cv.drawString(72, 720, "SECTION 03 30 00 - CAST-IN-PLACE CONCRETE")
cv.drawString(72, 700, "Concrete shall reach 4000 psi at 28 days.")
cv.save()
PDF = buf.getvalue()

H = {"X-User": "editor"}
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "DocText"}, headers=H).json()["id"]
    # JSON text ingest
    r = c.post(f"/projects/{pid}/doctext", json={"name": "Spec", "text": SPEC}, headers=H)
    assert r.status_code == 200 and r.json()["chunks"] == 2, r.text[:200]
    # raw PDF ingest
    rp = c.post(f"/projects/{pid}/doctext?name=Structural Notes", content=PDF,
                headers={**H, "Content-Type": "application/pdf"})
    assert rp.status_code == 200 and rp.json()["chunks"] >= 1, rp.text[:300]
    assert c.get(f"/projects/{pid}/doctext", headers=H).json()["documents"], "catalog lists both"
    s = c.get(f"/projects/{pid}/doctext/search", params={"q": "4000 psi concrete"}, headers=H).json()
    assert s["hits"] and s["hits"][0]["doc"] == "Structural Notes", s["hits"][:1]
    ans = c.post(f"/projects/{pid}/doctext/ask",
                 json={"question": "what strength must the concrete reach?"}, headers=H).json()
    assert ans["answer"] and "4000 psi" in ans["answer"], ans
    assert c.post(f"/projects/{pid}/doctext/ask", json={}, headers=H).status_code == 400
    # empty ingest is a clean 400
    assert c.post(f"/projects/{pid}/doctext", json={"name": "x", "text": "  "},
                  headers=H).status_code == 400

    # the NL-QA route now falls through to the ingested documents (cited, intent=document)
    g = c.post(f"/projects/{pid}/generate/massing",
               json={"lot_width": 20, "lot_depth": 15, "far": 1.0}, headers=H)
    assert g.status_code == 200, g.text[:200]
    qa = c.post(f"/projects/{pid}/rfi/qa",
                json={"question": "what psi must cast-in-place concrete reach?"}, headers=H).json()
    assert qa["intent"] == "document" and "4000 psi" in qa["answer"], (qa["intent"], qa.get("answer"))
    assert qa["citations"] and qa["citations"][0]["kind"] == "document", qa["citations"][:1]

print("DOC-TEXT OK - W9-4 harder half: chunking splits at spec-section headers (title+page kept, "
      "headerless -> paragraph chunks); ingest/catalog/replace; search boosts section-number queries "
      "and finds content ('gypsum fastener spacing' -> 09 21 16); answers are the document's OWN text "
      "with doc/section/page cites and honest no-match; PDF ingest via pypdf ('4000 psi' round-trips); "
      "endpoints serve ingest(JSON+PDF)/catalog/search/ask; /rfi/qa falls through to documents with "
      "intent=document and kind=document citations.")
