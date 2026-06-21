"""Evidence gate: modules with close_requires_attachment can't enter a sign-off state until a
photo/attachment exists. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_evidence_gate.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./evidence_test.db"
os.environ["STORAGE_DIR"] = "./test_storage_ev"
os.environ.pop("AEC_RBAC", None)
for f in ("./evidence_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Evidence"}).json()["id"]

    # punchlist: open -> ready -> (verify needs a photo) -> verified
    r = c.post(f"/projects/{pid}/modules/punchlist", json={"data": {"description": "Touch-up paint"}}).json()
    rid = r["id"]
    assert c.post(f"/projects/{pid}/modules/punchlist/{rid}/transition", json={"action": "ready_to_inspect"}).status_code == 200
    # verify with no attachment -> blocked
    blocked = c.post(f"/projects/{pid}/modules/punchlist/{rid}/transition", json={"action": "verify"})
    assert blocked.status_code == 400 and "attachment" in blocked.json()["detail"], blocked.json()
    # attach a photo, then verify -> allowed
    up = c.post(f"/projects/{pid}/modules/punchlist/{rid}/attachments",
                files={"file": ("fix.jpg", b"\xff\xd8\xff demo", "image/jpeg")})
    assert up.status_code in (200, 201), up.text
    ok = c.post(f"/projects/{pid}/modules/punchlist/{rid}/transition", json={"action": "verify"})
    assert ok.status_code == 200 and ok.json()["workflow_state"] == "verified", ok.json()

    # an ungated module (rfi) transitions freely with no attachment
    rf = c.post(f"/projects/{pid}/modules/rfi", json={"data": {"subject": "Q", "question": "?"}}).json()
    assert c.post(f"/projects/{pid}/modules/rfi/{rf['id']}/transition", json={"action": "submit"}).status_code == 200

    print("EVIDENCE GATE OK - sign-off blocked without a photo, allowed after; ungated modules unaffected")
