"""Preconstruction intelligence: contract risk review, scope-gap detection, and doc Q&A with
citations — exercising the offline rules path (no AI key).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_review.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_review.db"
os.environ["STORAGE_DIR"] = "./test_storage_review"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("ANTHROPIC_API_KEY", None)                # force the rules/offline path
for _f in ("./test_review.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient   # noqa: E402
from aec_api import review                  # noqa: E402
from aec_api.main import app                # noqa: E402

CONTRACT = (
    "The Subcontractor shall be paid only if and when the Owner pays the Contractor (pay-if-paid). "
    "No damages for delay shall be payable for any cause whatsoever. The Contractor may terminate "
    "for convenience at its sole discretion. Subcontractor shall indemnify and hold harmless the "
    "Contractor from all claims. Retainage of ten percent (10%) shall be withheld."
)
SPEC = (
    "Provide and install all fire-stopping as required. Structural steel by others. Louvers: TBD. "
    "Doors shall match existing. Coordinate with the mechanical trade for penetrations."
)

# --- engine (unit) ---
rc = review.review_contract(CONTRACT)
assert rc["source"] == "rules", rc
cats = {f["category"] for f in rc["findings"]}
assert {"Payment", "Delay", "Termination", "Indemnity"} <= cats, cats
assert rc["counts"]["high"] >= 2, rc["counts"]           # pay-if-paid + no-damage-for-delay are high
# severity ordering: first finding is high
assert rc["findings"][0]["severity"] == "high", rc["findings"][0]

sg = review.scope_gaps(SPEC)
assert sg["source"] == "rules", sg
markers = " ".join(g["marker"].lower() for g in sg["gaps"])
assert "by others" in markers and ("tbd" in markers or "as required" in markers), sg

pages = [{"page": 1, "text": "Retainage of 10% applies."}, {"page": 2, "text": "Warranty period is one year."}]
qa = review.ask_doc("what is the warranty period?", pages)
assert qa["citations"] and qa["citations"][0]["page"] == 2, qa
assert "warranty" in qa["answer"].lower() or "one year" in qa["answer"].lower(), qa

# empty inputs degrade cleanly
assert review.review_contract("")["source"] == "empty"
assert review.scope_gaps("")["source"] == "empty"

# --- endpoints (text form field, no file) ---
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Review"}).json()["id"]
    r = c.post(f"/projects/{pid}/review/contract", data={"text": CONTRACT})
    assert r.status_code == 200 and r.json()["counts"]["high"] >= 2, r.text[:200]
    r = c.post(f"/projects/{pid}/review/scope", data={"text": SPEC})
    assert r.status_code == 200 and len(r.json()["gaps"]) >= 2, r.text[:200]
    r = c.post(f"/projects/{pid}/review/ask", data={"question": "warranty period?",
                                                    "text": "Warranty period is one year."})
    assert r.status_code == 200 and r.json()["citations"], r.text[:200]

print("REVIEW OK - contract flags pay-if-paid/no-damage-for-delay (high) + indemnity/termination; "
      "scope gaps catch 'by others'/'TBD'/'as required'; doc Q&A cites p.2 for warranty; endpoints 200 "
      "on text form; empty inputs degrade to 'empty' (rules/offline path, no fabrication)")
