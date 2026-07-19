"""Discipline-model registry + federated (cross-model) clash.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_federated_clash.py"""
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_fed_clash.db"
os.environ["STORAGE_DIR"] = "./test_storage_fed"   # matches .gitignore test_storage*/
os.environ["IFC_DIR"] = "./test_ifc_fed"           # matches .gitignore test_ifc*/
os.environ.pop("AEC_RBAC", None)
for f in ("./test_fed_clash.db",):
    if os.path.exists(f):
        os.remove(f)

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_data import massing  # noqa: E402

# a small real IFC with geometry (columns/slabs) — two copies overlap → federated clashes
metrics = massing.compute_massing({"lot_width": 30, "lot_depth": 20, "far": 2.0,
                                   "floor_to_floor": 3.5, "height_limit": 14})
_ifc = Path(tempfile.gettempdir()) / "fed_test_model.ifc"
massing.generate_ifc(metrics, str(_ifc), name="Fed Test")
IFC_BYTES = _ifc.read_bytes()
assert IFC_BYTES[:4] == b"ISO-"[:4] or b"IFC" in IFC_BYTES[:200], "generated IFC looks wrong"


def add_model(c, pid, discipline):
    r = c.post(f"/projects/{pid}/models",
               files={"file": (f"{discipline}.ifc", IFC_BYTES, "application/octet-stream")},
               data={"discipline": discipline})
    assert r.status_code == 201, f"add {discipline}: {r.status_code} {r.text[:160]}"
    return r.json()["id"]


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Coordination"}).json()["id"]

    # <2 models → 409
    r = c.post(f"/projects/{pid}/clash/federated")
    assert r.status_code == 409, f"expected 409 with no models, got {r.status_code}"

    mid_str = add_model(c, pid, "STR")
    add_model(c, pid, "MEP")

    models = c.get(f"/projects/{pid}/models").json()
    assert len(models) == 2 and {m["discipline"] for m in models} == {"STR", "MEP"}, models

    # federated clash auto-builds the disciplines map from the registry; identical overlapping
    # geometry across the two models must produce cross-model clashes (intra-model excluded)
    r = c.post(f"/projects/{pid}/clash/federated?create_topics=true&limit=50")
    assert r.status_code == 200, f"federated clash: {r.status_code} {r.text[:200]}"
    res = r.json()
    assert set(res["disciplines"]) == {"STR", "MEP"}, res["disciplines"]
    assert isinstance(res["count"], int) and res["count"] > 0, f"expected cross-model clashes, got {res['count']}"
    assert res["created_topics"] > 0, res
    # clashes carry the originating model labels
    assert all("a_model" in cl and "b_model" in cl for cl in res["clashes"][:3]), res["clashes"][:1]

    # the clash topics became BCF topics (→ Issues / pins)
    topics = c.get(f"/projects/{pid}/pins").json()
    assert any(t.get("type") == "clash" for t in topics), "expected clash topics among pins"

    # delete one discipline → back under the 2-model minimum → 409
    assert c.delete(f"/projects/{pid}/models/{mid_str}").json()["deleted"] is True
    assert len(c.get(f"/projects/{pid}/models").json()) == 1
    assert c.post(f"/projects/{pid}/clash/federated").status_code == 409

# --- QUERY-DSL wiring (Sprint 1): detect() accepts explicit GUID sets per side ---------------------
from aec_data import clash  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

_m = open_model(str(_ifc))
base = clash.detect(_m, narrow=False)                        # broad-phase: the model self-overlaps
assert base, "the massing model must self-overlap for the filter test"
one_guid = base[0]["a_guid"]
scoped = clash.detect(_m, narrow=False, guids_a={one_guid})
assert scoped and all(x["a_guid"] == one_guid for x in scoped), "guids_a scopes side A to the set"
assert len(scoped) < len(base), "a one-element scope must shrink the result"
assert clash.detect(_m, narrow=False, guids_a=set()) == [], "an empty GUID set matches nothing"

print(f"FEDERATED CLASH OK — {res['count']} cross-model clashes (STR×MEP), "
      f"{res['created_topics']} BCF topics; registry append/list/delete + auto-build verified; "
      f"QUERY-DSL guid scoping: {len(scoped)}/{len(base)} clashes for one scoped element, empty set → none")
