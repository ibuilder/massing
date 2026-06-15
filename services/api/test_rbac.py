"""RBAC test — enforced mode. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_rbac.py"""
import os

os.environ["AEC_RBAC"] = "1"  # must be set before importing the app
os.environ["DATABASE_URL"] = "sqlite:///./rbac_test.db"
os.environ["STORAGE_DIR"] = "./test_storage"
for f in ("./rbac_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402

H = lambda u: {"X-User": u}  # noqa: E731

with TestClient(app) as c:
    # alice creates a project -> becomes admin
    pid = c.post("/projects", json={"name": "Secure"}, headers=H("alice")).json()["id"]
    assert c.get(f"/projects/{pid}/members", headers=H("alice")).json() == [{"user": "alice", "role": "admin"}]

    # bob (no role) cannot create a topic
    r = c.post(f"/projects/{pid}/topics", json={"type": "rfi", "title": "x"}, headers=H("bob"))
    assert r.status_code == 403, r.status_code

    # bob also cannot read members (needs viewer)
    assert c.get(f"/projects/{pid}/members", headers=H("bob")).status_code == 403

    # alice grants bob reviewer
    g = c.post(f"/projects/{pid}/members", json={"user": "bob", "role": "reviewer"}, headers=H("alice"))
    assert g.status_code == 201, g.text

    # now bob can create a topic (reviewer) ...
    t = c.post(f"/projects/{pid}/topics", json={"type": "rfi", "title": "Bob's RFI"}, headers=H("bob"))
    assert t.status_code == 201, t.text
    # ... but cannot edit the IFC (needs editor)
    e = c.post(f"/projects/{pid}/edit", json={"recipe": "batch_tag", "params": {}}, headers=H("bob"))
    assert e.status_code == 403, e.status_code

    # bob can read (viewer-level inherited by reviewer)
    assert c.get(f"/projects/{pid}/topics", headers=H("bob")).status_code == 200

    # carol (no role) cannot even be granted by bob (needs admin)
    assert c.post(f"/projects/{pid}/members", json={"user": "carol", "role": "viewer"},
                  headers=H("bob")).status_code == 403

    print("RBAC OK — admin/reviewer/editor/viewer enforced; default-deny for non-members")
