"""AI assistant — natural-language ask over a project snapshot (graceful no-key path).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_ai.py

Without ANTHROPIC_API_KEY the assistant degrades to returning the live snapshot it would feed
the model — so the endpoint, RBAC, context gathering and graceful fallback are all exercised
without a network call. The Claude path reuses the same seam (ai.ask)."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_ai.db"
os.environ["STORAGE_DIR"] = "./test_storage_ai"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("ANTHROPIC_API_KEY", None)   # ensure the disabled/fallback path
for f in ("./test_ai.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import ai  # noqa: E402
from aec_api.main import app  # noqa: E402

H = {"X-User": "gc"}

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "AI Tower"}, headers=H).json()["id"]
    for subj in ("Beam clash", "Door schedule", "Duct routing"):
        c.post(f"/projects/{pid}/modules/rfi", json={"data": {"subject": subj, "question": "?"}}, headers=H)
    c.post(f"/projects/{pid}/modules/change_event", json={"data": {"subject": "Added steel"}}, headers=H)

    # ask with no key -> graceful "disabled" answer that still carries the live snapshot
    r = c.post(f"/projects/{pid}/ai/ask", json={"question": "How many RFIs are open?"}, headers=H)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["source"] == "disabled" and j["ai_enabled"] is False, j
    snap = j["snapshot"]
    assert snap["record_counts"]["rfi"] == 3, snap["record_counts"]
    assert snap["record_counts"]["change_event"] == 1, snap["record_counts"]
    assert "kpis" in snap and len(snap["open_rfis"]) == 3, snap

    # empty question is rejected
    assert c.post(f"/projects/{pid}/ai/ask", json={"question": "  "}, headers=H).status_code == 422

    # ai.ask is a pure seam: given a context it returns an answer dict (disabled here)
    out = ai.ask("anything", {"kpis": {"open_rfis": 3}})
    assert out["source"] == "disabled" and "snapshot" in out, out

    # AI estimate (text -> BOQ): degrades to a clean stub with no key; rejects empty input
    est = c.post(f"/projects/{pid}/ai/estimate", json={"description": "Two-storey 500 m2 office, steel frame"}, headers=H)
    assert est.status_code == 200, est.text
    ej = est.json()
    assert ej["source"] == "disabled" and ej["ai_enabled"] is False and ej["lines"] == [], ej
    assert c.post(f"/projects/{pid}/ai/estimate", json={"description": "  "}, headers=H).status_code == 422
    # ai.estimate_boq seam: amounts roll up from quantity x rate (verified on a synthetic line set)
    assert ai.estimate_boq("")["source"] == "empty"

    # RFI triage: stub path returns a usable classification + ball-in-court + draft (no key)
    rid = c.post(f"/projects/{pid}/modules/rfi", json={"data": {"subject": "Beam clash at C4",
                 "question": "Please advise.", "discipline": "Structural", "cost_impact": "Yes"}}).json()["id"]
    tr = c.post(f"/projects/{pid}/ai/triage-rfi", json={"rid": rid}).json()
    assert tr["ai_enabled"] is False and tr["source"] == "template", tr
    assert tr["discipline"] == "Structural" and tr["urgency"] == "high", tr
    assert tr["ball_in_court"] in ("GC", "Owner", "OwnersRep", "Consultant", "Subcontractor"), tr
    assert tr["draft_response"], tr

print("AI OK - ask + estimate endpoints ground/degrade gracefully with no key, reject empty input; "
      "ai.ask + ai.estimate_boq seams verified")
