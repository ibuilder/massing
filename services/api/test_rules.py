"""W11 D3 detail-rule engine + D7 window-flashing worked case: a window in an EXTERNAL wall auto-gets the
IBC §1404.4 / ASTM E2112 flashing detail + MasterFormat 08 51 00; a window in an interior wall does not.
The same rules validate as IDS QA (missing-keynote pre-flight).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_rules.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import detailing, edit, massing, rules  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_rules_test.ifc")
massing.generate_blank_ifc(TMP, name="Rules Test", storeys=1, storey_height=3.0, ground_size=30.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# an EXTERNAL wall with a window, and an INTERIOR wall with a window
ext = edit.add_wall(m, [0, 0], [8, 0], 3.0, 0.2, st)
edit.set_element_pset(m, ext, "Pset_WallCommon", "IsExternal", True, "bool")
ext_win = edit.add_opening(m, ext, width=1.5, height=1.2, sill=0.9, kind="window")

interior = edit.add_wall(m, [0, 5], [8, 5], 3.0, 0.1, st)
edit.set_element_pset(m, interior, "Pset_WallCommon", "IsExternal", False, "bool")
int_win = edit.add_opening(m, interior, width=1.0, height=1.2, sill=0.9, kind="window")

# --- before auto-detail: the exterior window is a compliance GAP -----------------------------------
v0 = rules.validate_rules(m)
assert any(g["guid"] == ext_win and "08 51 00" in g["missing"] for g in v0["elements"]), v0

# --- run the rule engine ---------------------------------------------------------------------------
r = rules.apply_rules(m)
assert r["matches"] >= 1 and r["codes_written"] >= 1 and r["documents_written"] >= 1, r
# the exterior window matched the flashing rule
assert any(a["rule"] == "exterior-window-flashing" and a["guid"] == ext_win for a in r["applied"]), r["applied"]

# the EXTERIOR window now carries MasterFormat 08 51 00 + the flashing detail + install instruction
det = detailing.element_detailing(m, ext_win)
codes = {(c["system"], c["code"]) for c in det["classifications"]}
assert ("MasterFormat", "08 51 00") in codes and ("UniFormat", "B2020") in codes, codes
doc_ids = {d["identification"] for d in det["documents"]}
assert "A-541/3" in doc_ids and "INST-0851-01" in doc_ids, det["documents"]

# CODE-3: applying with a resolved IBC edition rewords the citation from the seed's 2021 to that edition
TMP2 = os.path.join(os.path.dirname(__file__), "_rules_ed.ifc")
massing.generate_blank_ifc(TMP2, name="Rules Ed", storeys=1, storey_height=3.0, ground_size=30.0)
me = open_model(TMP2); ste = me.by_type("IfcBuildingStorey")[0].Name
we = edit.add_wall(me, [0, 0], [8, 0], 3.0, 0.2, ste)
edit.set_element_pset(me, we, "Pset_WallCommon", "IsExternal", True, "bool")
wine = edit.add_opening(me, we, width=1.5, height=1.2, sill=0.9, kind="window")
r24 = rules.apply_rules(me, ibc_edition="2024")
assert r24["ibc_edition"] == "2024", r24
descs = " ".join(d.get("description", "") for d in detailing.element_detailing(me, wine)["documents"])
assert "IBC 2024" in descs and "IBC 2021" not in descs, descs
if os.path.exists(TMP2):
    os.remove(TMP2)

# the INTERIOR window did NOT get the flashing rule (host not external)
det_int = detailing.element_detailing(m, int_win)
assert ("MasterFormat", "08 51 00") not in {(c["system"], c["code"]) for c in det_int["classifications"]}, det_int
assert not det_int["documents"], det_int

# --- after auto-detail: the gap is closed ----------------------------------------------------------
v1 = rules.validate_rules(m)
assert not any(g["guid"] == ext_win for g in v1["elements"]), v1

# --- fire-rated wall rule fires on FireRating ------------------------------------------------------
edit.set_element_pset(m, ext, "Pset_WallCommon", "FireRating", "2HR", "str")
r2 = rules.apply_rules(m)
assert any(a["rule"] == "fire-rated-wall-keynote" and a["guid"] == ext for a in r2["applied"]), r2["applied"]
assert ("MasterFormat", "09 21 16") in {(c["system"], c["code"]) for c in detailing.element_detailing(m, ext)["classifications"]}

# --- recipe path (the /edit route) -----------------------------------------------------------------
OUT = os.path.join(os.path.dirname(__file__), "_rules_out.ifc")
rc = edit.apply_recipe(TMP, "apply_detailing_rules", {}, OUT)
assert rc["changed"]["matches"] >= 1, rc
mo = open_model(OUT)
assert ("MasterFormat", "08 51 00") in {(c["system"], c["code"])
                                        for c in detailing.element_detailing(mo, ext_win)["classifications"]}

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("RULES OK - apply_rules auto-details: exterior window (in external wall) gets IBC 1404.4/ASTM E2112 "
      "flashing detail (A-541/3) + install instruction + MasterFormat 08 51 00 + UniFormat B2020; interior "
      "window gets nothing; fire-rated wall gets 09 21 16 keynote; validate_rules flags the gap before and "
      "clears it after; apply_detailing_rules works via apply_recipe.")
