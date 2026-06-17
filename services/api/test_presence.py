"""Live presence + shared viewpoints. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_presence.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./pres_test.db"
os.environ["STORAGE_DIR"] = "./test_storage"
os.environ.pop("AEC_RBAC", None)
for f in ("./pres_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api import presence  # noqa: E402

H = lambda u: {"X-User": u}  # noqa: E731

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Live"}, headers=H("alice")).json()["id"]

    # alice heartbeats → sees no peers (herself excluded)
    r = c.post(f"/projects/{pid}/presence", headers=H("alice")).json()
    assert r["user"] == "alice" and r["active"] == [], r

    # bob heartbeats and shares a camera viewpoint
    vp = {"position": {"x": 12.0, "y": 4.5, "z": 7.6}, "target": {"x": 0, "y": 0, "z": 0}}
    c.post(f"/projects/{pid}/presence", json={"viewpoint": vp}, headers=H("bob"))

    # alice now sees bob in the roster, with the shared viewpoint
    roster = c.get(f"/projects/{pid}/presence", headers=H("alice")).json()["active"]
    assert any(p["user"] == "bob" and p["viewpoint"] == vp for p in roster), roster

    # a plain heartbeat keeps the last shared viewpoint (doesn't clear it)
    c.post(f"/projects/{pid}/presence", headers=H("bob"))
    roster = c.get(f"/projects/{pid}/presence", headers=H("alice")).json()["active"]
    assert any(p["user"] == "bob" and p["viewpoint"] == vp for p in roster), roster

    # TTL prune: nothing is "active" within 0 seconds
    assert presence.active(pid, ttl=0) == []

    print("PRESENCE OK — heartbeat roster, shared viewpoint, self-exclude, TTL prune")
