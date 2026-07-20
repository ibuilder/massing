"""REBAR-RULES + BBS — the reinforcement rule catalog (ACI-envelope tie spacing), the cage checker,
and the bar bending schedule off authored IfcReinforcingBar geometry.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_rebar_rules.py"""
import math
import os

from aec_data import edit, massing, rebar, rebar_rules  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# --- rule catalog: pure params maths ---------------------------------------------------------------
# 0.5×0.5 column, #8 bars (25.4 mm), #3 ties (9.5 mm): 16·db=0.406 < 48·dt=0.457 < 0.5 → 16·d_bar
p = rebar_rules.column_cage_params(0.5, 0.5)
assert p["bar_size"] == "#8" and p["tie_size"] == "#3", p
assert p["governing"] == "16·d_bar" and p["tie_spacing"] == 0.406, p
assert p["min_longitudinal_bars"] == 4, p
# a skinny 0.25 column: least dimension governs
p2 = rebar_rules.column_cage_params(0.25, 0.6)
assert p2["governing"] == "least dimension" and p2["tie_spacing"] == 0.25, p2
# small bars + fat ties: 16·db (#4 = 12.7 mm → 0.203) governs over 48·dt (#5 → 0.762)
p3 = rebar_rules.column_cage_params(0.5, 0.5, bar_size="#4", tie_size="#5")
assert p3["governing"] == "16·d_bar" and p3["tie_spacing"] == 0.203, p3
assert "column" in rebar_rules.RULES and "beam" in rebar_rules.RULES, "catalog typologies"

