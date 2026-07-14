"""W11 D1 code-analysis summary: assemble the IBC code sheet data (occupancy, construction type, gross
area + stories, computed occupant load + egress, governing sections) from a model.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_code_analysis.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import codecheck as cc  # noqa: E402
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_ca_test.ifc")
massing.generate_blank_ifc(TMP, name="Code Analysis Test", storeys=2, storey_height=3.5, ground_size=30.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_spaces(m, rooms_per_storey=4, ceiling_height=3.0)      # occupiable spaces (business default)
w = edit.add_wall(m, [0, 0], [8, 0], 3.0, 0.2, st)
edit.add_opening(m, w, width=0.9, height=2.1, kind="door")

# --- default analysis (occupancy inferred, construction type defaulted) ---------------------------
a = cc.code_analysis(m)
assert a["building"]["stories"] == 2, a["building"]
assert a["building"]["gross_area_ft2"] > 0 and a["building"]["occupant_load"] > 0, a["building"]
assert a["occupancy"]["group"] in {"B", "A", "M", "S", "—"}, a["occupancy"]      # inferred group letter
assert a["construction_type"].startswith("II-B"), a["construction_type"]         # default
assert a["sprinklered"] is False
# egress + doors carried through from the egress computation
assert "required_width_in" in a["egress"] and a["doors"]["checked"] >= 1, a
# governing sections cited
secs = " ".join(a["allowable"]["sections"] + a["citations"])
assert "Table 506.2" in secs and "504" in secs and "Table 601" in secs, secs
assert a["disclaimer"], "must carry the not-a-certified-review disclaimer"

# --- explicit inputs: occupancy group + construction type + sprinklered ---------------------------
a2 = cc.code_analysis(m, occupancy_group="A", construction_type="I-A", sprinklered=True)
assert a2["occupancy"]["group"] == "A" and a2["construction_type"] == "I-A", a2["occupancy"]
assert a2["sprinklered"] is True and a2["allowable"]["sprinkler_increase"] == "eligible", a2["allowable"]

# --- occupant-load-by-occupancy breakdown present -------------------------------------------------
assert isinstance(a["occupant_load_by_occupancy"], list) and a["occupant_load_by_occupancy"], a
assert all("occupancy" in o and "load" in o for o in a["occupant_load_by_occupancy"])

if os.path.exists(TMP):
    os.remove(TMP)

print("CODE ANALYSIS OK - code_analysis assembles the IBC code sheet: 2 stories, gross area + computed "
      "occupant load, occupancy group (inferred / explicit), construction type (default II-B / explicit "
      "I-A), sprinkler increase, egress + door checks carried through, governing sections cited "
      "(Table 506.2 / §504 / Table 601), with the pre-check disclaimer.")
