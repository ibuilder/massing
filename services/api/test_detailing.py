"""W11 Track D carrier layer: attach classification codes (UniFormat/MasterFormat/OmniClass keynote+spec
codes) and documents (detail drawing + install instruction) to elements, IFC-natively, and read them back.
The join layer the detail-rule engine + keynote/spec/drawing generators consume.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_detailing.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import detailing, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_detailing_test.ifc")
massing.generate_blank_ifc(TMP, name="Detailing Test", storeys=1, storey_height=3.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
wall = edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)
win = edit.add_opening(m, wall, width=1.5, height=1.2, sill=0.9, kind="window")

# --- classify the window with all three systems (element + spec + product) --------------------------
assert detailing.classify(m, [win], "UniFormat", "B2020", "Exterior Windows") == 1
assert detailing.classify(m, [win], "MasterFormat", "08 51 00", "Aluminum Windows", edition="2020") == 1
assert detailing.classify(m, [win], "OmniClass", "23-17 11 11", "Windows") == 1

# --- attach the IBC/ASTM flashing detail + installation instruction as documents --------------------
assert detailing.attach_document(m, [win], "Head/Sill Flashing @ Punched Opening",
                                 location="details/win_flashing.svg", identification="A-541/3",
                                 description="IBC 1404.4 / ASTM E2112 window flashing") == 1
assert detailing.attach_document(m, [win], "Window Flashing Installation Sequence",
                                 location="docs/win_flashing_install.pdf", identification="INST-0851-01",
                                 purpose="INSTRUCTION") == 1

# --- read it back via the inspector -----------------------------------------------------------------
det = detailing.element_detailing(m, win)
codes = {c["system"]: c["code"] for c in det["classifications"]}
assert codes.get("MasterFormat") == "08 51 00", det["classifications"]
assert codes.get("UniFormat") == "B2020" and codes.get("OmniClass") == "23-17 11 11", codes
docs = {d["identification"]: d for d in det["documents"]}
assert "A-541/3" in docs and docs["A-541/3"]["location"] == "details/win_flashing.svg", docs
assert "INST-0851-01" in docs, docs
assert len(det["documents"]) == 2 and len(det["classifications"]) == 3, det

# --- re-attaching the same document (by identification) reuses the IfcDocumentInformation ------------
n_info_before = len(m.by_type("IfcDocumentInformation"))
detailing.attach_document(m, [wall], "Head/Sill Flashing @ Punched Opening",
                          location="details/win_flashing.svg", identification="A-541/3")
assert len(m.by_type("IfcDocumentInformation")) == n_info_before, "duplicate IfcDocumentInformation"
# the wall now shares that detail too
assert any(d["identification"] == "A-541/3" for d in detailing.element_detailing(m, wall)["documents"])

# --- stale GUIDs skipped ----------------------------------------------------------------------------
assert detailing.classify(m, [win, "NOTAGUID000000000000000"], "Uniclass", "SS_25_10") == 1
assert detailing.attach_document(m, ["NOTAGUID000000000000000"], "nope") == 0

# --- recipe path (the /edit route) ------------------------------------------------------------------
OUT = os.path.join(os.path.dirname(__file__), "_detailing_out.ifc")
rc = edit.apply_recipe(TMP, "classify",
                       {"guids": [wall], "system": "MasterFormat", "code": "04 20 00"}, OUT)
assert rc["changed"] == 1, rc
rd = edit.apply_recipe(OUT, "attach_document",
                       {"guids": [wall], "name": "CMU wall section", "location": "details/cmu.svg",
                        "identification": "A-521/1"}, OUT)
assert rd["changed"] == 1, rd
mo = open_model(OUT)
det2 = detailing.element_detailing(mo, wall)
assert any(c["code"] == "04 20 00" for c in det2["classifications"])
assert any(d["identification"] == "A-521/1" for d in det2["documents"])

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("DETAILING OK - classify attaches UniFormat/MasterFormat/OmniClass codes (IfcRelAssociatesClassification); "
      "attach_document attaches detail SVG + install instruction (IfcRelAssociatesDocument -> "
      "IfcDocumentReference -> IfcDocumentInformation, deduped by identification); element_detailing reads "
      "both back; stale GUIDs skipped; classify + attach_document recipes work via apply_recipe.")
