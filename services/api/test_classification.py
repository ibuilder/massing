"""Regional classification standards + GAEB X83 export.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_classification.py"""
import os
import tempfile
import xml.etree.ElementTree as ET

os.environ["DATABASE_URL"] = "sqlite:///./test_classif.db"
os.environ["STORAGE_DIR"] = "./test_storage_classif"
os.environ["IFC_DIR"] = "./test_ifc_classif"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_classif.db",):
    if os.path.exists(f):
        os.remove(f)

import sys                                                  # noqa: E402
from pathlib import Path                                    # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from fastapi.testclient import TestClient                   # noqa: E402
from aec_api.main import app                                # noqa: E402
from aec_api import classification as cls                   # noqa: E402
from aec_data import massing                                # noqa: E402

# --- unit: classify + GAEB rendering (no IFC needed) -------------------------
assert {s["id"] for s in cls.systems()} == {"masterformat", "din276", "nrm1"}
assert cls.classify("IfcWall", "din276")[0] == "331"
assert cls.classify("IfcColumn", "nrm1")[0] == "2.1"
assert cls.classify("IfcSlab", "masterformat")[0].startswith("03")
assert cls.classify("IfcMadeUp", "din276") == cls.CLASSIFICATIONS["din276"]["default"]   # fallback

# --- unit: the unified discipline tree (colors + IFC-class coverage) ---------
from aec_data import disciplines as _disc                               # noqa: E402  (canonical color source)
assert cls.discipline_color("F") == _disc.DISCIPLINE_COLORS["F"]        # fire = red family
assert cls.discipline_color("FA") == _disc.SERIES_COLORS["FA"]          # fire alarm reads apart
assert cls.discipline_color("Ad") == _disc.DISCIPLINE_COLORS["A"]       # 2-letter designator folds to level-1
assert cls.discipline_color("zz") == "#8A8F98"                          # unknown -> General grey
# MEP/fire/telecom classes the MasterFormat map doesn't enumerate must still classify to a discipline
assert cls.discipline_of_ifc_class("IfcSprinkler") == "F"
assert cls.discipline_of_ifc_class("IfcAlarm") == "E"                   # electronic safety -> Electrical
assert cls.discipline_of_ifc_class("IfcCommunicationsAppliance") == "T"
assert cls.discipline_of_ifc_class("IfcTransformer") == "E"
assert cls.discipline_of_ifc_class("IfcPump") == "P"
assert cls.discipline_of_ifc_class("IfcCoolingTower") == "M"
assert cls.discipline_of_ifc_class("IfcTransportElement") == "Q"
assert cls.discipline_of_ifc_class("IfcReinforcingBar") == "S"        # rebar rolls up to Structural
tree = cls.discipline_tree()
codes = {d["code"] for d in tree["disciplines"]}
assert codes == {d["code"] for d in cls.DISCIPLINES}, codes
assert all(d["color"].startswith("#") for d in tree["disciplines"])
assert tree["colors"]["P"] == cls.discipline_color("P")
# every discipline's ifc_classes actually roll up to it (no cross-contamination)
for d in tree["disciplines"]:
    for icl in d["ifc_classes"]:
        assert cls.discipline_of_ifc_class(icl) == d["code"], (icl, d["code"])
fire = next(d for d in tree["disciplines"] if d["code"] == "F")
assert "IfcSprinkler" in fire["ifc_classes"]
assert tree["ifc_class_discipline"]["IfcBoiler"] == "M"
# the FA series is carried distinctly (fire alarm documented apart from the E series)
assert any(s["code"] == "FA" for s in tree["series"])

sample = [{"ifc_class": "IfcWall", "unit": "m²", "quantity": 120.5, "rate": 85.0},
          {"ifc_class": "IfcColumn", "unit": "ea", "count": 8, "quantity": 8, "rate": 1200.0}]
xml = cls.gaeb_x83("Demo Tower", sample, system="din276")
root = ET.fromstring(xml)                                   # must be well-formed
ns = "{http://www.gaeb.de/GAEB_DA_XML/DA86/3.2}"
assert root.tag == f"{ns}GAEB", root.tag
assert root.find(f"{ns}Award/{ns}DP").text == "83"
items = root.findall(f".//{ns}Item")
assert len(items) == 2, f"expected 2 items, got {len(items)}"
assert items[0].find(f"{ns}Qty").text == "120.500" and items[0].find(f"{ns}QU").text == "m2"
assert "331" in "".join(items[0].itertext())               # DIN code in the short text

# --- integration: endpoints --------------------------------------------------
with TestClient(app) as c:
    assert {s["id"] for s in c.get("/classifications").json()["systems"]} == {"masterformat", "din276", "nrm1"}

    ref = c.get("/reference/disciplines").json()
    assert all("color" in d for d in ref["disciplines"]), "disciplines must carry a color"
    assert "tree" in ref and ref["tree"]["colors"]["F"] == cls.discipline_color("F")
    assert ref["tree"]["ifc_class_discipline"]["IfcSprinkler"] == "F"

    pid = c.post("/projects", json={"name": "Classif Tower"}).json()["id"]
    # no source IFC yet → GAEB export should 4xx, not 500
    assert c.get(f"/projects/{pid}/estimate/gaeb.x83").status_code >= 400

    # give it a real IFC (geometry) without the heavy publish step
    metrics = massing.compute_massing({"lot_width": 24, "lot_depth": 16, "far": 1.5, "floor_to_floor": 3.5, "height_limit": 11})
    ifc = Path(tempfile.gettempdir()) / "classif_model.ifc"
    massing.generate_ifc(metrics, str(ifc), name="Classif")
    r = c.post(f"/projects/{pid}/source-ifc?publish=false",
               files={"file": ("model.ifc", ifc.read_bytes(), "application/octet-stream")})
    assert r.status_code == 200, r.text[:160]

    for sysid in ("din276", "nrm1", "masterformat"):
        g = c.get(f"/projects/{pid}/estimate/gaeb.x83?system={sysid}")
        assert g.status_code == 200, f"{sysid}: {g.status_code} {g.text[:160]}"
        assert g.headers["content-type"].startswith("application/xml")
        gx = ET.fromstring(g.text)                           # well-formed GAEB
        assert gx.find(f"{ns}Award/{ns}DP").text == "83"
        assert len(gx.findall(f".//{ns}Item")) >= 1, f"{sysid}: no items"

print("CLASSIFICATION OK - 3 systems; GAEB X83 well-formed; estimate->GAEB export verified for "
      "din276 / nrm1 / masterformat; 409 without a source IFC")
