"""MASTER-BUILDER brief — the 8-step Master Builder Protocol run over a project's own data. A bare
project is all gaps (readiness 0, not grounded in place); setting a jurisdiction + seeding budget /
schedule / bid-package / compliance records lifts the matching steps to ready/partial and raises the
readiness score. Plus the /master-builder/brief route (404 on unknown project).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_master_builder.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_master_builder.db"
os.environ["STORAGE_DIR"] = "./test_storage_masterbuilder"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_master_builder.db"):
    os.remove("./test_master_builder.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import master_builder  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Tower on Nowhere"}).json()["id"]

    # --- a bare project: the protocol runs but every step is a gap, and it's not grounded in place ----
    with SessionLocal() as db:
        b0 = master_builder.brief(db, pid)
    assert b0["step_count"] == 8 and len(b0["steps"]) == 8, b0
    assert [s["n"] for s in b0["steps"]] == list(range(1, 9)), b0
    assert b0["grounded_in_place"] is False and b0["jurisdiction"] is None, b0
    assert b0["readiness_pct"] == 0.0 and b0["ready_steps"] == 0 and b0["gap_steps"] == 8, b0
    # every step carries its "why" + a link to the tool that closes its gap, and lists its gaps
    for s in b0["steps"]:
        assert s["why"] and s["link"] and s["status"] == "gap" and s["gaps"], s
    assert "not a substitute" in b0["disclaimer"].lower(), b0["disclaimer"]     # honest-status boundary

    # --- ground it in place + seed real signals across steps ------------------------------------------
    with SessionLocal() as db:
        p = db.get(Project, pid)
        p.jurisdiction = "CA"                     # step 1 place: the AHJ/state that resolves code editions
        db.commit()
    # feasibility (budget), delivery (schedule + bid package), regulatory (compliance evidence)
    c.post(f"/projects/{pid}/modules/budget", json={"data": {"name": "Sitework allowance", "amount": 500000}})
    c.post(f"/projects/{pid}/modules/schedule_activity",
           json={"data": {"name": "Excavate", "trade": "Earthwork", "duration": 10}})
    c.post(f"/projects/{pid}/modules/bid_package",
           json={"data": {"name": "Concrete", "discipline": "Structural"}})
    c.post(f"/projects/{pid}/modules/compliance_evidence",
           json={"data": {"requirement": "Egress width per CBC 1005", "outcome": "Pass"}})

    with SessionLocal() as db:
        b1 = master_builder.brief(db, pid)
    by = {s["key"]: s for s in b1["steps"]}
    assert b1["grounded_in_place"] is True and b1["jurisdiction"] == "CA", b1
    # place is partial now (jurisdiction present, but no source IFC model yet)
    assert by["place"]["status"] == "partial", by["place"]
    # feasibility has a budget line; delivery has BOTH a schedule and a bid package → ready
    assert by["feasibility"]["status"] in ("partial", "ready"), by["feasibility"]
    assert by["delivery"]["status"] == "ready", by["delivery"]
    assert any("schedule" in f["label"].lower() for f in by["delivery"]["findings"]), by["delivery"]
    # regulatory has the compliance ledger + a resolvable jurisdiction → ready
    assert by["regulatory"]["status"] == "ready", by["regulatory"]
    # the score strictly improved once real signals exist
    assert b1["readiness_pct"] > b0["readiness_pct"] and b1["ready_steps"] >= 2, b1

    # --- route ----------------------------------------------------------------------------------------
    r = c.get(f"/projects/{pid}/master-builder/brief")
    assert r.status_code == 200, r.status_code
    j = r.json()
    assert j["jurisdiction"] == "CA" and len(j["steps"]) == 8 and j["readiness_pct"] == b1["readiness_pct"], j
    assert c.get("/projects/no-such/master-builder/brief").status_code == 404

print("MASTER-BUILDER OK - the 8-step protocol runs over a project's own data: a bare project is all gaps "
      "(readiness 0%%, not grounded in place, every step links to the tool that closes it, with the "
      "not-a-substitute disclaimer); setting the jurisdiction grounds it in place and seeding budget / "
      "schedule+bid-package / compliance-evidence records lifts feasibility, delivery (ready) and regulatory "
      "(ready) and raises the readiness score; the /master-builder/brief route returns the brief and 404s "
      "on an unknown project.")
