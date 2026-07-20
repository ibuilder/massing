"""PM-CLOSE — the project charter (initiating) + lessons-learned register (closing) modules that close
the PMBOK process-group spine. Both are config-only modules on the generic engine: assert they register,
create records with the right ref prefixes, and run their workflows.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_pm_close.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_pm_close.db"
os.environ["STORAGE_DIR"] = "./test_storage_pmclose"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_pm_close.db"):
    os.remove("./test_pm_close.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import modules_registry as mr  # noqa: E402
from aec_api.main import app  # noqa: E402

# both modules are discovered by the registry with the expected metadata
mr.load_registry()
assert "project_charter" in mr.REGISTRY and "lessons_learned" in mr.REGISTRY, list(mr.REGISTRY)[:5]
assert mr.REGISTRY["project_charter"]["section"] == "Preconstruction"
assert mr.REGISTRY["lessons_learned"]["section"] == "Closeout"

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "PM Close"}).json()["id"]

    # --- project charter: create → submit_for_review → authorize -----------------------------------
    ch = c.post(f"/projects/{pid}/modules/project_charter",
                json={"data": {"title": "Downtown Tower Charter", "sponsor": "Owner LLC",
                               "project_manager": "A. Manager", "business_case": "Fill the market gap",
                               "objectives": "Deliver 30 storeys by Q4"}})
    assert ch.status_code == 201, ch.text[:200]
    cr = ch.json()
    rid = cr["id"]
    assert (cr.get("ref") or "").startswith("CHTR"), cr.get("ref")
    assert cr.get("workflow_state") == "draft", cr
    # walk the initiating workflow to approved
    r1 = c.post(f"/projects/{pid}/modules/project_charter/{rid}/transition", json={"action": "submit_for_review"})
    assert r1.status_code == 200 and r1.json()["workflow_state"] == "in_review", r1.text[:200]
    r2 = c.post(f"/projects/{pid}/modules/project_charter/{rid}/transition", json={"action": "authorize"})
    assert r2.status_code == 200 and r2.json()["workflow_state"] == "approved", r2.text[:200]

    # --- lessons learned: create → review → adopt --------------------------------------------------
    ll = c.post(f"/projects/{pid}/modules/lessons_learned",
                json={"data": {"title": "Coordinate MEP earlier", "category": "What to improve",
                               "phase": "Construction", "impact": "High",
                               "recommendation": "Run MEP clash reviews at 60% DD"}})
    assert ll.status_code == 201, ll.text[:200]
    lr = ll.json()
    lid = lr["id"]
    assert (lr.get("ref") or "").startswith("LL"), lr.get("ref")
    assert lr.get("workflow_state") == "logged", lr
    a1 = c.post(f"/projects/{pid}/modules/lessons_learned/{lid}/transition", json={"action": "review"})
    assert a1.status_code == 200 and a1.json()["workflow_state"] == "reviewed", a1.text[:200]
    a2 = c.post(f"/projects/{pid}/modules/lessons_learned/{lid}/transition", json={"action": "adopt"})
    assert a2.status_code == 200 and a2.json()["workflow_state"] == "adopted", a2.text[:200]

    # both registers list their record
    assert len(c.get(f"/projects/{pid}/modules/project_charter").json()) == 1
    assert len(c.get(f"/projects/{pid}/modules/lessons_learned").json()) == 1

print("PM-CLOSE OK - the project_charter (Preconstruction/initiating) and lessons_learned "
      "(Closeout/closing) modules register on the generic engine; a charter creates with a CHTR ref and "
      "walks draft->in_review->approved, a lesson creates with an LL ref and walks logged->reviewed->adopted; "
      "both registers list their record.")
