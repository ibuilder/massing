"""INTEROP-RT — the round-trip fidelity gauntlet: author → serialize → reparse → compare
(GUID/class/name/containment/type/psets), the /model/roundtrip route, and the CLI subcommand.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_roundtrip.py"""
import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_roundtrip.db"
os.environ["STORAGE_DIR"] = "./test_storage_rt"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_roundtrip.db"):
    os.remove("./test_roundtrip.db")

import ifcopenshell.api  # noqa: E402

from aec_data import edit, massing, roundtrip  # noqa: E402
from aec_data.cli import main as cli_main  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

_ifc = Path(tempfile.gettempdir()) / "roundtrip_gauntlet.ifc"
massing.generate_blank_ifc(str(_ifc), name="RT", storeys=2, storey_height=3.0, ground_size=20.0)
m = open_model(str(_ifc))
w = edit.add_wall(m, [0, 0], [8, 0], 3.0, 0.2, "Level 1")
edit.add_opening(m, w, width=0.9, height=2.1, kind="door")
desk = edit.RECIPES["add_family"](m, {"family": "desk", "type_name": "1600 × 800", "storey": "Level 1"})
ps = ifcopenshell.api.run("pset.add_pset", m, product=m.by_guid(w), name="Pset_Custom")
ifcopenshell.api.run("pset.edit_pset", m, pset=ps, properties={"FireRating": "2HR", "Load": 4.5})

# --- the gauntlet: everything survives serialize → reparse -----------------------------------------
report = roundtrip.roundtrip(m)
assert report["fidelity_ok"], report
assert report["element_count"] >= 10 and report["counts"] == {"missing": 0, "added": 0, "changed": 0}

# --- the compare surfaces real drift, both ways ----------------------------------------------------
before = roundtrip.snapshot(m)
mutated = dict(before)
lost = mutated.pop(desk)                                     # an element vanished
diff = roundtrip.compare(before, mutated)
assert not diff["fidelity_ok"] and diff["missing"] == [desk]
tweaked = {**before, w: {**before[w], "psets": {**before[w]["psets"],
                                                "Pset_Custom": {"FireRating": "1HR", "Load": 4.5}}}}
diff2 = roundtrip.compare(before, tweaked)
assert diff2["counts"]["changed"] == 1 and diff2["changed"][0]["guid"] == w
assert "Pset_Custom" in diff2["changed"][0]["pset_diff"]["changed_psets"]
assert roundtrip.compare(mutated, before)["added"] == [desk]  # reported both ways, never netted

# --- the CLI + the route ---------------------------------------------------------------------------
m.write(str(_ifc))
assert cli_main(["roundtrip", str(_ifc)]) == 0
assert cli_main(["roundtrip", str(_ifc), "--gate"]) == 0     # lossless → gate passes

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "RT"}).json()["id"]
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = str(_ifc)
        db.commit()
    r = c.get(f"/projects/{pid}/model/roundtrip")
    assert r.status_code == 200 and r.json()["fidelity_ok"], r.text

if _ifc.exists():
    _ifc.unlink()

print("ROUNDTRIP OK - the authored model (2 storeys + wall + hosted door + cataloged desk + a "
      "custom pset) survives serialize->reparse byte-honestly (fidelity_ok, 0/0/0); the compare "
      "flags a removed element as missing one way and added the other (never netted) and pins a "
      "pset edit to the exact changed pset; `massing roundtrip --gate` exits 0 on lossless and "
      "GET /model/roundtrip serves the same verdict.")
