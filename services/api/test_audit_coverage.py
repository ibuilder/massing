"""Audit-log coverage for the contractual/destructive module mutations. Workflow transitions
(RFI answered, CO approved) and record deletes are the state changes an owner/auditor must be able
to reconstruct — verify they land in the append-only audit_log (and are committed, not just added).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_audit_coverage.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_audit_coverage.db"
os.environ["STORAGE_DIR"] = "./test_storage_audit_coverage"
os.environ.pop("AEC_RBAC", None)
os.environ["AEC_TRUST_XUSER"] = "1"
for _f in ("./test_audit_coverage.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import AuditLog  # noqa: E402

H = {"X-User": "admin"}
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Audit"}, headers=H).json()["id"]
    rfi = c.post(f"/projects/{pid}/modules/rfi", headers=H,
                 json={"data": {"subject": "Beam core", "question": "OK to core?"}}).json()
    rid = rfi["id"]
    # a workflow transition (draft -> open) must be audited with actor + resulting state + record id
    assert c.post(f"/projects/{pid}/modules/rfi/{rid}/transition", headers=H,
                  json={"action": "submit"}).json()["workflow_state"] == "open"
    # a delete must be audited (it's destructive)
    rfi2 = c.post(f"/projects/{pid}/modules/rfi", headers=H,
                  json={"data": {"subject": "Scrap", "question": "?"}}).json()
    assert c.delete(f"/projects/{pid}/modules/rfi/{rfi2['id']}", headers=H).status_code == 200

    with SessionLocal() as db:
        rows = db.query(AuditLog).all()
        actions = [r.action for r in rows]
        # transition audited, and its row carries actor + record id + the state it moved to
        tr = next((r for r in rows if r.action == "module.transition:rfi:submit"), None)
        assert tr is not None, actions
        assert tr.actor == "admin" and tr.topic_id == rid, (tr.actor, tr.topic_id)
        assert (tr.detail or {}).get("state") == "open", tr.detail
        # delete audited
        assert any(r.action == "module.delete:rfi" and r.topic_id == rfi2["id"] for r in rows), actions

print("AUDIT COVERAGE OK - module workflow transitions (module.transition:<key>:<action>, with actor + "
      "record id + resulting state) and record deletes (module.delete:<key>) are written to the "
      "append-only audit_log and committed, so the contractual trail is reconstructable.")
