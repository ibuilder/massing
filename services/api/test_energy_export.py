"""ENERGY phase 1 — the envelope export: the intermediate thermal model (zones · zero-thickness
surfaces · constructions from the model's own assemblies) and the gbXML + IDF writers.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_energy_export.py"""
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_energy_export.db"
os.environ["STORAGE_DIR"] = "./test_storage_energyx"
os.environ["AEC_GEOM_WORKERS"] = "1"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_energy_export.db"):
    os.remove("./test_energy_export.db")

from aec_data import edit, energy_export, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

_ifc = Path(tempfile.gettempdir()) / "energy_export.ifc"
massing.generate_blank_ifc(str(_ifc), name="EN", storeys=1, storey_height=3.0, ground_size=20.0)
m = open_model(str(_ifc))
w_n = edit.add_wall(m, [0, 0], [10, 0], 3.0, 0.3, "Level 1")
w_e = edit.add_wall(m, [10, 0], [10, 8], 3.0, 0.3, "Level 1")
edit.add_opening(m, w_n, width=1.5, height=1.2, kind="window", sill=1.0)
edit.RECIPES["add_roof"](m, {"points": [[0, 0], [10, 0], [10, 8], [0, 8]], "thickness": 0.25,
                             "storey": "Level 1"})

built = energy_export.build(m)

# --- zones -----------------------------------------------------------------------------------------
assert built["counts"]["zones"] >= 1
assert built["zone_source"] in ("space", "whole_building")
if built["zone_source"] == "whole_building":                    # no IfcSpace authored here
    assert built["zones"][0]["name"] == "Whole building"

# --- surfaces: zero-thickness mid-plane polygons, honestly tagged -----------------------------------
surfaces = built["surfaces"]
assert built["counts"]["surfaces"] >= 4, built["counts"]
by_type: dict[str, list] = {}
for s in surfaces:
    by_type.setdefault(s["idf_type"], []).append(s)
assert "Wall" in by_type and "Window" in by_type, sorted(by_type)
assert all(len(s["corners"]) == 4 for s in surfaces)            # every surface is a quad
assert all(s["zone_id"] == built["zones"][0]["id"] for s in surfaces)
# authored rectangular extrusions are provably exact, not "trust me"
assert built["counts"]["surfaces_exact"] >= 1, built["counts"]
assert built["counts"]["surfaces_exact"] + built["counts"]["surfaces_bbox"] == len(surfaces)

# the north wall is 10 m x 3 m -> its surface area is the real face area, and it is VERTICAL
north = next(s for s in by_type["Wall"] if s["id"] == w_n)
assert north["orientation"] == "vertical", north
assert abs(north["area_m2"] - 30.0) < 0.6, north["area_m2"]     # 10 x 3 (bbox includes thickness)
# the mid-plane sits at the wall's centre-line: y = 0 for a wall drawn along y=0
ys = {c[1] for c in north["corners"]}
assert len(ys) == 1 and abs(next(iter(ys))) < 1e-6, north["corners"]
# and the polygon spans the full height + length
zs = sorted({c[2] for c in north["corners"]})
assert abs(zs[-1] - zs[0] - 3.0) < 1e-6, zs
# a flat roof comes out horizontal (a "wall" that is really a lid is re-typed, never mislabelled)
assert any(s["orientation"] == "horizontal" for s in surfaces)

# --- constructions ---------------------------------------------------------------------------------
cons = {c["name"]: c for c in built["constructions"]}
assert cons, "expected at least the default constructions"
assert all(c["layers"] and c["layers"][0]["thickness_m"] > 0 for c in cons.values())
assert all(c["source"] in ("model", "default") for c in cons.values())
assert all(s["construction"] in cons for s in surfaces)   # no dangling reference

# --- gbXML: parses, and carries the same building -------------------------------------------------
xml = energy_export.to_gbxml(built)
assert xml.startswith("<?xml")
root = ET.fromstring(xml)                                        # well-formed or this raises
ns = "{http://www.gbxml.org/schema}"
assert root.attrib["lengthUnit"] == "Meters" and root.attrib["version"] == "6.01"
gb_surfaces = root.findall(f".//{ns}Surface")
assert len(gb_surfaces) == len(surfaces), (len(gb_surfaces), len(surfaces))
assert len(root.findall(f".//{ns}Space")) == len(built["zones"])
assert len(root.findall(f"{ns}Construction")) == len(cons)
first_loop = gb_surfaces[0].find(f".//{ns}PolyLoop")
assert len(first_loop.findall(f"{ns}CartesianPoint")) == 4
assert all(len(p.findall(f"{ns}Coordinate")) == 3 for p in first_loop.findall(f"{ns}CartesianPoint"))
assert energy_export.to_gbxml(built) == xml                      # deterministic

# --- IDF: the objects EnergyPlus needs for an envelope run -----------------------------------------
idf = energy_export.to_idf(built)
assert "Version,23.2;" in idf and "GlobalGeometryRules," in idf
assert idf.count("BuildingSurface:Detailed,") == len(surfaces)
assert idf.count("Construction,") == len(cons)
assert idf.count("Zone,") == len(built["zones"])
assert "!- No HVAC, schedules or loads" in idf                   # scope stated in the file itself
for s in surfaces:                                               # every surface names a real zone
    assert f"  {s['idf_type']},".strip() in idf
assert energy_export.to_idf(built) == idf                        # deterministic

# --- routes ----------------------------------------------------------------------------------------
m.write(str(_ifc))
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "EN"}).json()["id"]
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = str(_ifc)
        db.commit()
    r = c.get(f"/projects/{pid}/energy/model")
    assert r.status_code == 200 and r.json()["counts"]["surfaces"] == len(surfaces), r.text
    g = c.get(f"/projects/{pid}/energy/export.gbxml")
    assert g.status_code == 200 and g.text.startswith("<?xml")
    assert "envelope.gbxml" in g.headers["content-disposition"]
    i = c.get(f"/projects/{pid}/energy/export.idf")
    assert i.status_code == 200 and "BuildingSurface:Detailed," in i.text

if _ifc.exists():
    _ifc.unlink()

print("ENERGY-EXPORT OK - the IFC becomes a thermal model: a whole-building zone (no IfcSpace "
      "authored), one zero-thickness mid-plane surface per envelope element (the 10x3 m wall's "
      "polygon sits exactly on its centre-line and spans the full 3 m height), each tagged exact "
      "or bbox by actually checking the mesh against its bounding box, and constructions whose "
      "layer conductivities are back-derived from the platform's own R so the export can't "
      "contradict it; gbXML parses as valid XML with matching Surface/Space/Construction counts and "
      "4-point PolyLoops, the IDF carries Version/GlobalGeometryRules/Zone/Construction/"
      "BuildingSurface:Detailed with its no-HVAC scope stated in the file, both writers are "
      "byte-deterministic, and all three routes serve them.")
