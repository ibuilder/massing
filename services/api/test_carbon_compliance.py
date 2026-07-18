"""CARBON-EC3: per-element A1–A3 off the model index, Buy Clean limit check, LEED-style inventory —
hand-computed on a synthetic index + endpoint smoke (404 without a model).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_carbon_compliance.py"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./_carboncomp_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_carboncomp")
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./_carboncomp_test.db"):
    os.remove("./_carboncomp_test.db")

from aec_api import carbon_compliance as CC  # noqa: E402


def el(guid, name, cls, storey, qtos, type_name="", psets=None):
    return {"guid": guid, "name": name, "ifc_class": cls, "storey": storey,
            "type_name": type_name, "psets": psets or {}, "qtos": qtos}


# hand-computed fixture:
#  W1 concrete wall, 2 m3  -> 2 × 300  = 600 kg
#  C1 concrete column, 0.5 m3 (material via pset, not name) -> 150 kg
#  B1 steel beam, area-only qto (m2) but steel factor is per kg -> family mismatch, EXCLUDED
#  G1 glazing panel, 4 m2  -> 4 × 45   = 180 kg
#  X1 mystery element with volume, no keyword match -> counted in coverage denominator, excluded
#  P1 element with no qtos at all -> not even considered
idx = {
    "W1": el("W1", "Concrete Wall 200", "IfcWall", "L1", {"Qto_WallBaseQuantities": {"NetVolume": 2.0}}),
    "C1": el("C1", "Column C30", "IfcColumn", "L1", {"Qto_ColumnBaseQuantities": {"GrossVolume": 0.5}},
             psets={"Pset_Custom": {"MaterialName": "cast concrete"}}),
    "B1": el("B1", "Steel Beam W12", "IfcBeam", "L2", {"Qto_BeamBaseQuantities": {"NetSideArea": 3.0}}),
    "G1": el("G1", "Glazing Panel", "IfcPlate", "L2", {"Qto_PlateBaseQuantities": {"NetArea": 4.0}}),
    "X1": el("X1", "Mystery Thing", "IfcBuildingElementProxy", "L1",
             {"Qto_Base": {"NetVolume": 9.0}}),
    "P1": el("P1", "No Quantity", "IfcWall", "L1", {}),
}

r = CC.element_carbon(idx, gfa_m2=100.0)
assert r["element_count"] == 6 and r["with_quantity"] == 5, (r["element_count"], r["with_quantity"])
assert r["carbon_matched"] == 3, r["carbon_matched"]            # W1, C1, G1 (B1 family-mismatch, X1 no kw)
assert r["coverage_pct"] == 60.0, r["coverage_pct"]             # 3/5
assert r["total_kgco2e"] == 930.0, r["total_kgco2e"]            # 600 + 150 + 180
assert r["by_category"]["concrete"]["kgco2e"] == 750.0 and r["by_category"]["concrete"]["quantity"] == 2.5
assert r["by_category"]["glazing"]["kgco2e"] == 180.0
assert r["by_storey"]["L1"] == 750.0 and r["by_storey"]["L2"] == 180.0, r["by_storey"]
assert r["hotspots"][0]["guid"] == "W1" and r["hotspots"][0]["kgco2e"] == 600.0
assert r["intensity_kgco2e_m2"] == 9.3, r["intensity_kgco2e_m2"]   # 930 / 100

# --- Buy Clean: concrete default 300 <= limit 361 -> PASS; only categories present are checked ------
bc = CC.buy_clean_check(r)
rows = {x["category"]: x for x in bc["rows"]}
assert "concrete" in rows and rows["concrete"]["pass"] is True, rows
assert rows["concrete"]["headroom_pct"] == round((361.0 - 300.0) / 361.0 * 100, 1)
assert "glazing" not in rows, "glazing has no Buy Clean limit row — not checked"
# a category whose default exceeds the limit fails with the EPD action (steel 1.55 > 1.22)
r_steel = CC.element_carbon({"S1": el("S1", "structural steel brace", "IfcMember", "L1",
                                      {"Q": {"NetVolume": 1.0}})})
assert r_steel["carbon_matched"] == 0, "steel factor is per kg — a volume qto must NOT be guessed"
bc2 = CC.buy_clean_check({"by_category": {"structural steel": {"kgco2e": 100.0, "quantity": 64.0}}})
row = bc2["rows"][0]
assert row["pass"] is False and "EPD" in row["action"], row

# --- LEED inventory: shares sum to ~100, disclosure present -----------------------------------------
inv = CC.leed_inventory(r, project_name="Test Tower")
assert inv["project"] == "Test Tower" and inv["total_kgco2e"] == 930.0
assert abs(sum(i["share_pct"] for i in inv["items"]) - 100.0) < 0.5, inv["items"]
assert all("EPD" in i["factor_source"] for i in inv["items"])
assert "not a verified" in inv["disclosure"]

# --- endpoints: 404 until a model index exists -------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Carbon"}).json()["id"]
    assert c.get(f"/projects/{pid}/carbon/elements").status_code == 404
    assert c.get(f"/projects/{pid}/carbon/compliance").status_code == 404

print("CARBON-EC3 OK - per-element A1-A3 off the index: 600+150+180=930 kg over 3 matched of 5 "
      "quantified elements (60% coverage — the steel area/kg family mismatch and the unmatched proxy "
      "are excluded, never guessed); storey + category rollups; hotspot = the 600 kg wall; intensity "
      "9.3 kg/m2; Buy Clean: concrete 300<=361 passes with headroom, structural steel default 1.55>1.22 "
      "fails with the obtain-an-EPD action; LEED inventory shares sum to 100% with the disclosure; "
      "endpoints 404 without a model.")
