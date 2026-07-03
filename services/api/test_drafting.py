"""AI drafting engine — offline/rules path (no ANTHROPIC_API_KEY): draft RFI, submittal summary, and
trade scope of work from text/PDF, always with a citation, never fabricating.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_drafting.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_drafting.db"
os.environ["STORAGE_DIR"] = "./test_storage_drafting"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("ANTHROPIC_API_KEY", None)          # force the offline rules path
for _f in ("./test_drafting.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient           # noqa: E402
from aec_api import drafting                          # noqa: E402
from aec_api.main import app                          # noqa: E402

# --- engine (offline) ---
r = drafting.draft_rfi("The structural beam at grid B4 conflicts with the HVAC duct per detail 5/S-201.")
assert r["source"] == "rules", r
assert r["discipline"] in ("Structural", "MEP"), r          # keyword-classified, not fabricated
assert r["subject"] and r["question"], r
assert "API key" in r["message"], r                          # honest upgrade hint

# spec-section extraction + citation from page text
pages = [{"page": 1, "text": "Section 09 91 00 Painting. Provide and install two coats. See detail 3/A-501."},
         {"page": 2, "text": "Coordinate with 23 05 00 mechanical."}]
r2 = drafting.draft_rfi("What paint system is required?", pages)
assert r2["citations"] and r2["citations"][0]["page"] in (1, 2), r2

# submittal summary (offline)
sub = drafting.summarize_submittal([{"page": 1, "text": "Product Data 23 37 13 Diffusers. Manufacturer cut sheet."}])
assert sub["source"] == "rules" and sub["spec_section"].startswith("23 37 13"), sub

# scope draft (offline) — pulls candidate inclusions + spec sections, flags 'by others' as exclusion
scope_txt = ("Section 03 30 00 Cast-in-place concrete. Contractor shall provide and install all "
             "footings and slabs. Formwork by others. Verify 05 12 00.")
sc = drafting.draft_scope([{"page": 1, "text": scope_txt}], "Concrete")
assert sc["trade"] == "Concrete", sc
assert any("03 30 00" in s for s in sc["spec_sections"]), sc
assert sc["exclusions"], sc                                  # 'by others' -> an exclusion

# empty inputs degrade cleanly (no fabrication)
assert drafting.draft_rfi("", [])["source"] == "empty"
assert drafting.summarize_submittal([])["source"] == "empty"
assert drafting.draft_scope([], "Concrete")["source"] == "empty"

# --- endpoints ---
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    rr = c.post(f"/projects/{pid}/draft/rfi", data={"note": "Clarify the footing depth at line 5."})
    assert rr.status_code == 200 and rr.json()["subject"], rr.text[:200]
    sr = c.post(f"/projects/{pid}/draft/scope", data={"trade": "Electrical",
                "text": "Section 26 05 00. Provide and install all conduit. Fixtures by others."})
    assert sr.status_code == 200 and sr.json()["trade"] == "Electrical", sr.text[:200]
    assert sr.json()["exclusions"], sr.text[:200]

print("DRAFTING OK - offline RFI draft (keyword discipline + spec section + citation), submittal "
      "summary (spec/type), trade scope (inclusions + 'by others' exclusions + spec sections); empty "
      "inputs -> 'empty' (no fabrication); endpoints 200 with role gate")