# --- author a cage, then BBS + check ---------------------------------------------------------------
TMP = os.path.join(os.path.dirname(__file__), "_rebar_rules_test.ifc")
massing.generate_blank_ifc(TMP, name="RR Test", storeys=1, storey_height=3.5, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
col = edit.add_column(m, [3, 3], 3.5, 0.5, 0.5, st)
r = rebar.add_rebar_cage(m, col, bar_size="#8", tie_size="#3", cover=0.04, tie_spacing=0.3)

bbs = rebar_rules.bar_bending_schedule(m)
assert bbs["bars"] == r["bars"] + r["ties"] and bbs["skipped"] == 0, bbs
assert bbs["marks"] == 2, bbs                                     # one straight mark + one tie mark
straight = next(x for x in bbs["rows"] if x["shape"] == "straight")
tie = next(x for x in bbs["rows"] if x["shape"] == "closed tie")
assert straight["count"] == 4 and straight["size"] == "#8", straight
assert straight["cut_length_m"] == round(3.5 - 2 * 0.04, 2), straight   # full height minus covers
# #8 unit mass ≈ π·(12.7 mm)²·7850 ≈ 3.98 kg/m (the handbook value)
assert abs(straight["unit_mass_kg_m"] - 3.98) < 0.02, straight
assert tie["count"] == r["ties"] and tie["size"] == "#3", tie
assert bbs["total_kg"] > 0 and bbs["total_tonnes"] == round(bbs["total_kg"] / 1000, 3), bbs
csv_txt = rebar_rules.bbs_csv(bbs)
assert csv_txt.startswith("Mark,") and "TOTAL" in csv_txt and "#8" in csv_txt, csv_txt[:200]

# --- SPRINT E: bending detail (legs + bend angles) per mark, off the authored geometry -------------
# the straight column bar is a single leg, no bends; its leg length ≈ the cut length in mm
assert straight["shape_family"] == "straight" and straight["bends"] == 0, straight
assert straight["bend_angles_deg"] == [] and len(straight["legs_mm"]) == 1, straight
assert abs(straight["legs_mm"][0] - straight["cut_length_m"] * 1000) < 1.0, straight
# the closed tie is classified as a stirrup and carries per-leg lengths + corner angles
assert tie["shape_family"] == "closed tie / stirrup", tie
assert len(tie["legs_mm"]) >= 4 and all(a >= 0 for a in tie["bend_angles_deg"]), tie
# the CSV now carries the bending columns
assert "Bends" in csv_txt and "Bend angles (deg)" in csv_txt and "Legs (mm)" in csv_txt, csv_txt[:200]
# pure bending_detail: an L-bar (one 90° corner) → single bend, two legs
lbar = rebar_rules.bending_detail([(0, 0, 0), (0, 0, 1.0), (0.3, 0, 1.0)], closed=False)
assert lbar["bends"] == 1 and lbar["shape_family"] == "single bend (L)", lbar
assert lbar["legs_mm"] == [1000.0, 300.0] and abs(lbar["bend_angles_deg"][0] - 90.0) < 0.5, lbar
# a straight-through polyline (collinear points) registers zero bends
assert rebar_rules.bending_detail([(0, 0, 0), (0, 0, 1.0), (0, 0, 2.0)], closed=False)["bends"] == 0

# check_cage: authored at 0.3 m ties < the 0.406 envelope → clean
chk = rebar_rules.check_cage(m, col)
assert chk["checked"] and chk["longitudinal_bars"] == 4 and chk["violations"] == [], chk
assert chk["ties"] == r["ties"], chk

# a second cage tied at 0.6 m > envelope → spacing violation with the governing limb named
col2 = edit.add_column(m, [8, 8], 3.5, 0.5, 0.5, st)
r2 = rebar.add_rebar_cage(m, col2, tie_spacing=0.6)
chk2 = rebar_rules.check_cage(m, col2)
assert chk2["checked"] and len(chk2["violations"]) == 1, chk2
assert "exceeds 0.406" in chk2["violations"][0] and "16·d_bar" in chk2["violations"][0], chk2

# a bare column (no cage) is a finding, not an error
col3 = edit.add_column(m, [12, 12], 3.5, 0.5, 0.5, st)
chk3 = rebar_rules.check_cage(m, col3)
assert chk3["checked"] is False and "no reinforcement cage" in chk3["violations"][0], chk3

# _polyline_length sanity: the closed 5-pt stirrup perimeter = 2·(w−2·cover)+2·(d−2·cover)
per = 2 * (0.5 - 2 * 0.04) + 2 * (0.5 - 2 * 0.04)
assert abs(tie["cut_length_m"] - round(per, 2)) < 0.01, (tie["cut_length_m"], per)
assert math.isclose(rebar_rules._polyline_length([(0, 0, 0), (3, 4, 0)]), 5.0), "3-4-5"

# --- route contract: BBS + check served off the project source IFC --------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_rebar_rules.db"
os.environ["STORAGE_DIR"] = "./test_storage_rebar_rules"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_rebar_rules.db"):
    os.remove("./test_rebar_rules.db")
m.write(TMP)                                          # persist the caged model for upload
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "RebarAPI"}).json()["id"]
    from aec_api.db import SessionLocal  # noqa: E402
    from aec_api.models import Project  # noqa: E402
    with SessionLocal() as s:                          # point the project at the caged model file
        s.get(Project, pid).source_ifc = TMP
        s.commit()
    bapi = c.get(f"/projects/{pid}/rebar/bbs").json()
    assert bapi["bars"] == bbs["bars"] + r2["bars"] + r2["ties"] and bapi["total_tonnes"] > 0, bapi
    csv_r = c.get(f"/projects/{pid}/rebar/bbs.csv")
    assert csv_r.status_code == 200 and csv_r.text.startswith("Mark,"), csv_r.text[:80]
    ck = c.get(f"/projects/{pid}/rebar/check?column={col2}").json()
    assert ck["checked"] and len(ck["violations"]) == 1, ck               # the 0.6 m cage still flags
    bad = c.get(f"/projects/{pid}/rebar/check?column=NOTAGUID")
    assert bad.status_code == 422, bad.text

os.remove(TMP)
print("REBAR RULES OK - catalog: ACI tie-spacing envelope picks the governing limb (16db=0.406 on a "
      "0.5m/#8 column, least-dim on a 0.25m, 16db with #4 bars); BBS off the authored cage: 2 marks "
      "(4×#8 straights at h−2·cover, ties at the stirrup perimeter), #8 unit mass ≈3.98 kg/m, totals "
      "+ tonnage + CSV with TOTAL row; check_cage passes the 0.3m cage, flags 0.6m > 0.406 envelope "
      "naming the limb, and reports a bare column as a finding")
