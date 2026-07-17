"""RFI-0 NL-QA: ask a plain-language question and get a cited answer from the model's own data —
element provenance, decision-readiness gaps, spec-section lookup. Covers rfi_qa.ask + the /rfi/qa route.
Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_rfi_qa.py"""
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_rfi_qa.db"
os.environ["STORAGE_DIR"] = "./test_storage_rfiqa"
os.environ["IFC_DIR"] = "./test_ifc_rfiqa"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_rfi_qa.db",):
    if os.path.exists(f):
        os.remove(f)

import sys                                                   # noqa: E402
from pathlib import Path                                     # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from fastapi.testclient import TestClient                    # noqa: E402
from aec_api.main import app                                 # noqa: E402
from aec_data import detailing, edit, massing                # noqa: E402
from aec_data.ifc_loader import open_model                   # noqa: E402

# a model with a governed, detailed column + readiness gaps (unnamed spaces, a sub-min egress door)
_ifc = Path(tempfile.gettempdir()) / "rfiqa_test_model.ifc"
massing.generate_blank_ifc(str(_ifc), name="RFI-QA Test", storeys=1, storey_height=3.0, ground_size=30.0)
m = open_model(str(_ifc))
st = m.by_type("IfcBuildingStorey")[0].Name
col = edit.add_column(m, [3, 3], 3.0, 0.4, 0.4, st)
detailing.classify(m, [col], "MasterFormat", "05 12 00", "Structural Steel Framing")
detailing.attach_document(m, [col], "Column base detail", location="details/S-501.pdf")
edit.add_spaces(m, rooms_per_storey=2, ceiling_height=3.0)
w = edit.add_wall(m, [0, 0], [8, 0], 3.0, 0.2, st)
edit.add_opening(m, w, width=0.7, height=2.1, kind="door")       # sub-min egress door → a readiness gap
m.write(str(_ifc))
COL_GUID = col
IFC_BYTES = _ifc.read_bytes()

with TestClient(app := __import__("aec_api.main", fromlist=["app"]).app) as c:
    pid = c.post("/projects", json={"name": "RFI QA"}).json()["id"]

    # no source IFC yet → 409
    assert c.post(f"/projects/{pid}/rfi/qa", json={"question": "anything"}).status_code == 409
    r = c.post(f"/projects/{pid}/source-ifc?publish=false",
               files={"file": ("source.ifc", IFC_BYTES, "application/octet-stream")})
    assert r.status_code == 200, f"upload: {r.status_code} {r.text[:160]}"

    # a blank question is rejected
    assert c.post(f"/projects/{pid}/rfi/qa", json={"question": "   "}).status_code == 400

    # 1) element provenance by GUID → a cited answer (spec section + detail sheet + location)
    q1 = c.post(f"/projects/{pid}/rfi/qa", json={"question": f"what governs {COL_GUID}?"}).json()
    assert q1["intent"] == "element" and q1["found"], q1
    refs = [ci["ref"] for ci in q1["citations"]]
    assert "MasterFormat 05 12 00" in refs, refs
    assert any("Column base detail" in x and "S-501" in x for x in refs), refs
    assert "05 12 00" in q1["answer"] and "S-501" in q1["answer"], q1["answer"]

    # 2) readiness question → the ranked gaps with fixes, cited
    q2 = c.post(f"/projects/{pid}/rfi/qa", json={"question": "what's blocking approval?"}).json()
    assert q2["intent"] == "readiness", q2
    assert q2["ready"] is False and q2["total_gaps"] >= 1, q2
    assert q2["citations"] and all(ci["kind"] == "gap" for ci in q2["citations"]), q2["citations"]

    # 3) spec-section lookup by code → what it governs
    q3 = c.post(f"/projects/{pid}/rfi/qa", json={"question": "what is spec section 05 12 00?"}).json()
    assert q3["intent"] == "spec" and q3["found"], q3
    assert "Structural Steel Framing" in q3["answer"], q3["answer"]
    assert q3["citations"][0]["guids"], "the section cites the elements it governs"

    # 4) an unrecognised question → a model overview that points at how to ask a sourced question
    q4 = c.post(f"/projects/{pid}/rfi/qa", json={"question": "hello there"}).json()
    assert q4["intent"] == "overview" and "elements" in q4["counts"], q4

    # every answer carries the cited-source disclaimer
    for qq in (q1, q2, q3, q4):
        assert "cited-source" in qq["disclaimer"], qq["disclaimer"]

print("RFI-QA OK - /rfi/qa routes a plain-language question to the right substrate and answers with "
      "citations: 'what governs <guid>?' -> element provenance (MasterFormat 05 12 00 + Column base "
      "detail S-501 + level); 'what's blocking approval?' -> ranked decision-readiness gaps + fixes; "
      "'what is spec section 05 12 00?' -> the governed elements; an unrecognised question -> a model "
      "overview. 409 without a source IFC, 400 on a blank question; deterministic, no API key needed.")
