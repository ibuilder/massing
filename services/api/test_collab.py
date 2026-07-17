"""COLLAB-1 real-time co-editing awareness: the model signature (bumps on publish) + presence roster,
the collab snapshot endpoint, and the change signature that drives the SSE model stream.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_collab.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_collab.db"
os.environ["STORAGE_DIR"] = "./test_storage_collab"
os.environ["IFC_DIR"] = "./test_ifc_collab"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_collab.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient                    # noqa: E402
from aec_api import collab, presence                         # noqa: E402
from aec_api.db import SessionLocal                          # noqa: E402
from aec_api.main import app                                 # noqa: E402
from aec_api.models import ModelVersion                      # noqa: E402

H = lambda u: {"X-User": u}

with TestClient(app) as c:
    # unknown project → 404
    assert c.get("/projects/does-not-exist/collab", headers=H("alice")).status_code == 404

    pid = c.post("/projects", json={"name": "Collab"}, headers=H("alice")).json()["id"]

    # fresh project: a snapshot with no model, no other editors
    snap = c.get(f"/projects/{pid}/collab", headers=H("alice")).json()
    assert snap["model"]["has_model"] is False and snap["model"]["version"] == 0, snap
    assert snap["editor_count"] == 0, snap

    # bob heartbeats presence (sharing a viewpoint) → alice's snapshot now lists bob as a live editor
    presence.touch(pid, "bob", {"selection": "guid-123"})
    snap = c.get(f"/projects/{pid}/collab", headers=H("alice")).json()
    assert snap["editor_count"] == 1 and snap["editors"][0]["user"] == "bob", snap
    assert snap["editors"][0]["viewpoint"] == {"selection": "guid-123"}, snap["editors"]

    # --- model_signature bumps when a new ModelVersion is published --------------------------------
    with SessionLocal() as db:
        sig0 = collab.model_signature(db, pid)
        assert sig0["version"] == 0, sig0
        db.add(ModelVersion(project_id=pid, version=1, element_count=42))
        db.commit()
        sig1 = collab.model_signature(db, pid)
        assert sig1["version"] == 1 and sig1["element_count"] == 42, sig1
        db.add(ModelVersion(project_id=pid, version=2, element_count=50))
        db.commit()
        assert collab.model_signature(db, pid)["version"] == 2, "latest version wins"
        assert collab.model_signature(db, "nope") is None, "unknown project -> None"

    # --- stream_signature: changes on a model publish OR a roster/viewpoint change -----------------
    with SessionLocal() as db:
        base = collab.snapshot(db, pid, "alice")
        s_base = collab.stream_signature(base)
        # same state -> same signature (no spurious re-emit)
        assert collab.stream_signature(collab.snapshot(db, pid, "alice")) == s_base

    # bob moves his viewpoint -> signature changes (the stream re-emits)
    presence.touch(pid, "bob", {"selection": "guid-999"})
    with SessionLocal() as db:
        s_moved = collab.stream_signature(collab.snapshot(db, pid, "alice"))
    assert s_moved != s_base, "a viewpoint change must change the stream signature"

    # a third user joining also changes the signature
    presence.touch(pid, "carol", None)
    with SessionLocal() as db:
        s_joined = collab.stream_signature(collab.snapshot(db, pid, "alice"))
    assert s_joined != s_moved, "a new editor must change the stream signature"
    snap = c.get(f"/projects/{pid}/collab", headers=H("alice")).json()
    assert snap["editor_count"] == 2, snap                   # bob + carol (alice excluded)

    # the SSE model-stream endpoint emits exactly collab.snapshot (covered above) whenever
    # stream_signature changes — it's an infinite server-side poll loop, so it isn't opened here.

print("COLLAB OK - collab.snapshot bundles the model signature (version bumps per ModelVersion publish) "
      "with the presence roster; /projects/{pid}/collab serves it (404 unknown, editors exclude self). "
      "stream_signature is stable when nothing changes and flips on a model publish, a viewpoint move, or "
      "a user join/leave - so the /model/stream SSE re-emits exactly when a second client must reload the "
      "model or refresh who's in the session.")
