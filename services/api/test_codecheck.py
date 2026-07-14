"""Code-compliance assistant — offline IBC rules path (no ANTHROPIC_API_KEY).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_codecheck.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_codecheck.db"
os.environ["STORAGE_DIR"] = "./test_storage_codecheck"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("ANTHROPIC_API_KEY", None)          # force offline rules
for _f in ("./test_codecheck.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import codecheck  # noqa: E402
from aec_api.main import app  # noqa: E402

# assembly + large area + multistory -> occupancy A, sprinklers, assembly egress, multistory rules
r = codecheck.check("A 4-story restaurant and assembly hall, 20,000 sf, 400 occupants")
assert r["source"] == "rules", r
assert r["detected"]["occupancy"]["group"] == "A", r["detected"]
assert r["detected"]["area_sf"] == 20000 and r["detected"]["stories"] == 4, r["detected"]
titles = " ".join(t["title"].lower() for t in r["topics"])
assert "occupancy classification" in titles and "egress width" in titles and "accessibility" in titles, titles
assert "sprinkler" in titles, "large assembly should trigger sprinklers"
assert "assembly egress" in titles, "A occupancy should trigger panic hardware/aisles"
assert any("elevator" in t["requirement"].lower() or "fire-resistance" in t["title"].lower() for t in r["topics"]), r["topics"]
# every topic cites a real code + section (no fabricated blanks)
assert all(t["code"] and t["section"] and t["requirement"] for t in r["topics"]), r["topics"]

# small office -> business occupancy, no sprinkler/assembly triggers, still the universal checklist
r2 = codecheck.check("Single-story 2,000 sf professional office")
assert r2["detected"]["occupancy"]["group"] == "B", r2["detected"]
t2 = " ".join(t["title"].lower() for t in r2["topics"])
assert "sprinkler" not in t2 and "assembly egress" not in t2, t2
assert "occupant load" in t2, t2

# empty -> no fabrication
assert codecheck.check("")["source"] == "empty"

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    resp = c.post(f"/projects/{pid}/codecheck", json={"description": "5-story apartment building, 60,000 sf"})
    assert resp.status_code == 200, resp.text[:200]
    j = resp.json()
    assert j["detected"]["occupancy"]["group"] == "R" and j["detected"]["stories"] == 5, j["detected"]
    assert any("dwelling" in t["title"].lower() for t in j["topics"]), j["topics"]

# --- W9-2: computed occupancy load + egress capacity over a hand-built property index ----------------
import math  # noqa: E402

M2 = 1 / 10.7639   # ft² -> m² (IFC quantities store area in m²)
INDEX = {
    "office": {"ifc_class": "IfcSpace", "name": "Open Office 101",
               "qtos": {"Qto_SpaceBaseQuantities": {"NetFloorArea": 3000 * M2}}},          # 3000 ft² Business
    "conf": {"ifc_class": "IfcSpace", "name": "Conference",
             "psets": {"Pset_SpaceOccupancyRequirements": {"OccupancyType": "Assembly - conference"}},
             "qtos": {"Qto_SpaceBaseQuantities": {"NetFloorArea": 600 * M2}}},              # 600 ft² Assembly
    "shaft": {"ifc_class": "IfcSpace", "name": "Shaft"},                                     # no area
    "door_ok": {"ifc_class": "IfcDoor", "name": "D1", "psets": {"Pset_DoorCommon": {"Width": 0.9}}},
    "door_narrow": {"ifc_class": "IfcDoor", "name": "D2", "psets": {"Pset_DoorCommon": {"Width": 0.7}}},
    "w": {"ifc_class": "IfcWall", "name": "W"},
}
eg = codecheck.egress_analysis(INDEX)
office = next(s for s in eg["spaces"] if s["name"] == "Open Office 101")
conf = next(s for s in eg["spaces"] if s["name"] == "Conference")
assert office["occupancy"] == "Business" and office["load"] == 20, office        # 3000/150
assert conf["occupancy"].startswith("Assembly") and conf["load"] == 40, conf     # 600/15
assert eg["building"]["occupant_load"] == 60, eg["building"]
assert eg["building"]["spaces"] == 2 and eg["building"]["spaces_missing_area"] == 1, eg["building"]
assert eg["egress"]["required_width_in"] == 9.0, eg["egress"]                     # 60 × 0.15
assert eg["egress"]["adequate"] is True, eg["egress"]                            # 35.4 in provided ≥ 9.0
assert eg["doors"]["checked"] == 2 and eg["doors"]["below_min_32in"] == 1, eg["doors"]
assert eg["doors"]["fail_guids"] == ["door_narrow"], eg["doors"]
assert any("1004.5" in c for c in eg["citations"]) and eg["disclaimer"]
big = codecheck.egress_analysis({"b": {"ifc_class": "IfcSpace", "name": "Big",
                                       "qtos": {"Qto_SpaceBaseQuantities": {"NetFloorArea": 10000 * M2}}}})
assert big["spaces"][0]["load"] == math.ceil(10000 / 150) == 67 and big["spaces"][0]["needs_2_exits"] is True

print("CODECHECK OK - detects occupancy/area/stories; assembly+large+multistory -> sprinklers + assembly "
      "egress + elevator/fire-resistance; small office omits those; R triggers dwelling separation; all "
      "topics carry a real code+section; empty -> no fabrication; endpoint 200. "
      "W9-2 egress: office 3000/150=20 + conference 600/15=40 -> building 60 occ; required egress 9.0 in "
      "vs 35.4 in provided (adequate); 28 in door flagged below 32 in min; >49 occ forces two exits.")
