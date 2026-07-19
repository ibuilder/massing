"""BCF-API-SRV — the server-side BCF-API 2.1 (OpenCDE) surface over native Topics/Comments:
version negotiation, projects, topics (list/get/create), comments (list/create), mapped to the
BCF-API JSON shape and addressed by topic guid.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_bcf_api.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_bcf_api.db"
os.environ["STORAGE_DIR"] = "./test_storage_bcf_api"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_bcf_api.db"):
    os.remove("./test_bcf_api.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    # version negotiation (unauthenticated — the first call a BCF manager makes)
    ver = c.get("/bcf/versions").json()
    assert ver["versions"][0]["version_id"] == "2.1", ver
    auth = c.get("/bcf/2.1/auth").json()
    assert auth["oauth2_token_url"] == "/auth/login", auth

    pid = c.post("/projects", json={"name": "BCF Coord"}).json()["id"]

    # projects list in BCF shape
    projs = c.get("/bcf/2.1/projects").json()
    assert any(p["project_id"] == pid and p["name"] == "BCF Coord" for p in projs), projs

    # create a topic via the BCF-API payload
    made = c.post(f"/bcf/2.1/projects/{pid}/topics", json={
        "title": "Duct clashes beam", "topic_type": "Clash", "topic_status": "Open",
        "priority": "High", "labels": ["MEP", "L3"], "assigned_to": "structural@team",
        "description": "SD-2 duct runs through B-14"}).json()
    guid = made["guid"]
    assert made["topic_type"] == "Clash" and made["topic_status"] == "Open", made
    assert made["title"] == "Duct clashes beam" and made["assigned_to"] == "structural@team", made
    assert made["labels"] == ["MEP", "L3"] and made["creation_date"], made

    # it appears in the BCF topics list + the native topics list (same underlying row)
    topics = c.get(f"/bcf/2.1/projects/{pid}/topics").json()
    assert any(t["guid"] == guid and t["topic_type"] == "Clash" for t in topics), topics
    nat = c.get(f"/projects/{pid}/topics").json()
    assert any(t["guid"] == guid and t["type"] == "clash" and t["status"] == "open" for t in nat), nat

    # fetch the single topic by guid
    one = c.get(f"/bcf/2.1/projects/{pid}/topics/{guid}").json()
    assert one["guid"] == guid and one["description"] == "SD-2 duct runs through B-14", one
    assert c.get(f"/bcf/2.1/projects/{pid}/topics/NOPE").status_code == 404

    # comments round-trip in BCF shape
    cm = c.post(f"/bcf/2.1/projects/{pid}/topics/{guid}/comments",
                json={"comment": "Rerouting the duct above the beam."}).json()
    assert cm["comment"] == "Rerouting the duct above the beam." and cm["topic_guid"] == guid, cm
    comments = c.get(f"/bcf/2.1/projects/{pid}/topics/{guid}/comments").json()
    assert len(comments) == 1 and comments[0]["author"], comments
    # the same comment shows on the native comment route (shared Comment row)
    tid = next(t["id"] for t in nat if t["guid"] == guid)
    assert len(c.get(f"/projects/{pid}/topics/{tid}/comments").json()) == 1

    # validation: missing title / empty comment → 422
    assert c.post(f"/bcf/2.1/projects/{pid}/topics", json={"topic_type": "Issue"}).status_code == 422
    assert c.post(f"/bcf/2.1/projects/{pid}/topics/{guid}/comments", json={}).status_code == 422

    # --- viewpoints: camera + selection + snapshot round-trip in BCF shape -------------------------
    # a 1x1 transparent PNG, base64
    png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    vp = c.post(f"/bcf/2.1/projects/{pid}/topics/{guid}/viewpoints", json={
        "perspective_camera": {"camera_view_point": {"x": 10, "y": 0, "z": 5},
                               "camera_direction": {"x": -1, "y": 0, "z": 0},
                               "camera_up_vector": {"x": 0, "y": 0, "z": 1}, "field_of_view": 60},
        "components": {"selection": [{"ifc_guid": "abc123"}],
                       "visibility": {"default_visibility": True, "exceptions": [{"ifc_guid": "hidden1"}]}},
        "snapshot": {"snapshot_type": "png", "snapshot_data": png_b64}}).json()
    vguid = vp["guid"]
    assert vp["perspective_camera"]["camera_view_point"] == {"x": 10.0, "y": 0.0, "z": 5.0}, vp
    # direction is a unit vector pointing -x
    assert abs(vp["perspective_camera"]["camera_direction"]["x"] + 1.0) < 1e-6, vp
    assert vp["components"]["selection"] == [{"ifc_guid": "abc123"}], vp
    assert vp["components"]["visibility"]["exceptions"] == [{"ifc_guid": "hidden1"}], vp
    assert vp["snapshot"] == {"snapshot_type": "png"}, vp                 # data fetched separately

    vps = c.get(f"/bcf/2.1/projects/{pid}/topics/{guid}/viewpoints").json()
    assert len(vps) == 1 and vps[0]["guid"] == vguid, vps
    # it's the same row the native viewpoint route returns
    assert len(c.get(f"/projects/{pid}/topics/{tid}/viewpoints").json()) == 1
    # the snapshot streams as a real PNG
    snap = c.get(f"/bcf/2.1/projects/{pid}/topics/{guid}/viewpoints/{vguid}/snapshot")
    assert snap.status_code == 200 and snap.content[:8] == b"\x89PNG\r\n\x1a\n", snap.status_code

print("BCF-API OK - /bcf/versions negotiates 2.1 + /bcf/2.1/auth advertises the token URL; "
      "/bcf/2.1/projects lists accessible projects; a BCF-shape topic create maps topic_type/"
      "topic_status/labels/assigned_to onto the native Topic (Clash/Open, same row as /projects/"
      "{pid}/topics), fetch-by-guid 404s on a bad guid; comments round-trip in BCF shape and share the "
      "native Comment row; missing title / empty comment → 422. Viewpoints round-trip the "
      "perspective_camera (view_point + unit direction), components.selection/visibility.exceptions, "
      "and snapshot — same row as the native viewpoint route; the snapshot streams as a real PNG.")
