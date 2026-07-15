"""CODE-EBC — IEBC existing-building scope classifier. The Work-Area-Method decision tree (Repair ·
Alteration 1/2/3 · Change of Occupancy · Addition) is facts of law; classify() is pure/deterministic and
from_model() infers a first-guess scope from the model's phasing.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_ebc.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import ebc, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# --- pathways catalog: 3 compliance methods + 6 classifications, all cited -------------------------
pw = ebc.pathways()
assert len(pw["methods"]) == 3 and {m["key"] for m in pw["methods"]} == {"prescriptive", "work-area", "performance"}
keys = {c["key"] for c in pw["classifications"]}
assert keys == {"repair", "alteration_1", "alteration_2", "alteration_3", "change_occupancy", "addition"}, keys
assert pw["work_area_threshold_pct"] == 50.0
assert pw["disclaimer"] and pw["verify"]
for c in pw["classifications"]:
    assert c["class_cite"].startswith("IEBC §") and c["req_cite"].startswith("IEBC Chapter"), c

# --- repair only → Repair --------------------------------------------------------------------------
r = ebc.classify(repair_only=True)
assert r["ok"] and r["classification"] == "Repair", r
assert r["classification_key"] == "repair" and r["citations"][0]["section"] == "IEBC §502", r

# --- same-purpose replacement, no reconfiguration → Alteration Level 1 -----------------------------
r = ebc.classify(replaces_same_purpose=True)
assert r["classification"] == "Alteration — Level 1", r
assert [a["classification"] for a in r["applies"]] == ["Alteration — Level 1"], r["applies"]

# --- a Level-2 trigger, no work-area given → Level 2, applies L1+L2 (with an assumed-≤50% note) -----
r = ebc.classify(reconfigures_space=True)
assert r["classification"] == "Alteration — Level 2", r
assert [a["classification"] for a in r["applies"]] == ["Alteration — Level 1", "Alteration — Level 2"], r["applies"]
assert any("50%" in n for n in r["notes"]), r["notes"]
assert "reconfigures_space" in r["triggers"], r["triggers"]

# --- a Level-2 trigger over >50% of the building → Level 3, applies L1+L2+L3 -----------------------
r = ebc.classify(alters_systems=True, work_area_pct=62)
assert r["classification"] == "Alteration — Level 3", r
assert [a["classification"] for a in r["applies"]] == [
    "Alteration — Level 1", "Alteration — Level 2", "Alteration — Level 3"], r["applies"]
assert r["citations"][0]["section"] == "IEBC §505", r
assert r["work_area_pct"] == 62.0, r

# --- exactly at the threshold stays Level 2 (must EXCEED 50%) --------------------------------------
r = ebc.classify(alters_openings=True, work_area_pct=50)
assert r["classification"] == "Alteration — Level 2", r
r = ebc.classify(alters_openings=True, work_area_pct=50.1)
assert r["classification"] == "Alteration — Level 3", r

# --- change of occupancy is the primary; a co-occurring alteration still applies -------------------
r = ebc.classify(changes_occupancy=True, reconfigures_space=True, work_area_pct=30)
assert r["classification"] == "Change of Occupancy", r
applied = [a["classification"] for a in r["applies"]]
assert "Change of Occupancy" in applied and "Alteration — Level 2" in applied, applied

# --- an addition governs as primary even alongside an alteration -----------------------------------
r = ebc.classify(adds_area=True, alters_systems=True, work_area_pct=20)
assert r["classification"] == "Addition", r
assert r["citations"][0]["section"] == "IEBC §507", r
assert any("alteration" in n.lower() for n in r["notes"]), r["notes"]

# --- empty scope → not classified, with guidance ---------------------------------------------------
r = ebc.classify()
assert r["ok"] is False and r["classification"] is None and "No scope" in r["reason"], r

# --- edition resolution: a seeded state pins the IEBC to its IBC cycle; unknown → baseline ---------
r = ebc.classify(jurisdiction="ca", repair_only=True)
assert r["code"]["edition"] == 2021 and r["code"]["adoption_resolved"] is True, r["code"]
r = ebc.classify(jurisdiction="ny", repair_only=True)      # NY seeds IBC 2018
assert r["code"]["edition"] == 2018, r["code"]
r = ebc.classify(jurisdiction="ZZ", repair_only=True)      # unknown → baseline
assert r["code"]["edition"] == 2021 and r["code"]["adoption_resolved"] is False, r["code"]

# --- from_model: a mixed existing/new model infers an alteration with a work-area estimate ---------
TMP = os.path.join(os.path.dirname(__file__), "_ebc_test.ifc")
massing.generate_blank_ifc(TMP, name="EBC Test", storeys=1, storey_height=4.0, ground_size=40.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
# author a few elements (proxies via the content library) to phase
for i in range(4):
    edit.place_content(m, "dumpster", [float(i * 3), 0.0], storey=st, name=f"E{i}")
guids = [e.GlobalId for e in m.by_type("IfcElement")]
assert len(guids) >= 4, len(guids)
edit.set_phase(m, guids[:3], "existing")   # 3 existing
edit.set_phase(m, guids[3:4], "new")       # 1 new  → worked share 1/4 = 25%

res = ebc.from_model(m, jurisdiction="ca")
assert res["ok"] and res["inferred"].get("reconfigures_space") is True, res.get("inferred")
assert res["classification"] == "Alteration — Level 2", res["classification"]
assert res["inferred"].get("work_area_pct") == 25.0, res["inferred"]
assert res["phase_counts"].get("EXISTING") == 3 and res["phase_counts"].get("NEW") == 1, res["phase_counts"]
assert res["basis"], "from_model must explain its inference"

# an override beats the geometry guess (force >50% → Level 3)
res2 = ebc.from_model(m, jurisdiction="ca", work_area_pct=80)
assert res2["classification"] == "Alteration — Level 3", res2["classification"]

# a model with only existing elements → treated as a repair
edit.set_phase(m, guids, "existing")
res3 = ebc.from_model(m)
assert res3["inferred"].get("repair_only") is True and res3["classification"] == "Repair", res3

for p in (TMP,):
    if os.path.exists(p):
        os.remove(p)

print("test_ebc OK")
