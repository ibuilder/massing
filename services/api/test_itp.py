"""TRANSMIT-ITP (ITP slice) — the Inspection & Test Plan register: the QA *plan* (hold/witness points +
acceptance criteria per work activity), distinct from the `inspection` module that logs field *results*.
A config module on the generic engine — assert it registers, creates with an ITP ref, and walks its
planned → active → verified workflow (verify gated on acceptance criteria).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_itp.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_itp.db"
os.environ["STORAGE_DIR"] = "./test_storage_itp"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_itp.db"):
    os.remove("./test_itp.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import modules_registry as mr  # noqa: E402
from aec_api.main import app  # noqa: E402

mr.load_registry()
assert "itp" in mr.REGISTRY and mr.REGISTRY["itp"]["section"] == "Quality", list(mr.REGISTRY)[:5]

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "ITP Project"}).json()["id"]

    # a Hold Point without acceptance criteria can be released but NOT verified (requires gate)
    rec = c.post(f"/projects/{pid}/modules/itp",
                 json={"data": {"activity": "Rebar placement — footings", "point_type": "Hold Point",
                                "method": "Visual", "spec_section": "03 20 00",
                                "responsible_party": "Third-Party Agency"}})
    assert rec.status_code == 201, rec.text[:200]
    r = rec.json()
    rid = r["id"]
    assert (r.get("ref") or "").startswith("ITP") and r.get("workflow_state") == "planned", r
    rel = c.post(f"/projects/{pid}/modules/itp/{rid}/transition", json={"action": "release"})
    assert rel.status_code == 200 and rel.json()["workflow_state"] == "active", rel.text[:200]
    # verify is gated on acceptance_criteria — should fail while it's blank
    v_block = c.post(f"/projects/{pid}/modules/itp/{rid}/transition", json={"action": "verify"})
    assert v_block.status_code >= 400, f"verify must be blocked without acceptance criteria: {v_block.status_code}"

    # add acceptance criteria, then verify succeeds
    c.patch(f"/projects/{pid}/modules/itp/{rid}",
            json={"acceptance_criteria": "Bar size/spacing/cover per drawings; ACI 318 tolerances"})
    v_ok = c.post(f"/projects/{pid}/modules/itp/{rid}/transition", json={"action": "verify"})
    assert v_ok.status_code == 200 and v_ok.json()["workflow_state"] == "verified", v_ok.text[:200]

    assert len(c.get(f"/projects/{pid}/modules/itp").json()) == 1

print("TRANSMIT-ITP OK - the Inspection & Test Plan register (Quality) registers on the generic engine; a "
      "Hold Point creates with an ITP ref in 'planned', releases to 'active', is BLOCKED from 'verified' "
      "until acceptance criteria are set, then verifies once they are — the QA plan (hold/witness points), "
      "distinct from the inspection results log.")
