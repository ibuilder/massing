"""Smoke test for the API (M3 + properties). Run with the api venv:
   PYTHONPATH=src ./.venv/Scripts/python.exe test_api.py
"""
import io
import os
import zipfile

os.environ["DATABASE_URL"] = "sqlite:///./test_aec.db"
os.environ["STORAGE_DIR"] = "./test_storage"

for f in ("./test_aec.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402

# context manager runs the lifespan handler -> init_db() creates tables
with TestClient(app) as c:
    assert c.get("/health").json() == {"status": "ok"}

    # 1. project (with working origin / georeferencing offset)
    pid = c.post("/projects", json={"name": "School", "origin": {"e": 1000, "n": 2000, "z": 0}}).json()["id"]

    # 2. pin an RFI to an element (M3)
    topic = c.post(f"/projects/{pid}/topics", json={
        "type": "rfi", "title": "Beam clash at grid C3", "author": "alice",
        "status": "open", "priority": "high",
        "anchor": {"x": 1.2, "y": 3.4, "z": 5.6},
        "element_guids": ["1WrzGm1SD2ev45B_OWQ39B"],
    }).json()
    tid = topic["id"]
    assert topic["type"] == "rfi" and topic["anchor"]["x"] == 1.2

    # 3. viewpoint (camera + components + visibility) — restorable by the viewer
    vp = c.post(f"/projects/{pid}/topics/{tid}/viewpoints", json={
        "camera": {"type": "perspective", "position": {"x": 10, "y": 8, "z": 12},
                   "target": {"x": 0, "y": 0, "z": 0}, "fov": 60},
        "components": ["1WrzGm1SD2ev45B_OWQ39B"],
        "visibility": {"default_visibility": True, "exceptions": []},
    }).json()
    assert vp["camera"]["fov"] == 60

    # 4. comment
    c.post(f"/projects/{pid}/topics/{tid}/comments", json={"author": "bob", "text": "Confirmed, RFI raised."})

    # 5. attachment (a drawing)
    files = {"file": ("sheet-A101.txt", b"fake drawing bytes", "text/plain")}
    att = c.post(f"/projects/{pid}/topics/{tid}/attachments", data={"kind": "drawing"}, files=files).json()
    dl = c.get(f"/attachments/{att['id']}/download")
    assert dl.content == b"fake drawing bytes"

    # 6. pins overlay
    pins = c.get(f"/projects/{pid}/pins").json()
    assert len(pins) == 1 and pins[0]["id"] == tid

    # 7. RFI workflow transition open -> answered
    patched = c.patch(f"/projects/{pid}/topics/{tid}", json={"status": "answered"}).json()
    assert patched["status"] == "answered"

    # 8. BCF export -> valid zip with markup + viewpoint
    raw = c.get(f"/projects/{pid}/bcf/export").content
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist()
        assert any(n.endswith("markup.bcf") for n in names), names
        assert any(n.endswith(".bcfv") for n in names), names

    # 9. BCF import round-trip into a new project
    pid2 = c.post("/projects", json={"name": "Imported"}).json()["id"]
    imp = c.post(f"/projects/{pid2}/bcf/import", files={"file": ("x.bcfzip", raw, "application/zip")}).json()
    assert imp["imported"] == 1, imp
    t2 = c.get(f"/projects/{pid2}/topics").json()
    assert t2[0]["title"] == "Beam clash at grid C3"

    # 10. properties index upload + lookup by GUID
    #     fixture lives in the repo (tests/fixtures); fall back to the local samples/ dir
    _fx = "tests/fixtures/school_str.props.json"
    if not os.path.exists(_fx):
        _fx = "../../samples/school_str.props.json"
    with open(_fx, "rb") as fh:
        up = c.post(f"/projects/{pid}/properties/index", files={"file": ("props.json", fh, "application/json")}).json()
    assert up["loaded"] > 1000, up
    el = c.get(f"/projects/{pid}/elements/1WrzGm1SD2ev45B_OWQ39B").json()
    assert el["ifc_class"] == "IfcBeam", el
    beams = c.get(f"/projects/{pid}/elements", params={"ifc_class": "IfcBeam", "limit": 5}).json()
    assert all(e["ifc_class"] == "IfcBeam" for e in beams)

    print("API SMOKE OK")
    print(f"  project={pid}  topic={tid}  loaded_elements={up['loaded']}")
    print(f"  bcf files: {names}")
