"""Auto-propagate 2D on model change: publishing a new model bumps an in-process version that the 2D
sync-status surfaces (and /drawings/stream pushes), so on-demand drawings regenerate. No event bus.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_model_events.py"""
import json
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_model_events.db"
os.environ["STORAGE_DIR"] = "./test_storage_model_events"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_model_events.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import model_events  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- unit: monotonic version + signature-reconcile ------------------------------------------------
assert model_events.current("px")["version"] == 0
assert model_events.bump("px", "sigA")["version"] == 1
assert model_events.bump("px", "sigB")["version"] == 2
# observe with an unchanged signature does NOT bump; a changed one does
assert model_events.observe("px", "sigB")["version"] == 2
assert model_events.observe("px", "sigC")["version"] == 3


def _props(guids):
    return {"schema": "IFC4", "elements": [{"guid": g, "ifc_class": "IfcWall"} for g in guids]}


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    # no model yet -> version 0, not stale-able
    s0 = c.get(f"/projects/{pid}/drawings/sync-status").json()
    assert s0["version"] == 0 and s0["model_loaded"] is False, s0

    # publish a model -> version bumps to 1, signature appears
    c.post(f"/projects/{pid}/properties/index",
           files={"file": ("props.json", json.dumps(_props(["g1", "g2"])).encode(), "application/json")})
    s1 = c.get(f"/projects/{pid}/drawings/sync-status").json()
    assert s1["version"] == 1 and s1["model_loaded"] and s1["signature"], s1

    # re-reading sync-status with the SAME model must NOT keep bumping (idempotent)
    assert c.get(f"/projects/{pid}/drawings/sync-status").json()["version"] == 1

    # publish a CHANGED model -> version bumps again + signature changes (2D is now stale)
    c.post(f"/projects/{pid}/properties/index",
           files={"file": ("props.json", json.dumps(_props(["g1", "g2", "g3"])).encode(), "application/json")})
    s2 = c.get(f"/projects/{pid}/drawings/sync-status").json()
    assert s2["version"] == 2 and s2["signature"] != s1["signature"], (s1, s2)

print("MODEL EVENTS OK - monotonic version + signature-reconcile (no double-bump on unchanged); "
      "publishing a model bumps sync-status version (0->1), a re-read is idempotent (stays 1), and a "
      "changed model bumps again (->2) with a new signature - the auto-propagate staleness signal")
