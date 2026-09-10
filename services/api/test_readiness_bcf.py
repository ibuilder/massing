"""RFI-0: promote the decision-readiness gaps to BCF topics (one per gap, GUID-anchored, priority by
severity), idempotently. The audit itself is covered by test_rfi_readiness; this covers the /bcf endpoint.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_readiness_bcf.py"""
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_readiness_bcf.db"
os.environ["STORAGE_DIR"] = "./test_storage_rbcf"   # matches .gitignore test_storage*/
os.environ["IFC_DIR"] = "./test_ifc_rbcf"           # matches .gitignore test_ifc*/
os.environ.pop("AEC_RBAC", None)
for f in ("./test_readiness_bcf.db",):
    if os.path.exists(f):
        os.remove(f)

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# a gap-y model: spaces without OccupancyType, a below-min egress door, an un-substantiated rated wall
_ifc = Path(tempfile.gettempdir()) / "rbcf_test_model.ifc"
massing.generate_blank_ifc(str(_ifc), name="RFI BCF Test", storeys=1, storey_height=3.0, ground_size=30.0)
m = open_model(str(_ifc))
st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_spaces(m, rooms_per_storey=3, ceiling_height=3.0)
w = edit.add_wall(m, [0, 0], [8, 0], 3.0, 0.2, st)
edit.add_opening(m, w, width=0.7, height=2.1, kind="door")        # 0.7 m < 32 in → egress gap
rw = edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)
edit.set_element_pset(m, rw, "Pset_WallCommon", "FireRating", "2HR")
m.write(str(_ifc))
IFC_BYTES = _ifc.read_bytes()

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Readiness"}).json()["id"]

    # no source IFC yet → 409
    assert c.post(f"/projects/{pid}/rfi/readiness/bcf").status_code == 409

    # upload the gap-y model as the source (skip the converter publish)
    r = c.post(f"/projects/{pid}/source-ifc?publish=false",
               files={"file": ("source.ifc", IFC_BYTES, "application/octet-stream")})
    assert r.status_code == 200, f"upload: {r.status_code} {r.text[:160]}"

    # the audit finds gaps
    ra = c.get(f"/projects/{pid}/rfi/readiness").json()
    assert ra["total_gaps"] >= 1 and ra["ready"] is False, ra

    # promote them to BCF topics
    rb = c.post(f"/projects/{pid}/rfi/readiness/bcf")
    assert rb.status_code == 200, f"bcf: {rb.status_code} {rb.text[:200]}"
    body = rb.json()
    assert body["created"] == ra["total_gaps"], (body["created"], ra["total_gaps"])
    assert body["created"] >= 1 and body["ready"] is False, body

    # they land as BCF topics of type "readiness" (visible in Issues), labelled by category.
    #
    # **Read through `/topics`, NOT `/pins`, and that distinction is the point.** This block used
    # to assert `len(readiness_in_pins) == body["created"]`, and it passed for a reason that had
    # nothing to do with this endpoint: `GET /pins` filters `Topic.anchor IS NOT NULL`, and a
    # SQLAlchemy `JSON` column without `none_as_null=True` stores a Python `None` as the JSON
    # scalar `null` -- which is not SQL NULL. So that filter matched every topic ever written and
    # `/pins` returned the whole issue log. PIN-ANCHOR fixed the column; this assertion was the
    # first thing to notice, because it was the only one measuring the difference.
    topics = c.get(f"/projects/{pid}/topics").json()
    readiness = [t for t in topics if t.get("type") == "readiness"]
    assert len(readiness) == body["created"], (len(readiness), body["created"])
    assert all("readiness" in (t.get("labels") or []) for t in readiness), readiness[:1]
    assert any(t.get("priority") == "high" for t in readiness), "a high-severity gap → high-priority topic"

    # A GAP IS ANCHORED WHEN IT NAMES AN ELEMENT, AND NOT OTHERWISE. Four of these gaps are
    # model-wide findings -- egress capacity, occupancy classification, accessible entrance, egress
    # door clear width -- with no single element to point at; `readiness_to_bcf` stores
    # `anchor=None` for them, which is the honest answer. The other seven carry GlobalIds and are
    # placed. Derived from the audit rather than hard-coded, so a change in what the audit finds
    # moves both sides together.
    anchorable = [g for g in ra["gaps"] if [x for x in (g.get("guids") or []) if x]]
    assert 0 < len(anchorable) < body["created"], (
        len(anchorable), body["created"],
        "this check is only meaningful when SOME gaps anchor and some do not")
    assert len([t for t in readiness if t.get("anchor")]) == len(anchorable), (
        [t["title"] for t in readiness if t.get("anchor")], len(anchorable))
    assert all(t.get("element_guids") for t in readiness if t.get("anchor")), \
        "an anchored topic must carry the GlobalId it was anchored from"

    # ...and `/pins` returns EXACTLY that anchored subset -- strictly fewer than the topic count.
    # Before PIN-ANCHOR this returned all eleven, and nothing here or anywhere else said so. The
    # same defect also made that route's `limit=2000` cap -- documented as "keeps the NEWEST pins"
    # -- a cap on the newest 2,000 TOPICS, so a project past that could return a window holding
    # few pins or none while having plenty. That is the LIMIT-FILTER shape, live in `/pins`.
    pins = c.get(f"/projects/{pid}/pins").json()
    readiness_pins = [t for t in pins if t.get("type") == "readiness"]
    assert len(readiness_pins) == len(anchorable), (len(readiness_pins), len(anchorable))
    assert len(readiness_pins) < len(readiness), (
        len(readiness_pins), len(readiness),
        "`/pins` is the ANCHORED subset; equal counts mean the anchor filter is matching every row "
        "again, which is what a JSON column without none_as_null=True does")
    assert all(t.get("anchor") for t in pins), "every row `/pins` returns must have an anchor"

    # idempotent: re-running clears the prior readiness topics, doesn't pile up duplicates
    rb2 = c.post(f"/projects/{pid}/rfi/readiness/bcf").json()
    topics2 = c.get(f"/projects/{pid}/topics").json()
    assert rb2["created"] == body["created"], (rb2["created"], body["created"])
    assert len([t for t in topics2 if t.get("type") == "readiness"]) == body["created"], "no duplicate piling"
    assert len([t for t in c.get(f"/projects/{pid}/pins").json()
                if t.get("type") == "readiness"]) == len(anchorable), "no duplicate piling in pins either"

print(f"READINESS->BCF OK - {body['created']} decision-readiness gaps promoted to type=readiness BCF topics "
      f"(category-labelled, high-severity->high-priority); {len(anchorable)} of them name an element and "
      f"are GUID-anchored, the rest are model-wide findings stored with anchor=None; `/pins` returns "
      f"exactly the anchored subset; 409 without a source IFC; re-running is idempotent (clears prior "
      "readiness topics, no duplicate piling).")
