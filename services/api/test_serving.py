"""HTTP range serving test. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_serving.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./serve_test.db"
os.environ["STORAGE_DIR"] = "./test_storage"
for f in ("./serve_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api import storage  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Tiles"}).json()["id"]
    storage.put(f"{pid}/model.frag", bytes(range(256)))  # 256 known bytes

    # full request: 200 + Accept-Ranges
    full = c.get(f"/projects/{pid}/model.frag")
    assert full.status_code == 200, full.status_code
    assert full.headers["accept-ranges"] == "bytes"
    assert len(full.content) == 256

    # range request: 206 + Content-Range + exact slice
    r = c.get(f"/projects/{pid}/model.frag", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206, r.status_code
    assert r.headers["content-range"] == "bytes 10-19/256", r.headers.get("content-range")
    assert r.content == bytes(range(10, 20)), r.content

    # open-ended range
    r2 = c.get(f"/projects/{pid}/model.frag", headers={"Range": "bytes=250-"})
    assert r2.status_code == 206 and r2.content == bytes(range(250, 256))

    # unsatisfiable
    assert c.get(f"/projects/{pid}/model.frag", headers={"Range": "bytes=999-"}).status_code == 416

    print("SERVING OK — 200 full / 206 ranged / 416 unsatisfiable; Accept-Ranges set")
