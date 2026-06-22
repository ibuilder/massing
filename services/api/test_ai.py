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

print("AI OK - ask endpoint grounds on a live snapshot (3 RFIs + 1 change event), "
      "degrades gracefully with no key, rejects empty questions; ai.ask seam verified")
