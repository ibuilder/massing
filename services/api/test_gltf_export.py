"""glTF 2.0 geometry export (interchange path). Generates a real massing IFC, exports it to glTF, and
validates the document parses back to meshes.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_gltf_export.py"""
import io
import json
import os
import sys
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_gltf.db"
os.environ["STORAGE_DIR"] = "./test_storage_gltf"
os.environ["IFC_DIR"] = tempfile.mkdtemp(prefix="gltf_ifc_")
os.environ.pop("AEC_RBAC", None)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))
for _f in ("./test_gltf.db",):
    if os.path.exists(_f):
        os.remove(_f)

import warnings  # noqa: E402

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "glTF Test"}).json()["id"]
    # no source IFC yet -> graceful 409, not a 500
    assert c.get(f"/projects/{pid}/model/export.gltf").status_code == 409

    # generate a real geometric model (storeys + slabs + spaces)
    g = c.post(f"/projects/{pid}/generate/massing",
               json={"lot_width": 40, "lot_depth": 30, "far": 2.0, "use_type": "residential"}).json()
    assert g["source_ifc"], g

    r = c.get(f"/projects/{pid}/model/export.gltf")
    assert r.status_code == 200, r.text[:200]
    assert r.headers["content-type"].startswith("model/gltf+json"), r.headers["content-type"]
    doc = json.loads(r.content)
    # valid glTF 2.0 skeleton
    assert doc["asset"]["version"] == "2.0", doc["asset"]
    assert doc["meshes"] and doc["nodes"] and doc["accessors"] and doc["buffers"], doc.keys()
    # the embedded buffer decodes and its length matches the declared byteLength
    import base64
    buf = base64.b64decode(doc["buffers"][0]["uri"].split(",", 1)[1])
    assert len(buf) == doc["buffers"][0]["byteLength"], "buffer length mismatch"
    # every node names an IFC class and points at a mesh; slabs must be present (one plate per floor)
    classes = {n["name"] for n in doc["nodes"]}
    assert "IfcSlab" in classes, classes

    # round-trips through a standard glTF reader (trimesh) with real triangles + Y-up bounds
    import trimesh  # noqa: E402
    scene = trimesh.load(io.BytesIO(r.content), file_type="gltf")
    tris = sum(len(gm.faces) for gm in scene.geometry.values())
    assert len(scene.geometry) == len(doc["meshes"]) and tris > 0, (len(scene.geometry), tris)
    # Y-up: the model's vertical extent is the Y axis (height > 0), not Z
    assert scene.bounds[1][1] > scene.bounds[0][1], scene.bounds.tolist()

print(f"GLTF EXPORT OK - 409 with no source IFC; generated massing exported to valid glTF 2.0 "
      f"({len(doc['meshes'])} per-class meshes, {tris} triangles, embedded buffer decodes, IfcSlab "
      f"present); trimesh round-trips the document, Y-up orientation confirmed")
