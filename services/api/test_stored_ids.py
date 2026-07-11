"""Validate against a *pinned* project IDS: a project can store the information-delivery
specification its model must satisfy (EIR/BEP-mandated), then `/validate` runs against it with no
re-upload. Precedence: an uploaded .ids wins; else `ids=auto` uses the pinned one; `ids=stored`
forces it (404 if none); `ids=default` forces the built-in QA specs.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_stored_ids.py"""
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_stored_ids.db"
os.environ["STORAGE_DIR"] = "./test_storage_stored_ids"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_stored_ids.db",):
    if os.path.exists(_f):
        os.remove(_f)

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import ids_authoring as ia  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_data import massing  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "IDS Tower"}).json()["id"]

    # give the project a real source IFC (needed before /validate) — light, no publish/fragments
    metrics = massing.compute_massing({"lot_width": 24, "lot_depth": 16, "far": 1.5,
                                       "floor_to_floor": 3.5, "height_limit": 11})
    ifc = Path(tempfile.gettempdir()) / "ids_model.ifc"
    massing.generate_ifc(metrics, str(ifc), name="IDS")
    up = c.post(f"/projects/{pid}/source-ifc?publish=false",
                files={"file": ("model.ifc", ifc.read_bytes(), "application/octet-stream")})
    assert up.status_code == 200, up.text[:160]

    # nothing pinned yet
    assert c.get(f"/projects/{pid}/ids").json() == {"exists": False, "bytes": 0}
    assert c.get(f"/projects/{pid}/ids", params={"download": True}).status_code == 404
    # forcing the stored IDS when none exists is a clean 404 (not the built-in fallback)
    assert c.post(f"/projects/{pid}/validate", params={"ids": "stored"}).status_code == 404

    # pin a real, ifctester-valid IDS (generated from a use-case template)
    ids_xml = ia.build_from_use_case("fire_life_safety", author="GC", purpose="handover")
    assert ids_xml.startswith("<ids"), ids_xml[:60]
    put = c.put(f"/projects/{pid}/ids",
                files={"file": ("project.ids", ids_xml.encode(), "application/xml")})
    assert put.status_code == 200 and put.json()["stored"] is True and put.json()["bytes"] > 0, put.text

    # status + round-trip download
    st = c.get(f"/projects/{pid}/ids").json()
    assert st["exists"] is True and st["bytes"] == len(ids_xml.encode()), st
    dl = c.get(f"/projects/{pid}/ids", params={"download": True})
    assert dl.status_code == 200 and dl.content == ids_xml.encode(), dl.status_code

    # empty IDS is rejected
    assert c.put(f"/projects/{pid}/ids",
                 files={"file": ("e.ids", b"   ", "application/xml")}).status_code == 400

    # validate against the PINNED IDS (engine runs; we only assert it ran cleanly against our specs)
    res = c.post(f"/projects/{pid}/validate", params={"ids": "stored"})
    assert res.status_code == 200, res.text[:200]
    body = res.json()
    assert isinstance(body, dict) and body, body
    # auto picks up the pinned IDS too (same result surface)
    assert c.post(f"/projects/{pid}/validate", params={"ids": "auto"}).status_code == 200
    # and a BCF punch list of the audit round-trips
    bcf = c.post(f"/projects/{pid}/validate", params={"ids": "stored", "format": "bcf"})
    assert bcf.status_code == 200 and bcf.content[:2] == b"PK", "bcfzip is a zip"

    # unpin → back to not-found; deleting again is a no-op
    assert c.request("DELETE", f"/projects/{pid}/ids").json() == {"deleted": True}
    assert c.get(f"/projects/{pid}/ids").json()["exists"] is False
    assert c.request("DELETE", f"/projects/{pid}/ids").json() == {"deleted": False}

print("STORED-IDS OK - PUT/GET/GET?download/DELETE lifecycle; empty rejected (400); validate "
      "precedence: stored-with-none=404, pinned IDS drives ids=stored/auto (json + bcfzip); "
      "delete is idempotent")
