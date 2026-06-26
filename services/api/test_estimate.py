"""Model estimating engine: aggregate takeoff by class, apply unit rates, total + unpriced,
GFA benchmark + recommended source. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_estimate.py"""
from aec_api import estimate as est

# fake takeoff rows (as aec_data.qto.takeoff would return). Concrete is billed by volume now.
rows = [
    {"ifc_class": "IfcWall", "area": 50.0}, {"ifc_class": "IfcWall", "area": 30.0},   # 80 m² @160 = 12800
    {"ifc_class": "IfcColumn", "volume": 1.0}, {"ifc_class": "IfcColumn", "volume": 1.0},  # 2 m³ @650 = 1300
    {"ifc_class": "IfcBeam", "volume": 2.0},                                           # 2 m³ @700 = 1400
    {"ifc_class": "IfcFurniture"},                                                     # unpriced
]
r = est.estimate_from_takeoff(rows)
by = {l["ifc_class"]: l for l in r["lines"]}

assert by["IfcWall"]["quantity"] == 80.0 and by["IfcWall"]["amount"] == 12800.0, by["IfcWall"]
assert by["IfcColumn"]["amount"] == 1300.0, by["IfcColumn"]      # volume-based concrete
assert by["IfcBeam"]["amount"] == 1400.0, by["IfcBeam"]
assert r["total"] == 12800.0 + 1300.0 + 1400.0, r["total"]
assert r["lines"][0]["ifc_class"] == "IfcWall"                   # sorted by amount desc
assert r["element_count"] == 6 and r["source"] == "model"
assert any(u["ifc_class"] == "IfcFurniture" for u in r["unpriced"]), r["unpriced"]

# per-class rate override
r2 = est.estimate_from_takeoff(rows, overrides={"IfcWall": 200.0})
assert {l["ifc_class"]: l for l in r2["lines"]}["IfcWall"]["amount"] == 16000.0

# GFA benchmark + recommended source ----------------------------------------
# sparse model (few elements) vs a large GFA -> recommend the GFA benchmark, not the tiny total
sparse = est.estimate_from_takeoff([{"ifc_class": "IfcColumn", "volume": 1.0}], gfa_sf=60_000)
assert sparse["gfa_benchmark"]["amount"] == round(60_000 * est.DEFAULT_PSF), sparse["gfa_benchmark"]
assert sparse["recommended"] == "gfa", sparse                     # 1 element, total << benchmark
assert sparse["recommended_total"] == sparse["gfa_benchmark"]["amount"]

# a model whose total is in-band with the GFA benchmark -> trust the model
big = est.estimate_from_takeoff(
    [{"ifc_class": "IfcSlab", "volume": 30.0} for _ in range(20)], gfa_sf=2_000)  # 20×30×550 = 330k
assert big["recommended"] == "model", big

# per-floor / per-discipline QTO: quantities + cost mapped to the storey they sit on
srows = [
    {"ifc_class": "IfcSlab", "volume": 10.0, "storey": "Level 1"},      # 10 m³ @550 = 5500
    {"ifc_class": "IfcColumn", "volume": 1.0, "storey": "Level 1"},     # 1 m³ @650 = 650
    {"ifc_class": "IfcSlab", "volume": 10.0, "storey": "Level 2"},      # 5500
    {"ifc_class": "IfcWall", "area": 100.0, "storey": "Level 2"},       # 100 m² @160 = 16000
]
bs = est.estimate_by_storey(srows)
floors = {s["storey"]: s for s in bs["storeys"]}
assert [s["storey"] for s in bs["storeys"]] == ["Level 1", "Level 2"], bs["storeys"]   # floor-ordered
assert floors["Level 1"]["total"] == 6150.0, floors["Level 1"]         # 5500 slab + 650 column
assert floors["Level 2"]["total"] == 21500.0, floors["Level 2"]        # 5500 slab + 16000 wall
assert bs["grand_total"] == 27650.0 and bs["element_count"] == 4, bs
disc = {d["ifc_class"]: d for d in bs["by_discipline"]}
assert disc["IfcSlab"]["quantity"] == 20.0 and disc["IfcSlab"]["amount"] == 11000.0, disc["IfcSlab"]  # both floors

print("ESTIMATE OK - concrete by volume (cols $1,300 / beams $1,400), walls $12,800; "
      "GFA benchmark + recommended source (sparse->gfa, in-band->model); overrides; "
      "per-floor QTO (L1 $6,150 / L2 $21,500) + discipline roll-up")
