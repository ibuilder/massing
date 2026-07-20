"""BEP-GEN — the BIM Execution Plan generated from the project's live config. A bare project yields a
valid skeleton (always-present sections configured, requirement/RACI/CDE sections unconfigured); adding
a responsibility matrix + a source model flips those sections to configured. Route + engine.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_bep.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_bep.db"
os.environ["STORAGE_DIR"] = "./test_storage_bep"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_bep.db"):
    os.remove("./test_bep.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import bep  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

SECTION_IDS = {"standards", "information_requirements", "roles", "cde", "exchange", "quality"}

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "BEP Project"}).json()["id"]

    # a bare project → valid skeleton BEP: all 6 sections present, the always-on ones configured
    b = c.get(f"/projects/{pid}/bep")
    assert b.status_code == 200, b.status_code
    j = b.json()
    assert j["project"]["name"] == "BEP Project" and j["project"]["has_model"] is False, j["project"]
    ids = {s["id"] for s in j["sections"]}
    assert ids == SECTION_IDS, ids
    by_id = {s["id"]: s for s in j["sections"]}
    # standards + quality are always configured (framework-level, not project-data-dependent)
    assert by_id["standards"]["configured"] is True and by_id["quality"]["configured"] is True
    # requirements / roles / cde / exchange need project data → unconfigured on a bare project
    assert by_id["roles"]["configured"] is False and by_id["cde"]["configured"] is False
    assert by_id["exchange"]["configured"] is False
    assert j["completeness"]["total"] == 6 and 0 < j["completeness"]["configured"] < 6, j["completeness"]
    base_configured = j["completeness"]["configured"]

    # give the project a source model → the exchange section configures with the IFC schema
    from aec_data import massing  # noqa: E402
    tmp = os.path.join(os.path.dirname(__file__), "_bep.ifc")
    massing.generate_blank_ifc(tmp, name="BEP model", storeys=1, storey_height=3.0, ground_size=10.0)
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = tmp
        db.commit()

    j2 = c.get(f"/projects/{pid}/bep").json()
    by_id2 = {s["id"]: s for s in j2["sections"]}
    assert j2["project"]["has_model"] is True, j2["project"]
    assert by_id2["exchange"]["configured"] is True, by_id2["exchange"]     # source model present
    assert "IFC" in by_id2["exchange"]["items"][0]["v"], by_id2["exchange"]["items"][0]
    assert j2["completeness"]["configured"] > base_configured, (base_configured, j2["completeness"])

# direct engine call: unknown project → graceful empty
with SessionLocal() as db:
    empty = bep.generate(db, "no-such-project")
    assert empty["project"] is None and empty["sections"] == [], empty

for f in ("./_bep.ifc",):
    p = os.path.join(os.path.dirname(__file__), f.lstrip("./"))
    if os.path.exists(p):
        os.remove(p)

print("BEP-GEN OK - a bare project yields a valid 6-section skeleton BEP (standards + quality-gates "
      "sections always configured; requirements/roles/CDE/exchange unconfigured until populated); adding a "
      "source model flips the exchange section to configured with the IFC schema and lifts the completeness "
      "count; an unknown project returns a graceful empty plan.")
