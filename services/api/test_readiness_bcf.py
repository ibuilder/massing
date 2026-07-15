"""RFI-0: promote the decision-readiness gaps to BCF topics (one per gap, GUID-anchored, priority by
severity), idempotently. The audit itself is covered by test_rfi_readiness; this covers the /bcf endpoint.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_readiness_bcf.py"""
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_readiness_bcf.db"
os.environ["STORAGE_DIR"] = "./test_storage_rbcf"   # matches .gitignore test_storage*/
os.environ["IFC_DIR"] = "./test_ifc_rbcf"           # matches .gitignore test_ifc*/
os.environ.pop("AEC_RBAC", None)
for f in ("./test_readiness_bcf.db",):
    if os.path.exists(f):
        os.remove(f)

import sys                                                   # noqa: E402
from pathlib import Path                                     # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from fastapi.testclient import TestClient                    # noqa: E402
from aec_api.main import app                                 # noqa: E402
from aec_data import edit, massing                           # noqa: E402
from aec_data.ifc_loader import open_model                   # noqa: E402

# a gap-y model: spaces without OccupancyType, a below-min egress door, an un-substantiated rated wall
_ifc = Path(tempfile.gettempdir()) / "rbcf_test_model.ifc"
massing.generate_blank_ifc(str(_ifc), name="RFI BCF Test", storeys=1, storey_height=3.0, ground_size=30.0)
m = open_model(str(_ifc))
st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_spaces(m, rooms_per_storey=3, ceiling_height=3.0)
w = edit.add_wall(m, [0, 0], [8, 0], 3.0, 0.2, st)
edit.add_opening(m, w, width=0.7, height=2.1, kind="door")        # 0.7 m < 32 in → egress gap
rw = edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)
edit.set_element_pset(m, rw, "Pset_WallCommon", "FireRating", "2HR")
m.write(str(_ifc))
IFC_BYTES = _ifc.read_bytes()

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Readiness"}).json()["id"]

    # no source IFC yet → 409
    assert c.post(f"/projects/{pid}/rfi/readiness/bcf").status_code == 409

    # upload the gap-y model as the source (skip the converter publish)
    r = c.post(f"/projects/{pid}/source-ifc?publish=false",
               files={"file": ("source.ifc", IFC_BYTES, "application/octet-stream")})
    assert r.status_code == 200, f"upload: {r.status_code} {r.text[:160]}"

    # the audit finds gaps
    ra = c.get(f"/projects/{pid}/rfi/readiness").json()
    assert ra["total_gaps"] >= 1 and ra["ready"] is False, ra

    # promote them to BCF topics
    rb = c.post(f"/projects/{pid}/rfi/readiness/bcf")
    assert rb.status_code == 200, f"bcf: {rb.status_code} {rb.text[:200]}"
    body = rb.json()
    assert body["created"] == ra["total_gaps"], (body["created"], ra["total_gaps"])
    assert body["created"] >= 1 and body["ready"] is False, body

    # they land as BCF topics of type "readiness" (visible in pins/Issues), labelled by category
    pins = c.get(f"/projects/{pid}/pins").json()
    readiness = [t for t in pins if t.get("type") == "readiness"]
    assert len(readiness) == body["created"], (len(readiness), body["created"])
    assert all("readiness" in (t.get("labels") or []) for t in readiness), readiness[:1]
    assert any(t.get("priority") == "high" for t in readiness), "a high-severity gap → high-priority topic"

    # idempotent: re-running clears the prior readiness topics, doesn't pile up duplicates
    rb2 = c.post(f"/projects/{pid}/rfi/readiness/bcf").json()
    pins2 = c.get(f"/projects/{pid}/pins").json()
    assert rb2["created"] == body["created"], (rb2["created"], body["created"])
    assert len([t for t in pins2 if t.get("type") == "readiness"]) == body["created"], "no duplicate piling"

print(f"READINESS->BCF OK - {body['created']} decision-readiness gaps promoted to type=readiness BCF topics "
      "(GUID-anchored, category-labelled, high-severity->high-priority); 409 without a source IFC; "
      "re-running is idempotent (clears prior readiness topics, no duplicate piling).")
