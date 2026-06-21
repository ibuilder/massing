"""Model estimating engine: aggregate takeoff by class, apply unit rates, total + unpriced.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_estimate.py"""
from aec_api import estimate as est

# fake takeoff rows (as aec_data.qto.takeoff would return)
rows = [
    {"ifc_class": "IfcWall", "area": 50.0}, {"ifc_class": "IfcWall", "area": 30.0},   # 80 m² @160 = 12800
    {"ifc_class": "IfcColumn"}, {"ifc_class": "IfcColumn"},                            # 2 ea @450 = 900
    {"ifc_class": "IfcBeam", "length": 10.0},                                          # 10 m @90 = 900
    {"ifc_class": "IfcFurniture"},                                                     # unpriced
]
r = est.estimate_from_takeoff(rows)
by = {l["ifc_class"]: l for l in r["lines"]}

assert by["IfcWall"]["quantity"] == 80.0 and by["IfcWall"]["amount"] == 12800.0, by["IfcWall"]
assert by["IfcColumn"]["count"] == 2 and by["IfcColumn"]["amount"] == 900.0, by["IfcColumn"]
assert by["IfcBeam"]["amount"] == 900.0
assert r["total"] == 12800.0 + 900.0 + 900.0, r["total"]
assert r["lines"][0]["ifc_class"] == "IfcWall"                       # sorted by amount desc
assert r["element_count"] == 6
assert any(u["ifc_class"] == "IfcFurniture" for u in r["unpriced"]), r["unpriced"]

# per-class rate override
r2 = est.estimate_from_takeoff(rows, overrides={"IfcWall": 200.0})
assert {l["ifc_class"]: l for l in r2["lines"]}["IfcWall"]["amount"] == 16000.0

print("ESTIMATE OK - takeoff aggregated by class, priced (walls 80m² @160 = $12,800), unpriced flagged, overrides")
