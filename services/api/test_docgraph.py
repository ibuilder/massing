"""W9-4 (harder half): the document / specification graph + cited-source element provenance.
Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_docgraph.py"""
import os
import sys
import tempfile

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import detailing, docgraph, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(tempfile.gettempdir(), "_docgraph_test.ifc")
massing.generate_blank_ifc(TMP, name="DocGraph Test", storeys=1, storey_height=3.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

w = edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)
col = edit.add_column(m, [3, 2], 3.0, 0.4, 0.4, st)
# two governing spec sections (MasterFormat) + a detail sheet on the column
detailing.classify(m, [w], "MasterFormat", "04 20 00", "Unit Masonry")
detailing.classify(m, [col], "MasterFormat", "05 12 00", "Structural Steel Framing")
detailing.attach_document(m, [col], "Column base detail", location="details/S-501.pdf")

# --- build: spec-section + document nodes over the model --------------------------------------------
b = docgraph.build(m)
assert b["counts"]["spec_sections"] == 2 and b["counts"]["documents"] == 1, b["counts"]
assert b["counts"]["edges"] == 3, b["counts"]                       # 2 classifications + 1 document
assert b["by_rel"]["specified_by"] == 2 and b["by_rel"]["documented_by"] == 1, b["by_rel"]
codes = {s["code"] for s in b["spec_sections"]}
assert codes == {"04 20 00", "05 12 00"}, codes
steel = next(s for s in b["spec_sections"] if s["code"] == "05 12 00")
assert steel["title"] == "Structural Steel Framing" and col in steel["elements"], steel

# --- element_sources: the cited provenance of one element -------------------------------------------
src = docgraph.element_sources(m, col)
assert src["found"] and src["class"] == "IfcColumn", src
refs = [c["ref"] for c in src["citations"]]
assert "MasterFormat 05 12 00" in refs, refs                       # spec section citation
assert any(r.startswith("Column base detail") and "S-501" in r for r in refs), refs  # document + sheet
assert any(c["kind"] == "location" for c in src["citations"]), src["citations"]       # spatial container
# the document carries its derived sheet reference
doc = src["documents"][0]
assert doc["name"] == "Column base detail" and doc["sheet"] == "S-501", doc

# --- an element with no governing docs/codes still resolves (empty citations, not an error) ---------
uncoded = edit.add_column(m, [8, 8], 3.0, 0.4, 0.4, st)
us = docgraph.element_sources(m, uncoded)
assert us["found"] and us["spec_sections"] == [] and us["documents"] == [], us
# location is still cited even with no spec/doc
assert any(c["kind"] == "location" for c in us["citations"]), us["citations"]

# --- an unknown GUID is reported, not raised --------------------------------------------------------
miss = docgraph.element_sources(m, "0123456789abcdefABCDEF")
assert miss["found"] is False and miss["citations"] == [], miss

if os.path.exists(TMP):
    os.remove(TMP)

print("DOCGRAPH OK - build() folds spec-section (classification code) + document (sheet-ref'd) nodes onto "
      "the model: 2 MasterFormat sections + 1 detail sheet -> 3 element edges (specified_by / "
      "documented_by). element_sources() returns one element's cited provenance — MasterFormat 05 12 00 "
      "(spec), 'Column base detail (S-501)' (document + derived sheet ref), and its level (spatial "
      "container) — each citation tagged with its source. Uncoded elements resolve with empty citations; "
      "an unknown GUID is reported found=False, never raised. The RFI-0 NL-QA cited-source substrate.")
